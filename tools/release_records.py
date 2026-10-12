"""Preserve the original delivery records while Releases expose runnable files."""
import base64
import hashlib
import io
import json
import re
import urllib.parse
import zipfile

TEXT_NAMES = ("SHA256SUMS.txt", "manifest.json", "smoke-source.json",
              "smoke-onedir.json", "smoke-onefile.json")
MAX_SOURCE = 64 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(tag, commit):
    require(re.fullmatch(r"v\d+\.\d+\.\d+", tag), "Invalid archive tag")
    require(re.fullmatch(r"[a-f0-9]{40}", commit), "Invalid archive source")
    prefix = f"NetAudit-{tag[1:]}-windows-x64-{commit[:12]}"
    return sorted(prefix + suffix for suffix in ("-portable.zip", "-onefile.zip", "-onefile.exe"))


def runnable_files(files, manifest):
    tag = "v" + manifest["application_version"]
    names = identity(tag, manifest["source"]["commit"])
    require(all(name in files for name in names), "Missing runnable delivery file")
    return {name: files[name] for name in names}


def source_bytes(archive, member, expected_size):
    require(0 < expected_size <= MAX_SOURCE, "Invalid embedded source size")
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        matches = [entry for entry in z.infolist() if entry.filename == member]
        require(len(matches) == 1 and not matches[0].is_dir()
                and matches[0].file_size == expected_size, "Embedded source entry mismatch")
        return z.read(matches[0])  # Also checks this entry's ZIP CRC.


def make_record(repository, tag, files, manifest, artifact):
    commit = manifest["source"]["commit"]
    require(tag == "v" + manifest["application_version"], "Archive version mismatch")
    names = identity(tag, commit)
    source_name = f"NetAudit-{tag[1:]}-source-{commit[:12]}.zip"
    require(set(files) == set(names) | set(TEXT_NAMES) | {source_name},
            "Archive must describe exactly nine original files")
    require(re.fullmatch(r"[\w.-]+/[\w.-]+", repository), "Invalid archive repository")
    require(isinstance(artifact["id"], int) and artifact["id"] > 0
            and artifact["name"] == "NetAudit-windows-x64-" + commit
            and re.fullmatch(r"sha256:[a-f0-9]{64}", artifact["digest"]),
            "Invalid archived build artifact identity")
    locations = [{"archive": next(n for n in names if n.endswith(suffix)),
                  "member": root + source_name}
                 for suffix, root in (("-portable.zip", "NetAudit/"),
                                      ("-onefile.zip", "NetAudit-onefile/"))]
    for item in locations:
        require(source_bytes(files[item["archive"]], item["member"], len(files[source_name]))
                == files[source_name], "Runtime ZIP does not preserve the original source")
    return {"schema_version": 1, "repository": repository, "tag": tag,
            "source_commit": commit, "run_id": str(manifest["environment"]["github_run_id"]),
            "run_attempt": int(manifest["environment"]["github_run_attempt"]),
            "artifact": {key: artifact[key] for key in ("id", "name", "digest")},
            "runtime_names": names, "source_name": source_name, "source_locations": locations,
            "files": {name: {"size_bytes": len(data), "sha256": digest(data)}
                      for name, data in sorted(files.items())}}


def encode_record(record):
    return (json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def archive_readme(record):
    base = "https://github.com/" + record["repository"]
    tag = record["tag"]
    rows = "\n".join(f"| `{name}` | `{record['files'][name]['sha256']}` |"
                     for name in record["runtime_names"])
    return f"""# {tag} 构建与验收资料

[下载运行文件]({base}/releases/tag/{tag}) · [固定版本源码]({base}/tree/{tag})

Release 提供便携 ZIP、单 EXE 配套 ZIP、独立 EXE。两个运行 ZIP 内都包含完整对应源码、许可证和归属说明；独立源码 ZIP 的原始字节可从包内取得，具体路径与 SHA-256 见 [record.json](record.json)。

| 原始资料 | 用途 |
|---|---|
| [SHA256SUMS.txt](SHA256SUMS.txt) | 原始交付中其余八个文件的校验值；仍包含独立源码包与工程记录，并非仅列出当前三个下载附件 |
| [manifest.json](manifest.json) | 源码提交、构建环境、固定依赖、文件信息与验收结果 |
| [smoke-source.json](smoke-source.json) | 源码运行方式的实际进程验收 |
| [smoke-onedir.json](smoke-onedir.json) | 便携文件夹 EXE 的实际进程验收 |
| [smoke-onefile.json](smoke-onefile.json) | 单文件 EXE 的实际进程验收 |

这五份文件按原始字节永久保留。[record.json](record.json) 记录完整九文件的大小、SHA-256、来源构建与源码恢复位置。构建产物依旧包含九份交付文件，Release 下载区只展示三个运行文件。

源码提交：`{record['source_commit']}`。原 [Windows 构建]({base}/actions/runs/{record['run_id']}) 的验收范围以清单和报告为准；整理附件不新增 Windows 验收，也不重新构建、替换 EXE 或移动版本标签。Actions 原始产物有保留期限，本目录不依赖它长期保存。

| 运行文件 | SHA-256 |
|---|---|
{rows}
""".encode()


def archive_files(repository, tag, files, manifest, artifact):
    record = make_record(repository, tag, files, manifest, artifact)
    base = "docs/releases/" + tag + "/"
    result = {base + name: files[name] for name in TEXT_NAMES}
    result[base + "record.json"] = encode_record(record)
    result[base + "README.md"] = archive_readme(record)
    return result


def read_file(api, path, reference):
    require(re.fullmatch(r"[a-f0-9]{40}", reference), "Archive reference must be an immutable commit")
    item = api.repo("contents/" + urllib.parse.quote(path, safe="/") + "?ref=" + reference)
    require(item is not None and item.get("type") == "file"
            and item.get("encoding") == "base64", "Archived file unavailable: " + path)
    raw = base64.b64decode(item["content"], validate=False)
    require(len(raw) == item["size"], "Archived file size mismatch")
    return raw


def load_records(api, tag, reference):
    require(re.fullmatch(r"v\d+\.\d+\.\d+", tag), "Invalid archive tag")
    base = "docs/releases/" + tag + "/"
    record = json.loads(read_file(api, base + "record.json", reference))
    require(record["schema_version"] == 1 and record["repository"] == api.repository
            and record["tag"] == tag, "Archived record identity mismatch")
    data = {name: read_file(api, base + name, reference) for name in TEXT_NAMES}
    for name, raw in data.items():
        require(record["files"][name] == {"size_bytes": len(raw), "sha256": digest(raw)},
                "Archived verification file mismatch: " + name)
    return record, data


def verify_records(api, tag, files, manifest, artifact, reference):
    actual, text = load_records(api, tag, reference)
    expected = make_record(api.repository, tag, files, manifest, artifact)
    require(actual == expected, "Archived delivery identity mismatch")
    require(all(text[name] == files[name] for name in TEXT_NAMES),
            "Archived original verification bytes mismatch")
    return True


def ensure_records(api, tag, files, manifest, artifact):
    """Create missing records atomically; existing version records are immutable."""
    ref = api.repo("git/ref/heads/main")["object"]["sha"]
    path = "docs/releases/" + tag + "/record.json"
    if api.repo("contents/" + path + "?ref=" + ref) is not None:
        verify_records(api, tag, files, manifest, artifact, ref)
        return ref
    entries = archive_files(api.repository, tag, files, manifest, artifact)
    for name in entries:
        require(api.repo("contents/" + name + "?ref=" + ref) is None,
                "Refusing to overwrite a partial version archive")
    base = api.repo("git/commits/" + ref)["tree"]["sha"]
    tree = []
    for name, raw in sorted(entries.items()):
        blob = api.repo("git/blobs", method="POST", data={
            "content": base64.b64encode(raw).decode(), "encoding": "base64"})
        tree.append({"path": name, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    tree_sha = api.repo("git/trees", method="POST", data={"base_tree": base, "tree": tree})["sha"]
    commit = api.repo("git/commits", method="POST", data={
        "message": f"Archive original {tag} build and acceptance records [skip ci]",
        "tree": tree_sha, "parents": [ref]})["sha"]
    # A non-fast-forward update fails instead of replacing a concurrent user commit.
    api.repo("git/refs/heads/main", method="PATCH", data={"sha": commit, "force": False})
    verify_records(api, tag, files, manifest, artifact, commit)
    return commit


def recover_files(api, tag, reference, release):
    """Reconstruct original delivery bytes without relying on expiring artifacts."""
    record, files = load_records(api, tag, reference)
    names = identity(tag, record["source_commit"])
    require(record["runtime_names"] == names and release["tag_name"] == tag
            and release["draft"] is False, "Wrong archived release identity")
    assets = {item["name"]: item for item in release["assets"]}
    require(len(assets) == len(release["assets"]) and all(name in assets for name in names),
            "Missing or duplicate runnable release asset")
    for name in names:
        item = assets[name]
        expected = record["files"][name]
        require(item["size"] == expected["size_bytes"], "Runnable asset size changed")
        raw = api.repo(f"releases/assets/{item['id']}", binary=True,
                       accept="application/octet-stream")
        require(len(raw) == expected["size_bytes"] and digest(raw) == expected["sha256"],
                "Runnable asset bytes changed: " + name)
        files[name] = raw
    source_name = f"NetAudit-{tag[1:]}-source-{record['source_commit'][:12]}.zip"
    require(record["source_name"] == source_name, "Archived source filename mismatch")
    expected = record["files"][source_name]
    locations = [{"archive": next(n for n in names if n.endswith(suffix)),
                  "member": root + source_name}
                 for suffix, root in (("-portable.zip", "NetAudit/"),
                                      ("-onefile.zip", "NetAudit-onefile/"))]
    require(record["source_locations"] == locations, "Archived source location mismatch")
    for item in locations:
        raw = source_bytes(files[item["archive"]], item["member"], expected["size_bytes"])
        require(digest(raw) == expected["sha256"], "Embedded original source bytes changed")
        files[source_name] = raw
    return files
