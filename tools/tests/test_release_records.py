import base64
import importlib.util
import io
import json
from pathlib import Path
import unittest
import urllib.parse
import zipfile


spec = importlib.util.spec_from_file_location(
    "release_records_under_test", Path(__file__).parents[1] / "release_records.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
TAG = "v0.2.1"
SOURCE_COMMIT = "b" * 40
ARCHIVE_COMMIT = "a" * 40
REPOSITORY = "owner/NetAudit"
BASE = "docs/releases/" + TAG + "/"


def zip_bytes(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in entries.items():
            archive.writestr(zipfile.ZipInfo(name, (2026, 10, 3, 0, 0, 0)), raw)
    return output.getvalue()


def delivery():
    source_name = "NetAudit-0.2.1-source-" + SOURCE_COMMIT[:12] + ".zip"
    source = zip_bytes({"network-config-auditor/main.py": b"print('NetAudit')\n",
                        "LICENSE": b"Original license\r\n"})
    names = r.identity(TAG, SOURCE_COMMIT)
    files = {source_name: source}
    for suffix, root in (("-portable.zip", "NetAudit/"),
                         ("-onefile.zip", "NetAudit-onefile/")):
        name = next(name for name in names if name.endswith(suffix))
        files[name] = zip_bytes({root + "NetAudit.exe": b"frozen runtime",
                                root + source_name: source})
    files[next(name for name in names if name.endswith("-onefile.exe"))] = b"standalone EXE"
    manifest = {"application_version": "0.2.1", "source": {"commit": SOURCE_COMMIT},
                "environment": {"github_run_id": "123", "github_run_attempt": "1"}}
    # Preserve whitespace, CRLF, and non-ASCII bytes rather than re-serializing records.
    files["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=4).encode() + b"\r\n"
    for mode in ("source", "onedir", "onefile"):
        files["smoke-" + mode + ".json"] = (
            '{ "mode": "' + mode + '", "passed": true, "note": "实际验收" }\r\n').encode()
    files["SHA256SUMS.txt"] = "".join(
        r.digest(raw) + "  " + name + "\r\n" for name, raw in files.items()).encode()
    artifact = {"id": 42, "name": "NetAudit-windows-x64-" + SOURCE_COMMIT,
                "digest": "sha256:" + "c" * 64}
    return files, manifest, artifact


class ArchiveAPI:
    repository = REPOSITORY

    def __init__(self, contents=None, runtime=None):
        self.contents = dict(contents or {})
        self.requests = []
        self.mutations = []
        self.downloads = []
        self.runtime = dict(runtime or {})

    def repo(self, path, **kwargs):
        self.requests.append((path, kwargs))
        if kwargs.get("method"):
            self.mutations.append((path, kwargs))
            raise AssertionError("Archive test must not write or mutate Release: " + path)
        if path == "git/ref/heads/main":
            return {"object": {"sha": ARCHIVE_COMMIT}}
        if path.startswith("contents/"):
            parsed = urllib.parse.urlsplit(path)
            if urllib.parse.parse_qs(parsed.query).get("ref") != [ARCHIVE_COMMIT]:
                raise AssertionError("Records must be read at the pinned archive commit")
            name = urllib.parse.unquote(parsed.path[len("contents/"):])
            raw = self.contents.get(name)
            if raw is None:
                return None
            # GitHub inserts line breaks into its base64 contents responses.
            encoded = base64.b64encode(raw).decode()
            encoded = "\n".join(encoded[i:i + 60] for i in range(0, len(encoded), 60))
            return {"type": "file", "encoding": "base64", "size": len(raw), "content": encoded}
        if path.startswith("releases/assets/"):
            self.downloads.append(path)
            return self.runtime[int(path.rsplit("/", 1)[1])]
        raise AssertionError("Unexpected API request: " + path)


class ReleaseRecordsGuards(unittest.TestCase):
    def setUp(self):
        self.files, self.manifest, self.artifact = delivery()
        self.archive = r.archive_files(REPOSITORY, TAG, self.files, self.manifest, self.artifact)

    def api(self, archive=None):
        return ArchiveAPI(self.archive if archive is None else archive)

    def release(self):
        assets = []
        runtime = {}
        for asset_id, name in enumerate(r.identity(TAG, SOURCE_COMMIT), start=20):
            runtime[asset_id] = self.files[name]
            assets.append({"id": asset_id, "name": name, "size": len(self.files[name])})
        return {"tag_name": TAG, "draft": False, "assets": assets}, runtime

    def test_archive_keeps_original_five_file_bytes_and_source_locations(self):
        self.assertEqual(set(self.archive), {BASE + name for name in r.TEXT_NAMES}
                         | {BASE + "record.json", BASE + "README.md"})
        for name in r.TEXT_NAMES:
            self.assertEqual(self.archive[BASE + name], self.files[name])
        record = json.loads(self.archive[BASE + "record.json"])
        self.assertEqual(len(record["files"]), 9)
        self.assertEqual(record["source_commit"], SOURCE_COMMIT)
        self.assertEqual(record["artifact"], self.artifact)
        self.assertEqual(len(record["source_locations"]), 2)

    def test_both_runtime_archives_must_embed_identical_original_source(self):
        changed = dict(self.files)
        name = next(name for name in changed if name.endswith("-onefile.zip"))
        source_name = next(name for name in changed if "-source-" in name)
        original = changed[source_name]
        changed[name] = zip_bytes({"NetAudit-onefile/" + source_name: b"x" * len(original)})
        with self.assertRaisesRegex(ValueError, "preserve the original source"):
            r.make_record(REPOSITORY, TAG, changed, self.manifest, self.artifact)

    def test_record_verification_accepts_original_crlf_and_unusual_json_whitespace(self):
        api = self.api()
        self.assertTrue(r.verify_records(api, TAG, self.files, self.manifest,
                                         self.artifact, ARCHIVE_COMMIT))
        self.assertEqual(api.mutations, [])

    def test_any_archived_original_file_change_is_rejected(self):
        for name in r.TEXT_NAMES:
            with self.subTest(name=name):
                changed = dict(self.archive)
                changed[BASE + name] += b" "
                api = self.api(changed)
                with self.assertRaisesRegex(ValueError, "verification file mismatch"):
                    r.verify_records(api, TAG, self.files, self.manifest,
                                     self.artifact, ARCHIVE_COMMIT)
                self.assertEqual(api.mutations, [])

    def test_source_identity_in_record_cannot_be_changed(self):
        changed = dict(self.archive)
        record = json.loads(changed[BASE + "record.json"])
        record["source_commit"] = "d" * 40
        changed[BASE + "record.json"] = r.encode_record(record)
        with self.assertRaisesRegex(ValueError, "delivery identity mismatch"):
            r.verify_records(self.api(changed), TAG, self.files, self.manifest,
                             self.artifact, ARCHIVE_COMMIT)

    def test_original_file_hash_in_record_cannot_be_changed(self):
        changed = dict(self.archive)
        record = json.loads(changed[BASE + "record.json"])
        record["files"]["manifest.json"]["sha256"] = "0" * 64
        changed[BASE + "record.json"] = r.encode_record(record)
        with self.assertRaisesRegex(ValueError, "verification file mismatch"):
            r.verify_records(self.api(changed), TAG, self.files, self.manifest,
                             self.artifact, ARCHIVE_COMMIT)

    def test_different_build_artifact_cannot_reuse_existing_archive(self):
        artifact = dict(self.artifact, id=self.artifact["id"] + 1)
        with self.assertRaisesRegex(ValueError, "delivery identity mismatch"):
            r.verify_records(self.api(), TAG, self.files, self.manifest,
                             artifact, ARCHIVE_COMMIT)

    def test_recover_complete_original_bundle_using_only_three_release_assets(self):
        release, runtime = self.release()
        api = ArchiveAPI(self.archive, runtime)
        recovered = r.recover_files(api, TAG, ARCHIVE_COMMIT, release)
        self.assertEqual(recovered, self.files)
        self.assertEqual(len(api.downloads), 3)
        self.assertEqual(api.mutations, [])

    def test_changed_downloaded_runtime_bytes_fail_even_when_size_matches(self):
        release, runtime = self.release()
        asset_id = release["assets"][0]["id"]
        original = runtime[asset_id]
        runtime[asset_id] = bytes([original[0] ^ 1]) + original[1:]
        api = ArchiveAPI(self.archive, runtime)
        with self.assertRaisesRegex(ValueError, "Runnable asset bytes changed"):
            r.recover_files(api, TAG, ARCHIVE_COMMIT, release)
        self.assertEqual(api.mutations, [])

    def test_missing_runtime_asset_is_rejected_before_any_download(self):
        release, runtime = self.release()
        release["assets"].pop()
        api = ArchiveAPI(self.archive, runtime)
        with self.assertRaisesRegex(ValueError, "Missing or duplicate runnable"):
            r.recover_files(api, TAG, ARCHIVE_COMMIT, release)
        self.assertEqual(api.downloads, [])
        self.assertEqual(api.mutations, [])

    def test_partial_existing_archive_is_not_overwritten(self):
        for name in ("manifest.json", "smoke-source.json", "README.md"):
            with self.subTest(name=name):
                api = self.api({BASE + name: self.archive[BASE + name]})
                with self.assertRaisesRegex(ValueError, "partial version archive"):
                    r.ensure_records(api, TAG, self.files, self.manifest, self.artifact)
                self.assertEqual(api.mutations, [])

    def test_existing_matching_archive_does_not_make_a_new_commit(self):
        api = self.api()
        self.assertEqual(r.ensure_records(api, TAG, self.files, self.manifest,
                                          self.artifact), ARCHIVE_COMMIT)
        self.assertEqual(api.mutations, [])

    def test_existing_invalid_archive_is_not_replaced(self):
        changed = dict(self.archive)
        changed[BASE + "smoke-onedir.json"] += b"changed"
        api = self.api(changed)
        with self.assertRaisesRegex(ValueError, "verification file mismatch"):
            r.ensure_records(api, TAG, self.files, self.manifest, self.artifact)
        self.assertEqual(api.mutations, [])

    def test_archive_reads_require_an_immutable_reference(self):
        api = self.api()
        with self.assertRaisesRegex(ValueError, "immutable commit"):
            r.load_records(api, TAG, "main")
        self.assertEqual(api.requests, [])

    def test_missing_records_stop_recovery_before_release_assets_are_touched(self):
        release, runtime = self.release()
        api = ArchiveAPI({}, runtime)
        with self.assertRaisesRegex(ValueError, "Archived file unavailable"):
            r.recover_files(api, TAG, ARCHIVE_COMMIT, release)
        self.assertEqual(api.downloads, [])
        self.assertEqual(api.mutations, [])


if __name__ == "__main__":
    unittest.main()
