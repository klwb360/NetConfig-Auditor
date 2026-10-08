import hashlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location("publish_release", Path(__file__).parents[1] / "publish_release.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
COMMIT = "f" * 40
TAG = "v0.1.0"
RECORDS_COMMIT = "a" * 40


def bundle(change=None, version="0.1.0", counts=None):
    prefix = "NetAudit-" + version + "-windows-x64-" + COMMIT[:12]
    packages = {prefix + "-portable.zip": b"portable", prefix + "-onefile.zip": b"onefile",
                prefix + "-onefile.exe": b"exe", "NetAudit-" + version + "-source-" + COMMIT[:12] + ".zip": b"source"}
    reports = {mode: {"mode": mode, "passed": True, "checks": [{"status": "passed"} for _ in range(count)]}
               for mode, count in (counts or (("source", 9), ("onedir", 8), ("onefile", 8)))}
    manifest = {"application": "NetAudit", "application_version": version,
                "source": {"commit": COMMIT, "dirty": False},
                "environment": {"github_run_id": "123", "github_run_attempt": "1",
                                "architecture": "AMD64", "runner_os": "Windows"},
                "verification": reports,
                "artifacts": [{"file": name, "sha256": p.digest(data), "size_bytes": len(data)}
                              for name, data in packages.items()]}
    if change:
        change(manifest, reports)
    files = dict(packages)
    files["manifest.json"] = json.dumps(manifest).encode()
    files.update({f"smoke-{mode}.json": json.dumps(report).encode() for mode, report in reports.items()})
    files["SHA256SUMS.txt"] = "".join(f"{p.digest(data)}  {name}\n" for name, data in files.items()).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return output.getvalue()


def delivery_files():
    archive = bundle()
    return p.verify_bundle(archive, COMMIT, "123", 1, p.digest(archive))[0]


def runtime_files():
    files = delivery_files()
    return {name: files[name] for name in p.runtime_names(TAG, COMMIT)}


class PublicationAPI:
    repository = "owner/repo"

    def __init__(self, files=None, draft=False):
        self.mutations = []
        self.downloads = []
        self.bytes = {}
        self.release = None if files is None else self.make_release(files, draft)

    def make_release(self, files, draft):
        assets = []
        for asset_id, (name, data) in enumerate(sorted(files.items()), start=10):
            assets.append({"id": asset_id, "name": name, "size": len(data)})
            self.bytes[asset_id] = data
        return {"id": 1, "tag_name": TAG, "draft": draft, "assets": assets,
                "upload_url": "https://uploads.github.com/repos/owner/repo/releases/1/assets{?name,label}",
                "html_url": "https://github.com/owner/repo/releases/tag/" + TAG}

    def repo(self, path, **kwargs):
        if kwargs.get("method"):
            self.mutations.append((path, kwargs))
        if path.startswith("git/ref/tags/"):
            return {"object": {"type": "commit", "sha": COMMIT}}
        if path.startswith("releases?"):
            return [] if self.release is None else [self.release]
        if path == "releases" and kwargs.get("method") == "POST":
            self.release = self.make_release({}, True)
            return self.release
        if path == "releases/1" and kwargs.get("method") == "PATCH":
            self.release.update(kwargs["data"])
            return self.release
        if path.startswith("releases/assets/"):
            asset_id = int(path.rsplit("/", 1)[1])
            self.downloads.append(asset_id)
            return self.bytes[asset_id]
        raise AssertionError("Unexpected API request: " + path)

    def request(self, path, **kwargs):
        self.mutations.append((path, kwargs))
        name = p.urllib.parse.parse_qs(p.urllib.parse.urlsplit(path).query)["name"][0]
        asset_id = len(self.bytes) + 10
        data = kwargs["data"]
        self.bytes[asset_id] = data
        asset = {"id": asset_id, "name": name, "size": len(data)}
        self.release["assets"].append(asset)
        return asset


class BuildAPI:
    repository = "owner/repo"

    def __init__(self, expired=False):
        self.archive = bundle()
        self.artifact = {"id": 7, "name": "NetAudit-windows-x64-" + COMMIT,
                         "digest": "sha256:" + p.digest(self.archive), "expired": expired}
        self.config = {"repository": self.repository, "tag": TAG, "source_commit": COMMIT,
                       "run_id": "123", "artifact_id": 7, "artifact_sha256": p.digest(self.archive)}
        self.run = {"status": "completed", "conclusion": "success", "head_sha": COMMIT,
                    "head_branch": "main", "repository": {"full_name": self.repository},
                    "head_repository": {"full_name": self.repository}, "event": "push",
                    "path": ".github/workflows/netaudit-windows.yml", "run_attempt": 1}
        self.release = PublicationAPI(runtime_files()).release
        self.requests = []

    def repo(self, path, **kwargs):
        self.requests.append((path, kwargs))
        if kwargs.get("method"):
            raise AssertionError("Delivery preparation must not mutate Release or tags")
        if path == "":
            return {"private": True}
        if path == "actions/runs/123":
            return self.run
        if path == "actions/runs/123/artifacts?per_page=100":
            return {"artifacts": [self.artifact]}
        if path == "actions/artifacts/7/zip":
            return self.archive
        if path == "git/ref/heads/main":
            return {"object": {"sha": RECORDS_COMMIT}}
        if path.startswith("git/ref/tags/"):
            return {"object": {"type": "commit", "sha": COMMIT}}
        if path == "releases/tags/" + TAG:
            return self.release
        raise AssertionError("Unexpected build API request: " + path)

    def record(self):
        return {"repository": self.repository, "tag": TAG, "source_commit": COMMIT,
                "run_id": "123", "run_attempt": 1,
                "artifact": {key: self.artifact[key] for key in ("id", "name", "digest")}}


class PublicationGuards(unittest.TestCase):
    def verify(self, data):
        return p.verify_bundle(data, COMMIT, "123", 1, p.digest(data))

    def test_complete_bundle_and_archive_digest(self):
        data = bundle()
        self.assertEqual(len(self.verify(data)[0]), 9)
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            p.verify_bundle(data, COMMIT, "123", 1, "0" * 64)

    def test_recovered_files_still_require_all_original_checksums(self):
        files = delivery_files()
        files[next(name for name in files if name.endswith("-onefile.exe"))] = b"changed"
        with self.assertRaisesRegex(ValueError, "File checksum mismatch"):
            p.verify_files(files, COMMIT, "123", 1)

    def test_reject_path_traversal_even_with_matching_archive_digest(self):
        output = io.BytesIO(bundle())
        with zipfile.ZipFile(output, "a") as z:
            z.writestr("../outside", b"danger")
        with self.assertRaisesRegex(ValueError, "Unsafe archive"):
            self.verify(output.getvalue())

    def test_reject_dirty_or_other_source(self):
        for key, value in (("dirty", True), ("commit", "a" * 40)):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "source mismatch"):
                self.verify(bundle(lambda m, r: m["source"].update({key: value})))

    def test_reject_server_left_running(self):
        def change(m, r):
            r["onefile"]["checks"][0]["shutdown"] = {
                "remaining_pids": [123], "forced_cleanup": False, "port_closed": True}
        with self.assertRaisesRegex(ValueError, "Unclean server"):
            self.verify(bundle(change))

    def test_new_version_requires_the_added_process_acceptance(self):
        with self.assertRaisesRegex(ValueError, "Incomplete acceptance"):
            self.verify(bundle(version="0.2.0"))

    def test_new_version_accepts_all_passed_extended_checks(self):
        self.assertEqual(len(self.verify(bundle(version="0.2.0", counts=(("source", 10), ("onedir", 9), ("onefile", 9))))[0]), 9)

    def test_reject_failed_or_foreign_workflow(self):
        run = {"status": "completed", "conclusion": "success", "head_sha": COMMIT,
               "head_branch": "main", "repository": {"full_name": "owner/repo"},
               "head_repository": {"full_name": "owner/repo"}, "event": "push",
               "path": ".github/workflows/netaudit-windows.yml"}
        p.validate_run(run, "owner/repo", COMMIT)
        for key, value in (("conclusion", "failure"), ("head_sha", "a" * 40), ("event", "pull_request")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                p.validate_run(dict(run, **{key: value}), "owner/repo", COMMIT)

    def test_refuse_authenticated_request_to_storage(self):
        api = p.GitHub("owner/repo", "test-token")
        with patch.object(api.opener, "open") as opening:
            with self.assertRaisesRegex(ValueError, "outside GitHub"):
                api.request("https://storage.example.com/file", binary=True)
            opening.assert_not_called()

    def test_repository_metadata_endpoint_has_no_trailing_slash(self):
        api = p.GitHub("owner/repo", "test-token")
        with patch.object(api, "request", return_value={"private": True}) as request:
            self.assertEqual(api.repo(""), {"private": True})
            request.assert_called_once_with("/repos/owner/repo")

    def test_delete_asset_accepts_no_content_response(self):
        class Response:
            status = 204
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, limit):
                return b""
        api = p.GitHub("owner/repo", "test-token")
        with patch.object(api.opener, "open", return_value=Response()) as opening:
            self.assertIsNone(api.repo("releases/assets/2", method="DELETE"))
            request = opening.call_args.args[0]
            self.assertEqual(request.get_method(), "DELETE")
            self.assertEqual(request.full_url,
                             "https://api.github.com/repos/owner/repo/releases/assets/2")

    def test_artifact_and_asset_use_their_documented_media_types(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, limit):
                return b"bytes"
        api = p.GitHub("owner/repo", "test-token")
        with patch.object(api.opener, "open", return_value=Response()) as opening:
            api.repo("actions/artifacts/1/zip", binary=True)
            self.assertEqual(opening.call_args.args[0].get_header("Accept"), "application/vnd.github+json")
            api.repo("releases/assets/2", binary=True, accept="application/octet-stream")
            self.assertEqual(opening.call_args.args[0].get_header("Accept"), "application/octet-stream")

    def test_storage_request_has_no_authorization(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, limit):
                return b"artifact"
        with patch.object(p.urllib.request, "build_opener") as opening:
            opening.return_value.open.return_value = Response()
            self.assertEqual(p.GitHub.storage_download("https://storage.example.com/file"), b"artifact")
            request = opening.return_value.open.call_args.args[0]
            self.assertIsNone(request.get_header("Authorization"))

    def test_tag_conflict_stops_without_write(self):
        class API:
            def repo(self, path, **kwargs):
                if kwargs:
                    raise AssertionError("Conflict must not write")
                return {"object": {"type": "commit", "sha": "a" * 40}}
        with self.assertRaisesRegex(ValueError, "different source"):
            p.ensure_tag(API(), "v0.1.0", COMMIT)

    def test_bad_asset_keeps_draft_unpublished(self):
        api = PublicationAPI(runtime_files(), draft=True)
        api.bytes[min(api.bytes)] = b"changed"
        with self.assertRaisesRegex(ValueError, "asset verification failed"):
            p.publish(api, TAG, COMMIT, runtime_files(), "notes")
        self.assertTrue(api.release["draft"])
        self.assertEqual(api.mutations, [])

    def test_published_release_missing_asset_is_never_modified(self):
        files = runtime_files()
        api = PublicationAPI({name: data for name, data in files.items() if not name.endswith("-portable.zip")})
        with self.assertRaisesRegex(ValueError, "Published release is incomplete"):
            p.publish(api, TAG, COMMIT, files, "notes")
        self.assertEqual(api.mutations, [])

    def test_new_release_uploads_and_verifies_only_three_runtime_assets(self):
        api = PublicationAPI()
        files = runtime_files()
        self.assertEqual(p.publish(api, TAG, COMMIT, files, "notes"), api.release["html_url"])
        self.assertEqual({asset["name"] for asset in api.release["assets"]}, set(files))
        self.assertEqual(len(api.downloads), 3)
        uploads = [kwargs for path, kwargs in api.mutations if kwargs.get("upload")]
        self.assertEqual(len(uploads), 3)
        self.assertTrue(all(kwargs["method"] == "POST" for kwargs in uploads))
        self.assertEqual(api.mutations[-1][0], "releases/1")
        self.assertFalse(api.release["draft"])

    def test_published_three_runtime_assets_reverify_without_writes(self):
        api = PublicationAPI(runtime_files())
        p.publish(api, TAG, COMMIT, runtime_files(), "updated notes")
        self.assertEqual(len(api.downloads), 3)
        self.assertEqual(api.mutations, [])

    def test_published_legacy_nine_assets_require_explicit_migration(self):
        api = PublicationAPI(delivery_files())
        with self.assertRaisesRegex(ValueError, "explicit archival migration"):
            p.publish(api, TAG, COMMIT, runtime_files(), "notes")
        self.assertEqual(api.mutations, [])
        self.assertEqual(api.downloads, [])

    def test_delivery_preparation_verifies_nine_before_archiving_then_returns_three(self):
        api = BuildAPI()
        with patch.object(p.records, "ensure_records", return_value=RECORDS_COMMIT) as archive:
            runtime, manifest, reference, recovered = p.prepare_delivery(api, api.config, TAG, COMMIT, "123")
        args = archive.call_args.args
        self.assertEqual(len(args[2]), 9)
        self.assertEqual(args[3], manifest)
        self.assertEqual(set(runtime), p.runtime_names(TAG, COMMIT))
        self.assertEqual(reference, RECORDS_COMMIT)
        self.assertFalse(recovered)

    def test_failed_permanent_record_verification_stops_before_publish(self):
        api = BuildAPI()
        with patch.dict(p.os.environ, {"GITHUB_TOKEN": "test-token"}, clear=True), \
                patch.object(p.Path, "read_text", return_value=json.dumps(api.config)), \
                patch.object(p, "GitHub", return_value=api), \
                patch.object(p.records, "ensure_records", side_effect=ValueError("Archive digest mismatch")), \
                patch.object(p, "publish") as publish:
            with self.assertRaisesRegex(ValueError, "Archive digest mismatch"):
                p.main()
            publish.assert_not_called()

    def test_expired_artifact_reconstructs_nine_without_downloading_outer_archive(self):
        api = BuildAPI(expired=True)
        with patch.object(p.records, "load_records", return_value=(api.record(), {})) as load, \
                patch.object(p.records, "recover_files", return_value=delivery_files()) as recover, \
                patch.object(p.records, "ensure_records", return_value=RECORDS_COMMIT):
            runtime, _, reference, recovered = p.prepare_delivery(api, api.config, TAG, COMMIT, "123")
        self.assertTrue(recovered)
        self.assertEqual(reference, RECORDS_COMMIT)
        self.assertEqual(len(runtime), 3)
        load.assert_called_once_with(api, TAG, RECORDS_COMMIT)
        recover.assert_called_once_with(api, TAG, RECORDS_COMMIT, api.release)
        self.assertNotIn("actions/artifacts/7/zip", [path for path, _ in api.requests])

    def test_expired_artifact_cannot_publish_a_new_draft_or_legacy_release(self):
        for release in (None, PublicationAPI(runtime_files(), draft=True).release,
                        PublicationAPI(delivery_files()).release):
            api = BuildAPI(expired=True)
            api.release = release
            with self.subTest(release=release), \
                    patch.object(p.records, "load_records", return_value=(api.record(), {})), \
                    patch.object(p.records, "recover_files") as recover, \
                    patch.object(p.records, "ensure_records") as archive:
                with self.assertRaisesRegex(ValueError, "Expired build requires"):
                    p.prepare_delivery(api, api.config, TAG, COMMIT, "123")
                recover.assert_not_called()
                archive.assert_not_called()

    def test_expired_artifact_records_cannot_change_build_identity(self):
        api = BuildAPI(expired=True)
        record = api.record()
        record["source_commit"] = "0" * 40
        with patch.object(p.records, "load_records", return_value=(record, {})), \
                patch.object(p.records, "recover_files") as recover:
            with self.assertRaisesRegex(ValueError, "Archived build identity mismatch"):
                p.prepare_delivery(api, api.config, TAG, COMMIT, "123")
            recover.assert_not_called()


class ReleaseNotesTests(unittest.TestCase):
    def manifest(self, version):
        def add_environment(manifest, reports):
            manifest["environment"].update({"os": "Windows-2022", "python": "3.12.10"})
            manifest["build_dependencies"] = {"pyinstaller": "6.12.0"}
        archive = bundle(add_environment, version=version,
                         counts=(("source", 10), ("onedir", 9), ("onefile", 9)))
        return p.verify_bundle(archive, COMMIT, "123", 1, p.digest(archive))[1]

    def test_legacy_notes_keep_original_vendor_and_feature_scope(self):
        for version in ("0.1.0", "0.2.0", "0.2.1"):
            with self.subTest(version=version):
                text = p.notes("owner/repo", "v" + version, self.manifest(version), "123")
                self.assertIn("选择 Cisco、华为或 H3C", text)
                self.assertIn("三厂商及三种报告", text)
                self.assertNotIn("锐捷", text)
                self.assertNotIn("四厂商", text)
                self.assertNotIn("配置解析与整改修复", text)
                self.assertEqual("### 本版升级" in text, version != "0.1.0")
                self.assertEqual("### 界面与使用体验" in text, version == "0.2.1")

    def test_current_and_future_notes_describe_rgos_grouping_and_command_limits(self):
        for version in ("0.2.2", "0.2.3", "0.3.0"):
            with self.subTest(version=version):
                text = p.notes("owner/repo", "v" + version, self.manifest(version), "123")
                for expected in ("选择 Cisco、华为、H3C 或锐捷 RGOS", "四厂商及三种报告",
                                 "`vlan range`", "单编号 VTY", "`no spanning-tree`",
                                 "同一缺失 VLAN 按 VLAN ID 合并", "全部相关端口", "完整配置证据",
                                 "发生次数", "不同风险等级", "只读核查命令", "整改脚本",
                                 "候选模板", "执行前提", "完整模式进入与退出", "不连接设备或自动执行整改"):
                    self.assertIn(expected, text)
                self.assertNotIn("三厂商及三种报告", text)

    def test_theme_notes_only_apply_to_supported_versions(self):
        for version in ("0.1.0", "0.2.0", "0.2.1", "0.2.2"):
            with self.subTest(version=version):
                text = p.notes("owner/repo", "v" + version, self.manifest(version), "123")
                self.assertNotIn("主题切换与重复风险折叠", text)
                self.assertNotIn("跟随系统", text)

    def test_theme_notes_describe_display_only_grouping_and_complete_reports(self):
        for version in ("0.2.3", "0.3.0"):
            with self.subTest(version=version):
                manifest = self.manifest(version)
                original = json.dumps(manifest, sort_keys=True)
                text = p.notes("owner/repo", "v" + version, manifest, "123")
                for expected in ("主题切换与重复风险折叠", "明亮", "暗黑", "跟随系统",
                                 "浏览器记住主题偏好", "配置内容不会随主题偏好保存",
                                 "涉及处数", "每项对象、证据和整改建议", "一键展开或收起",
                                 "折叠仅调整网页展示", "严重度筛选", "审计统计",
                                 "JSON / Markdown / HTML 完整报告"):
                    self.assertIn(expected, text)
                rows = [line for line in text.splitlines() if line.startswith("| `NetAudit-")]
                self.assertEqual(len(rows), 3)
                self.assertEqual(json.dumps(manifest, sort_keys=True), original)

    def test_new_notes_preserve_three_runtime_downloads_and_permanent_records(self):
        manifest = self.manifest("0.2.2")
        original = json.dumps(manifest, sort_keys=True)
        text = p.notes("owner/repo", "v0.2.2", manifest, "123", RECORDS_COMMIT)
        rows = [line for line in text.splitlines() if line.startswith("| `NetAudit-")]
        self.assertEqual(len(rows), 3)
        for artifact in manifest["artifacts"]:
            if artifact["file"].endswith(("-portable.zip", "-onefile.zip", "-onefile.exe")):
                self.assertIn(f"| `{artifact['file']}` | `{artifact['sha256']}` |", rows)
            else:
                self.assertNotIn(artifact["file"], text)
        self.assertIn("https://github.com/owner/repo/tree/" + RECORDS_COMMIT + "/docs/releases/v0.2.2", text)
        self.assertIn("https://github.com/owner/repo/tree/v0.2.2", text)
        self.assertIn("原始 `SHA256SUMS.txt` 保留完整九文件交付时其余八个文件的校验值", text)
        self.assertIn("GPL-3.0-only", text)
        self.assertIn("两个分发 ZIP 内保留对应源码 ZIP、许可证与来源说明", text)
        self.assertEqual(json.dumps(manifest, sort_keys=True), original)
