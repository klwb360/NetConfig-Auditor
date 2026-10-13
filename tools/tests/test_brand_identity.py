"""Keep the new distribution brand coherent without rewriting old releases."""
import copy
import hashlib
import io
import json
import unittest
from unittest.mock import patch
import zipfile

from tools.tests import test_publish_release as fixture
from tools.tests import test_release_records as archive_fixture

p = fixture.p
r = p.records
COMMIT = fixture.COMMIT


def branded_bundle():
    raw = fixture.bundle(fixture.highlighting_evidence, version="1.1.1",
                         counts=(("source", 10), ("onedir", 9), ("onefile", 9)))
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        files = {name.replace("NetAudit-", "NetConfig-Auditor-"): archive.read(name)
                 for name in archive.namelist()}
    manifest = json.loads(files["manifest.json"])
    manifest["application"] = "NetConfig Auditor"
    for item in manifest["artifacts"]:
        item["file"] = item["file"].replace("NetAudit-", "NetConfig-Auditor-")
    files["manifest.json"] = json.dumps(manifest).encode()
    files["SHA256SUMS.txt"] = "".join(
        p.digest(raw) + "  " + name + "\n" for name, raw in files.items()
        if name != "SHA256SUMS.txt").encode()
    return files


class BrandIdentityTests(unittest.TestCase):
    def test_filename_identity_changes_only_from_1_1_1(self):
        for version in ("0.1.0", "1.0.1", "1.1.0", "1.1.1", "1.2.0"):
            stem = "NetConfig-Auditor" if tuple(map(int, version.split("."))) >= (1, 1, 1) else "NetAudit"
            expected = {f"{stem}-{version}-windows-x64-{COMMIT[:12]}{suffix}"
                        for suffix in ("-portable.zip", "-onefile.zip", "-onefile.exe")}
            self.assertEqual(p.runtime_names("v" + version, COMMIT), expected)
            self.assertEqual(set(r.identity("v" + version, COMMIT)), expected)

    def test_current_bundle_accepts_new_brand_and_rejects_wrong_application(self):
        files = branded_bundle()
        self.assertEqual(len(p.verify_files(files, COMMIT, "123", 1)[0]), 9)
        changed = dict(files)
        manifest = json.loads(changed["manifest.json"])
        manifest["application"] = "NetAudit"
        changed["manifest.json"] = json.dumps(manifest).encode()
        changed["SHA256SUMS.txt"] = "".join(p.digest(raw) + "  " + name + "\n"
            for name, raw in changed.items() if name != "SHA256SUMS.txt").encode()
        with self.assertRaisesRegex(ValueError, "Manifest source mismatch"):
            p.verify_files(changed, COMMIT, "123", 1)

    def test_current_archive_uses_new_source_roots_and_rejects_old_artifact(self):
        files, manifest, artifact = archive_fixture.delivery()
        names = {old: old.replace("NetAudit-0.2.1-", "NetConfig-Auditor-1.1.1-") for old in files}
        renamed = {names[name]: raw for name, raw in files.items()}
        source_name = next(name for name in renamed if "-source-" in name)
        for suffix, root in (("-portable.zip", "NetConfig-Auditor/"),
                             ("-onefile.zip", "NetConfig-Auditor-onefile/")):
            name = next(name for name in renamed if name.endswith(suffix))
            renamed[name] = archive_fixture.zip_bytes({root + source_name: renamed[source_name]})
        manifest = copy.deepcopy(manifest)
        manifest["application_version"] = "1.1.1"
        artifact = dict(artifact, name="NetConfig-Auditor-windows-x64-" + archive_fixture.SOURCE_COMMIT)
        record = r.make_record("owner/repo", "v1.1.1", renamed, manifest, artifact)
        self.assertEqual(record["source_name"], source_name)
        self.assertTrue(all(item["member"].startswith("NetConfig-Auditor") for item in record["source_locations"]))
        archived = r.archive_files("owner/repo", "v1.1.1", renamed, manifest, artifact)
        assets = [{"id": number, "name": name, "size": len(renamed[name])}
                  for number, name in enumerate(record["runtime_names"], start=20)]
        api = archive_fixture.ArchiveAPI(archived,
            {item["id"]: renamed[item["name"]] for item in assets})
        api.repository = "owner/repo"
        recovered = r.recover_files(api, "v1.1.1", archive_fixture.ARCHIVE_COMMIT,
                                   {"tag_name": "v1.1.1", "draft": False, "assets": assets})
        self.assertEqual(recovered, renamed)
        self.assertEqual(api.mutations, [])
        with self.assertRaisesRegex(ValueError, "artifact identity"):
            r.make_record("owner/repo", "v1.1.1", renamed, manifest,
                          dict(artifact, name="NetAudit-windows-x64-" + archive_fixture.SOURCE_COMMIT))

    def test_current_build_artifact_is_found_before_delivery_is_archived(self):
        files = branded_bundle()
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for name, raw in files.items():
                archive.writestr(name, raw)
        api = fixture.BuildAPI()
        api.archive = output.getvalue()
        api.artifact.update(name="NetConfig-Auditor-windows-x64-" + COMMIT,
                            digest="sha256:" + p.digest(api.archive))
        api.config["tag"] = "v1.1.1"
        api.config["artifact_sha256"] = p.digest(api.archive)
        with patch.object(r, "ensure_records", return_value=fixture.RECORDS_COMMIT):
            runtime, manifest, _, recovered = p.prepare_delivery(api, api.config, "v1.1.1", COMMIT, "123")
        self.assertEqual(set(runtime), p.runtime_names("v1.1.1", COMMIT))
        self.assertEqual(manifest["application"], "NetConfig Auditor")
        self.assertFalse(recovered)

    def test_1_1_0_notes_remain_byte_identical(self):
        manifest = fixture.ReleaseNotesTests().manifest("1.1.0")
        text = p.notes("owner/repo", "v1.1.0", manifest, "123")
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),
                         "da5ca8479e717c6d51f0a3d203487d9305522d19dce39284e3191926da7641b7")

    def test_new_release_title_and_three_downloads_use_current_brand(self):
        api = fixture.PublicationAPI()
        files = branded_bundle()
        runtime = {name: files[name] for name in p.runtime_names("v1.1.1", COMMIT)}
        p.publish(api, "v1.1.1", COMMIT, runtime, "new release notes")
        creation = next(kwargs["data"] for path, kwargs in api.mutations
                        if path == "releases" and kwargs["method"] == "POST")
        self.assertEqual(creation["name"], "NetConfig Auditor 1.1.1 · Windows x64 便携版")
        self.assertEqual({item["name"] for item in api.release["assets"]}, set(runtime))

    def test_new_notes_use_new_launchers_and_describe_neutral_dark_theme(self):
        manifest = fixture.ReleaseNotesTests().manifest("1.1.1")
        text = p.notes("owner/repo", "v1.1.1", manifest, "123")
        for term in ("NetConfig Auditor", "Start-NetConfig-Auditor.bat", "NetConfig-Auditor.exe", "#111111", "中性"):
            self.assertIn(term, text)


if __name__ == "__main__":
    unittest.main()
