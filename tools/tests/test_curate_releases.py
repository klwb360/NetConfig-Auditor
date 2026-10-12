import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).parents[1]
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location("curate_releases", TOOLS / "curate_releases.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
p = c.p
COMMIT = "f" * 40
REFERENCE = "a" * 40
REPOSITORY = "klwb360/NetAudit"


def fixture():
    config = {"repository": REPOSITORY, "releases": []}
    deliveries = {}
    for index, tag in enumerate(("v0.2.1", "v0.2.0", "v0.1.0")):
        version = tag[1:]
        prefix = f"NetAudit-{version}-windows-x64-{COMMIT[:12]}"
        packages = {prefix + "-portable.zip": b"portable", prefix + "-onefile.zip": b"onefile",
                    prefix + "-onefile.exe": b"executable",
                    f"NetAudit-{version}-source-{COMMIT[:12]}.zip": b"source"}
        counts = (("source", 9), ("onedir", 8), ("onefile", 8)) if version == "0.1.0" else (
            ("source", 10), ("onedir", 9), ("onefile", 9))
        reports = {mode: {"mode": mode, "passed": True,
                          "checks": [{"status": "passed"} for _ in range(count)]}
                   for mode, count in counts}
        run_id = 1000 + index
        manifest = {"application": "NetAudit", "application_version": version,
                    "source": {"commit": COMMIT, "dirty": False},
                    "environment": {"github_run_id": str(run_id), "github_run_attempt": "1",
                                    "architecture": "AMD64", "runner_os": "Windows"},
                    "verification": reports,
                    "artifacts": [{"file": name, "sha256": p.digest(data), "size_bytes": len(data)}
                                  for name, data in packages.items()]}
        files = dict(packages)
        files["manifest.json"] = json.dumps(manifest).encode()
        files.update({f"smoke-{mode}.json": json.dumps(report).encode() for mode, report in reports.items()})
        files["SHA256SUMS.txt"] = "".join(f"{p.digest(data)}  {name}\n" for name, data in files.items()).encode()
        assets = [{"id": 100 + index * 10 + offset, "name": name, "size": len(data),
                   "digest": "sha256:" + p.digest(data),
                   "keep": name.endswith(c.RUNTIME_SUFFIXES)}
                  for offset, (name, data) in enumerate(files.items())]
        config["releases"].append({"id": index + 1, "tag": tag, "source_commit": COMMIT,
                                    "run_id": run_id, "run_attempt": 1,
                                    "artifact": {"id": 5000 + index,
                                                 "name": "NetAudit-windows-x64-" + COMMIT,
                                                 "digest": "sha256:" + "b" * 64}, "assets": assets})
        deliveries[tag] = files
    return config, deliveries


class FakeAPI:
    repository = REPOSITORY

    def __init__(self, config, deliveries):
        self.config = config
        self.deliveries = deliveries
        self.releases = {plan["id"]: {"id": plan["id"], "tag_name": plan["tag"],
                                     "draft": False, "prerelease": False, "body": "old notes",
                                     "assets": [{k: v for k, v in a.items() if k != "keep"}
                                                for a in plan["assets"]]}
                         for plan in config["releases"]}
        self.mutations = []
        self.verified_archives = []
        self.bad_run = None
        self.bad_tag = None
        self.corrupt_asset = None
        self.after_delete = None
        self.private = True
        self.latest_id = 1

    def repo(self, path, **kwargs):
        method = kwargs.get("method", "GET")
        if method != "GET":
            if len(self.verified_archives) != 3:
                raise AssertionError("All three archives must pass before any write")
            self.mutations.append((method, path, kwargs.get("data")))
            if method == "PATCH":
                if set(kwargs["data"]) != {"body"}:
                    raise AssertionError("Only description may be patched")
                release = self.releases[int(path.split("/")[-1])]
                release.update(kwargs["data"])
                return copy.deepcopy(release)
            if method == "DELETE":
                asset_id = int(path.split("/")[-1])
                for release in self.releases.values():
                    release["assets"] = [a for a in release["assets"] if a["id"] != asset_id]
                if self.after_delete:
                    self.after_delete(self)
                return None
            raise AssertionError("Unexpected mutation")
        if path == "":
            return {"private": self.private}
        if path == "releases/latest":
            return copy.deepcopy(self.releases[self.latest_id])
        if path.startswith("git/ref/tags/"):
            tag = path.rsplit("/", 1)[1]
            return {"object": {"type": "commit", "sha": "c" * 40 if tag == self.bad_tag else COMMIT}}
        if path.startswith("actions/runs/"):
            run_id = int(path.rsplit("/", 1)[1])
            return {"status": "completed", "conclusion": "failure" if run_id == self.bad_run else "success",
                    "head_sha": COMMIT, "head_branch": "main", "run_attempt": 1,
                    "repository": {"full_name": self.repository}, "head_repository": {"full_name": self.repository},
                    "path": ".github/workflows/netaudit-windows.yml", "event": "push"}
        if path.startswith("releases/assets/"):
            asset_id = int(path.rsplit("/", 1)[1])
            for plan in self.config["releases"]:
                for asset in plan["assets"]:
                    if asset["id"] == asset_id:
                        if kwargs.get("accept") != "application/octet-stream" or not kwargs.get("binary"):
                            raise AssertionError("Release download must use documented media type")
                        return b"corrupt" if asset_id == self.corrupt_asset else self.deliveries[plan["tag"]][asset["name"]]
            raise AssertionError("Unknown asset download")
        if path.startswith("releases/"):
            return copy.deepcopy(self.releases[int(path.rsplit("/", 1)[1])])
        raise AssertionError("Unexpected API path: " + path)


class CurationGuards(unittest.TestCase):
    def setUp(self):
        self.config, self.files = fixture()
        self.api = FakeAPI(self.config, self.files)
        self.recover = patch.object(c.records, "recover_files",
                                    side_effect=lambda api, tag, ref, release: self.files[tag])
        self.recover.start()
        self.addCleanup(self.recover.stop)

        def verify(api, tag, files, manifest, artifact, reference):
            self.assertEqual(reference, REFERENCE)
            self.assertEqual(artifact, next(r["artifact"] for r in self.config["releases"] if r["tag"] == tag))
            api.verified_archives.append(tag)
            return True

        self.archive = patch.object(c.records, "verify_records", side_effect=verify)
        self.archive.start()
        self.addCleanup(self.archive.stop)
        self.notes = patch.object(p, "notes", side_effect=lambda repo, tag, manifest, run, ref: "Archived records for " + tag)
        self.notes.start()
        self.addCleanup(self.notes.stop)

    def test_all_versions_preflight_and_keep_only_original_runtime_ids(self):
        result = c.curate(self.api, self.config, REFERENCE)
        self.assertTrue(result["passed"])
        deleted = {int(path.rsplit("/", 1)[1]) for method, path, data in self.api.mutations if method == "DELETE"}
        allowed = {a["id"] for plan in self.config["releases"] for a in plan["assets"] if not a["keep"]}
        self.assertEqual(deleted, allowed)
        self.assertEqual(len(deleted), 18)
        for plan in self.config["releases"]:
            actual = self.api.releases[plan["id"]]["assets"]
            self.assertEqual({a["id"] for a in actual}, {a["id"] for a in plan["assets"] if a["keep"]})

    def test_failure_in_last_archive_blocks_every_write(self):
        c.records.verify_records.side_effect = lambda api, tag, *args: False if tag == "v0.1.0" else True
        with self.assertRaisesRegex(ValueError, "archive failed"):
            c.curate(self.api, self.config, REFERENCE)
        self.assertEqual(self.api.mutations, [])

    def test_late_build_failure_blocks_every_write(self):
        self.api.bad_run = self.config["releases"][-1]["run_id"]
        with self.assertRaisesRegex(ValueError, "Build must be successful"):
            c.curate(self.api, self.config, REFERENCE)
        self.assertEqual(self.api.mutations, [])

    def test_partial_previous_cleanup_resumes_then_second_run_is_idempotent(self):
        for plan in self.config["releases"]:
            removed = {a["id"] for a in plan["assets"] if not a["keep"]}
            removed = set(sorted(removed)[:2])
            release = self.api.releases[plan["id"]]
            release["assets"] = [a for a in release["assets"] if a["id"] not in removed]
        result = c.curate(self.api, self.config, REFERENCE)
        self.assertTrue(result["passed"])
        self.assertEqual(sum(m == "DELETE" for m, path, data in self.api.mutations), 12)
        self.api.mutations.clear()
        self.api.verified_archives.clear()
        self.assertTrue(c.curate(self.api, self.config, REFERENCE)["passed"])
        self.assertEqual(self.api.mutations, [])

    def test_unknown_asset_stops_cleanup(self):
        self.api.releases[3]["assets"].append({"id": 999, "name": "other.zip", "size": 1, "digest": "sha256:" + "c" * 64})
        with self.assertRaisesRegex(ValueError, "Unknown or duplicate"):
            c.curate(self.api, self.config, REFERENCE)
        self.assertEqual(self.api.mutations, [])

    def test_replaced_asset_id_stops_cleanup(self):
        self.api.releases[2]["assets"][0]["id"] += 10000
        with self.assertRaisesRegex(ValueError, "replaced or changed"):
            c.curate(self.api, self.config, REFERENCE)
        self.assertEqual(self.api.mutations, [])

    def test_missing_runtime_stops_cleanup(self):
        self.api.releases[3]["assets"] = self.api.releases[3]["assets"][1:]
        with self.assertRaisesRegex(ValueError, "Runnable release asset is missing"):
            c.curate(self.api, self.config, REFERENCE)
        self.assertEqual(self.api.mutations, [])

    def test_changed_tag_or_nonfixed_evidence_reference_stops_cleanup(self):
        self.api.bad_tag = "v0.1.0"
        with self.assertRaisesRegex(ValueError, "different source"):
            c.curate(self.api, self.config, REFERENCE)
        self.assertEqual(self.api.mutations, [])
        with self.assertRaisesRegex(ValueError, "fixed commit SHA"):
            c.curate(self.api, self.config, "main")
        self.assertEqual(self.api.mutations, [])

    def test_plan_can_never_delete_runtime_files(self):
        self.config["releases"][0]["assets"][0]["keep"] = False
        with self.assertRaisesRegex(ValueError, "Only the three runnable"):
            c.curate(self.api, self.config, REFERENCE)
        self.assertEqual(self.api.mutations, [])

    def test_public_repository_is_never_modified(self):
        self.api.private = False
        with self.assertRaisesRegex(ValueError, "existing private repository"):
            c.curate(self.api, self.config, REFERENCE)
        self.assertEqual(self.api.mutations, [])

    def test_changed_latest_release_is_never_modified(self):
        self.api.latest_id = 2
        with self.assertRaisesRegex(ValueError, "Latest release must remain"):
            c.curate(self.api, self.config, REFERENCE)
        self.assertEqual(self.api.mutations, [])

    def test_downloaded_extra_bytes_are_checked_before_deletion(self):
        self.api.corrupt_asset = next(a["id"] for a in self.config["releases"][-1]["assets"] if not a["keep"])
        with self.assertRaisesRegex(ValueError, "download failed verification"):
            c.curate(self.api, self.config, REFERENCE)
        self.assertEqual(self.api.mutations, [])

    def test_concurrent_change_is_caught_before_next_delete_and_report_records_partial_result(self):
        def replace_asset(api):
            api.after_delete = None
            api.releases[1]["assets"][0]["id"] += 10000
        self.api.after_delete = replace_asset
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "result.json"
            with self.assertRaisesRegex(ValueError, "replaced or changed"):
                c.curate(self.api, self.config, REFERENCE, path)
            result = json.loads(path.read_text())
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["releases"][0]["deleted_asset_ids"]), 1)
        self.assertEqual(sum(m == "DELETE" for m, path, data in self.api.mutations), 1)


if __name__ == "__main__":
    unittest.main()
