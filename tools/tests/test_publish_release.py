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


def bundle(change=None):
    prefix = "NetAudit-0.1.0-windows-x64-" + COMMIT[:12]
    packages = {prefix + "-portable.zip": b"portable", prefix + "-onefile.zip": b"onefile",
                prefix + "-onefile.exe": b"exe", "NetAudit-0.1.0-source-" + COMMIT[:12] + ".zip": b"source"}
    reports = {mode: {"mode": mode, "passed": True, "checks": [{"status": "passed"} for _ in range(count)]}
               for mode, count in (("source", 9), ("onedir", 8), ("onefile", 8))}
    manifest = {"application": "NetAudit", "application_version": "0.1.0",
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


class PublicationGuards(unittest.TestCase):
    def verify(self, data):
        return p.verify_bundle(data, COMMIT, "123", 1, p.digest(data))

    def test_complete_bundle_and_archive_digest(self):
        data = bundle()
        self.assertEqual(len(self.verify(data)[0]), 9)
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            p.verify_bundle(data, COMMIT, "123", 1, "0" * 64)

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
        class API:
            repository = "owner/repo"
            def repo(self, path, **kwargs):
                if path.startswith("git/ref/"):
                    return {"object": {"type": "commit", "sha": COMMIT}}
                if path.startswith("releases?"):
                    return [{"id": 1, "tag_name": "v0.1.0", "draft": True,
                             "assets": [{"id": 2, "name": "test.zip", "size": 4}]}]
                if path == "releases/assets/2":
                    return b"bad!"
                raise AssertionError("Failed verification must not publish")
        with self.assertRaisesRegex(ValueError, "asset verification failed"):
            p.publish(API(), "v0.1.0", COMMIT, {"test.zip": b"good"}, "notes")

    def test_published_release_missing_asset_is_never_modified(self):
        class API:
            def repo(self, path, **kwargs):
                if kwargs:
                    raise AssertionError("Published assets must not be modified")
                if path.startswith("git/ref/"):
                    return {"object": {"type": "commit", "sha": COMMIT}}
                return [{"id": 1, "tag_name": "v0.1.0", "draft": False, "assets": []}]
        with self.assertRaisesRegex(ValueError, "Published release is incomplete"):
            p.publish(API(), "v0.1.0", COMMIT, {"test.zip": b"good"}, "notes")
