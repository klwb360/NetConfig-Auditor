"""Move release evidence to fixed Git records before removing redundant assets.

Only the three explicitly inventoried releases are touched. All releases pass
preflight before the first write; reruns resume safely after partial deletion.
"""
import json
import os
from pathlib import Path
import re
import sys
import urllib.parse
import zipfile

import publish_release as p
import release_records as records

TAGS = {"v0.2.1", "v0.2.0", "v0.1.0"}
RUNTIME_SUFFIXES = ("-portable.zip", "-onefile.zip", "-onefile.exe")
RECORD_FILES = {"manifest.json", "SHA256SUMS.txt", "smoke-source.json",
                "smoke-onedir.json", "smoke-onefile.json"}


def positive(value):
    return type(value) is int and value > 0


def validate_config(config, reference):
    p.require(re.fullmatch(r"[a-f0-9]{40}", reference or ""),
              "Evidence reference must be a fixed commit SHA")
    p.require(config.get("repository") == "klwb360/NetAudit", "Wrong curation repository")
    plans = config.get("releases", [])
    p.require(len(plans) == 3 and {r.get("tag") for r in plans} == TAGS,
              "Curation must inventory exactly the three authorized versions")
    release_ids = set()
    asset_ids = set()
    for plan in plans:
        p.require(positive(plan.get("id")) and plan["id"] not in release_ids,
                  "Invalid or duplicate release ID")
        release_ids.add(plan["id"])
        commit = plan.get("source_commit", "")
        p.require(re.fullmatch(r"[a-f0-9]{40}", commit), "Invalid source commit")
        p.require(positive(plan.get("run_id")) and plan.get("run_attempt") == 1,
                  "Invalid build workflow identity")
        artifact = plan.get("artifact", {})
        p.require(positive(artifact.get("id"))
                  and artifact.get("name") == "NetAudit-windows-x64-" + commit
                  and re.fullmatch(r"sha256:[a-f0-9]{64}", artifact.get("digest", "")),
                  "Invalid original build artifact identity")
        version = plan["tag"][1:]
        prefix = f"NetAudit-{version}-windows-x64-{commit[:12]}"
        runtime = {prefix + suffix for suffix in RUNTIME_SUFFIXES}
        expected = runtime | RECORD_FILES | {f"NetAudit-{version}-source-{commit[:12]}.zip"}
        assets = plan.get("assets", [])
        p.require(len(assets) == 9 and {a.get("name") for a in assets} == expected,
                  "Inventory must contain exactly the original nine files")
        for asset in assets:
            p.require(positive(asset.get("id")) and asset["id"] not in asset_ids,
                      "Invalid or duplicate asset ID")
            asset_ids.add(asset["id"])
            p.require(positive(asset.get("size"))
                      and re.fullmatch(r"sha256:[a-f0-9]{64}", asset.get("digest", "")),
                      "Invalid inventoried asset metadata")
            p.require(type(asset.get("keep")) is bool
                      and asset["keep"] == (asset["name"] in runtime),
                      "Only the three runnable distributions may be retained")


def validate_release(release, plan):
    p.require(release and release.get("id") == plan["id"]
              and release.get("tag_name") == plan["tag"]
              and release.get("draft") is False and release.get("prerelease") is False,
              "Release identity or publication state changed")
    original = {a["name"]: a for a in plan["assets"]}
    assets = release.get("assets", [])
    names = [a.get("name") for a in assets]
    p.require(len(names) == len(set(names)) and set(names) <= set(original),
              "Unknown or duplicate live release assets")
    required = {a["name"] for a in plan["assets"] if a["keep"]}
    p.require(required <= set(names), "Runnable release asset is missing")
    for asset in assets:
        pinned = original[asset["name"]]
        p.require(all(asset.get(key) == pinned[key] for key in ("id", "size", "digest")),
                  "Live release asset was replaced or changed: " + asset["name"])
    return {a["name"]: a for a in assets}


def validate_tag(api, plan):
    ref = api.repo("git/ref/tags/" + urllib.parse.quote(plan["tag"], safe=""))
    p.require(ref is not None, "Version tag is missing")
    obj = ref["object"]
    for _ in range(10):
        if obj["type"] != "tag":
            break
        tag = api.repo("git/tags/" + obj["sha"])
        p.require(tag is not None, "Annotated version tag is missing")
        obj = tag["object"]
    p.require(obj["type"] == "commit" and obj["sha"] == plan["source_commit"],
              "Version tag points to different source")


def validate_repository(api, config):
    p.require(api.repository == config["repository"], "Curation API repository mismatch")
    repository = api.repo("")
    p.require(repository and repository.get("private") is True,
              "Expected the existing private repository")
    latest = api.repo("releases/latest")
    plan = next(r for r in config["releases"] if r["tag"] == "v0.2.1")
    p.require(latest and latest.get("id") == plan["id"]
              and latest.get("tag_name") == "v0.2.1",
              "Latest release must remain v0.2.1")


def verify_download(api, asset, expected):
    data = api.repo(f"releases/assets/{asset['id']}", binary=True,
                    accept="application/octet-stream")
    p.require(len(data) == asset["size"] and data == expected
              and "sha256:" + p.digest(data) == asset["digest"],
              "Original release download failed verification: " + asset["name"])


def preflight(api, config, reference, report, save):
    validate_config(config, reference)
    validate_repository(api, config)
    verified = []
    for plan, result in zip(config["releases"], report["releases"]):
        validate_tag(api, plan)
        run = api.repo(f"actions/runs/{plan['run_id']}")
        p.validate_run(run, api.repository, plan["source_commit"])
        p.require(run.get("run_attempt") == plan["run_attempt"], "Build attempt changed")
        release = api.repo(f"releases/{plan['id']}")
        live = validate_release(release, plan)
        files = records.recover_files(api, plan["tag"], reference, release)
        files, manifest = p.verify_files(files, plan["source_commit"], plan["run_id"], plan["run_attempt"])
        p.require(plan["tag"] == "v" + manifest["application_version"], "Version mismatch")
        p.require(set(files) == {a["name"] for a in plan["assets"]}, "Recovered file inventory mismatch")
        for asset in plan["assets"]:
            data = files[asset["name"]]
            p.require(len(data) == asset["size"] and "sha256:" + p.digest(data) == asset["digest"],
                      "Recovered bytes differ from original inventory: " + asset["name"])
        p.require(records.verify_records(api, plan["tag"], files, manifest,
                                         plan["artifact"], reference) is True,
                  "Permanent archive failed verification")
        retained = records.runnable_files(files, manifest)
        p.require(set(retained) == {a["name"] for a in plan["assets"] if a["keep"]},
                  "Runtime selection disagrees with inventory")
        # Recovery reads both runnable ZIPs; still verify all remaining original
        # uploads, including the single EXE and the soon-to-be-removed files.
        for asset in live.values():
            verify_download(api, asset, files[asset["name"]])
        result["preflight"] = "passed"
        result["live_before"] = sorted(a["id"] for a in live.values())
        save()
        verified.append((plan, manifest, files, result))
        print(f"Preflight {plan['tag']}: nine original files and permanent records verified")
    report["phase"] = "all_preflight_passed"
    save()
    return verified


def curate(api, config, reference, report_path=None):
    report = {"repository": config.get("repository"), "evidence_commit": reference,
              "phase": "preflight", "passed": False, "releases": [
                  {"tag": p_["tag"], "release_id": p_["id"], "preflight": "pending",
                   "body_updated": False, "deleted_asset_ids": []}
                  for p_ in config.get("releases", [])]}

    def save():
        if report_path:
            Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                        encoding="utf-8")

    save()
    try:
        verified = preflight(api, config, reference, report, save)
        for plan, manifest, files, result in verified:
            report["phase"] = "curating " + plan["tag"]
            save()
            validate_tag(api, plan)
            release = api.repo(f"releases/{plan['id']}")
            validate_release(release, plan)
            body = p.notes(api.repository, plan["tag"], manifest, plan["run_id"], reference)
            if release.get("body") != body:
                patched = api.repo(f"releases/{plan['id']}", method="PATCH", data={"body": body})
                validate_release(patched, plan)
                p.require(patched.get("body") == body, "Release description update failed")
            result["body_updated"] = True
            save()
            for asset in plan["assets"]:
                if asset["keep"]:
                    continue
                # Always reread immediately before each deletion. The original
                # immutable ID is the only possible DELETE target.
                release = api.repo(f"releases/{plan['id']}")
                live = validate_release(release, plan)
                if asset["name"] not in live:
                    continue
                api.repo(f"releases/assets/{asset['id']}", method="DELETE")
                result["deleted_asset_ids"].append(asset["id"])
                save()
                print(f"Removed archived/redundant asset {plan['tag']}: {asset['name']}")
        report["phase"] = "final_verification"
        save()
        for plan, manifest, files, result in verified:
            validate_tag(api, plan)
            release = api.repo(f"releases/{plan['id']}")
            live = validate_release(release, plan)
            p.require(set(live) == {a["name"] for a in plan["assets"] if a["keep"]},
                      "Release does not contain exactly three runnable uploads")
            for asset in live.values():
                verify_download(api, asset, files[asset["name"]])
            result["retained"] = [{k: asset[k] for k in ("id", "name", "size", "digest")}
                                  for asset in sorted(live.values(), key=lambda a: a["name"])]
            result["verified"] = True
            save()
            print(f"Verified {plan['tag']}: exactly three original runnable assets")
        validate_repository(api, config)
        report["phase"] = "completed"
        report["passed"] = True
        save()
        return report
    except Exception as exc:
        report["error"] = str(exc)
        save()
        raise


def main():
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / ".github/release-curation.json").read_text(encoding="utf-8"))
    reference = os.environ.get("GITHUB_SHA", "")
    p.require(os.environ.get("GITHUB_REPOSITORY") == config["repository"], "Workflow repository mismatch")
    p.require(os.environ.get("GITHUB_REF") == "refs/heads/main", "Curation must run from main")
    api = p.GitHub(config["repository"], os.environ.get("GITHUB_TOKEN", ""))
    report_path = os.environ.get("CURATION_REPORT", "release-curation-verification.json")
    report = curate(api, config, reference, report_path)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## NetAudit Release organization verified\n\n")
            f.write(f"Permanent evidence commit: `{reference}`\n\n")
            f.write("| Version | Retained runnable uploads | Removed this run |\n|---|---:|---:|\n")
            for result in report["releases"]:
                f.write(f"| {result['tag']} | {len(result['retained'])} | {len(result['deleted_asset_ids'])} |\n")
            f.write("\nEvery original file and permanent evidence archive passed before any deletion. "
                    "Retained downloads were verified again after cleanup. Version tags, executable bytes, "
                    "private visibility, and latest v0.2.1 were preserved.\n")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, RuntimeError, zipfile.BadZipFile) as exc:
        print("Release organization stopped: " + str(exc), file=sys.stderr)
        sys.exit(1)
