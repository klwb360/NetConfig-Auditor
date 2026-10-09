"""Publish verified Windows bytes; never rebuild or replace a published asset."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

try:
    from tools import release_records as records
except ModuleNotFoundError as exc:
    if exc.name != "tools":
        raise
    import release_records as records

API = "https://api.github.com"
MAX_DOWNLOAD = 64 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHub:
    def __init__(self, repository, token):
        require(re.fullmatch(r"[\w.-]+/[\w.-]+", repository), "Invalid repository")
        require(bool(token), "GITHUB_TOKEN is required")
        self.repository = repository
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, path, method="GET", data=None, binary=False, upload=False,
                accept="application/vnd.github+json"):
        url = path if path.startswith("https://") else API + path
        parsed = urllib.parse.urlsplit(url)
        host = "uploads.github.com" if upload else "api.github.com"
        require(parsed.scheme == "https" and parsed.netloc == host,
                "Refusing authenticated request outside GitHub API")
        headers = {"Authorization": "Bearer " + self.token,
                   "Accept": accept,
                   "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "NetAudit-release"}
        if data is not None:
            headers["Content-Type"] = "application/octet-stream" if upload else "application/json"
            if not upload:
                data = json.dumps(data).encode()
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            response = self.opener.open(request, timeout=60)
        except urllib.error.HTTPError as exc:
            if binary and exc.code in (301, 302, 303, 307, 308):
                return self.storage_download(exc.headers["Location"])
            if exc.code == 404 and method == "GET" and not binary:
                return None
            # Do not expose signed URLs, response bodies, or credentials in errors.
            raise RuntimeError(f"GitHub API {method} {parsed.path} failed: HTTP {exc.code}") from None
        with response:
            raw = response.read(MAX_DOWNLOAD + 1)
        require(len(raw) <= MAX_DOWNLOAD, "Download exceeds size limit")
        return raw if binary else (json.loads(raw) if raw else None)

    @staticmethod
    def storage_download(url):
        parsed = urllib.parse.urlsplit(url)
        require(parsed.scheme == "https" and parsed.hostname is not None,
                "Artifact redirect must use HTTPS")
        # A fresh opener/request has no Authorization header from the API call.
        request = urllib.request.Request(url, headers={"User-Agent": "NetAudit-release"})
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=60) as response:
                data = response.read(MAX_DOWNLOAD + 1)
        except (urllib.error.URLError, OSError):
            raise RuntimeError("Signed GitHub storage download failed") from None
        require(len(data) <= MAX_DOWNLOAD, "Download exceeds size limit")
        return data

    def repo(self, suffix, **kwargs):
        path = f"/repos/{self.repository}" + ("/" + suffix if suffix else "")
        return self.request(path, **kwargs)


def verify_bundle(archive, commit, run_id, run_attempt, expected_digest):
    require(digest(archive) == expected_digest, "Artifact archive digest mismatch")
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        entries = z.infolist()
        names = [e.filename for e in entries]
        require(len(names) == len(set(names)), "Duplicate archive entries")
        require(all(re.fullmatch(r"[A-Za-z0-9_.-]+", n) for n in names), "Unsafe archive paths")
        require(sum(e.file_size for e in entries) <= MAX_DOWNLOAD, "Archive expands beyond limit")
        require(all(e.file_size <= MAX_DOWNLOAD and not e.is_dir() for e in entries), "Invalid archive entries")
        files = {name: z.read(name) for name in names}  # Reading also verifies ZIP CRCs.
    return verify_files(files, commit, run_id, run_attempt)


def verify_files(files, commit, run_id, run_attempt):
    """Verify all nine original delivery files, including recovered archival bytes."""
    require(all(re.fullmatch(r"[A-Za-z0-9_.-]+", name) for name in files), "Unsafe delivery paths")
    require(all(isinstance(data, bytes) for data in files.values()), "Delivery files must be bytes")
    require(sum(len(data) for data in files.values()) <= MAX_DOWNLOAD, "Delivery files exceed size limit")
    manifest = json.loads(files["manifest.json"])
    version = manifest["application_version"]
    require(re.fullmatch(r"\d+\.\d+\.\d+", version), "Invalid application version")
    has_simulator = tuple(map(int, version.split("."))) >= (1, 0, 0)
    prefix = f"NetAudit-{version}-windows-x64-{commit[:12]}"
    packages = {prefix + "-portable.zip", prefix + "-onefile.zip", prefix + "-onefile.exe",
                f"NetAudit-{version}-source-{commit[:12]}.zip"}
    expected = packages | {"manifest.json", "SHA256SUMS.txt", "smoke-source.json",
                           "smoke-onedir.json", "smoke-onefile.json"}
    require(set(files) == expected, "Artifact must contain exactly the nine delivery files")
    sums = {}
    for line in files["SHA256SUMS.txt"].decode().splitlines():
        match = re.fullmatch(r"([a-f0-9]{64})  ([A-Za-z0-9_.-]+)", line)
        require(match is not None, "Invalid checksum line")
        sha, name = match.groups()
        require(name not in sums, "Duplicate checksum")
        sums[name] = sha
    require(set(sums) == expected - {"SHA256SUMS.txt"}, "Checksum file list mismatch")
    require(all(digest(files[n]) == sha for n, sha in sums.items()), "File checksum mismatch")
    require(manifest["application"] == "NetAudit" and manifest["source"]["commit"] == commit
            and manifest["source"]["dirty"] is False, "Manifest source mismatch")
    env = manifest["environment"]
    require(env["github_run_id"] == str(run_id) and env["github_run_attempt"] == str(run_attempt),
            "Manifest workflow identity mismatch")
    require(env["architecture"] == "AMD64" and env["runner_os"] == "Windows", "Not a Windows x64 build")
    items = manifest["artifacts"]
    require(len(items) == 4 and {item["file"] for item in items} == packages, "Manifest package list mismatch")
    for item in items:
        data = files[item["file"]]
        require(item["sha256"] == digest(data) and item["size_bytes"] == len(data), "Package metadata mismatch")
    counts = (("source", 9), ("onedir", 8), ("onefile", 8)) if version == "0.1.0" else (("source", 10), ("onedir", 9), ("onefile", 9))
    for mode, count in counts:
        report = json.loads(files[f"smoke-{mode}.json"])
        require(report == manifest["verification"][mode], "Standalone report differs from manifest")
        require(report["passed"] is True and report["mode"] == mode and len(report["checks"]) >= count,
                "Incomplete acceptance report")
        for check in report["checks"]:
            require(check["status"] == "passed", "Acceptance check did not pass")
            if "shutdown" in check:
                shutdown = check["shutdown"]
                require(shutdown["remaining_pids"] == [] and shutdown["forced_cleanup"] is False
                        and shutdown["port_closed"] is True, "Unclean server shutdown")
        if has_simulator:
            cli_checks = [c for c in report["checks"] if "simulator_cli" in c]
            expected_cli = {"plan_ready": True, "successful_transaction": True, "command_file": True,
                "repeated_arguments": True, "crlf_preserved": True, "failed_batch_exit": 2,
                "failed_output_unchanged": True, "input_unchanged": True, "no_automatic_audit": True,
                "unicode_and_spaces_in_paths": True}
            require(len(cli_checks) >= 2, "Incomplete simulator CLI acceptance")
            for check in cli_checks:
                require(all(type(check["simulator_cli"].get(key)) is type(value)
                            and check["simulator_cli"].get(key) == value for key, value in expected_cli.items()),
                        "Incomplete simulator CLI acceptance")
            # Every direct/BAT server path (fallback, no-argument, read-only)
            # must load the simulator UI and exercise actual API transitions.
            web_checks = [c for c in report["checks"] if "resources_sha256" in c]
            require(len(web_checks) >= 6, "Incomplete simulator server-path acceptance")
            expected_simulation = {"vendors": ["cisco", "huawei", "h3c", "ruijie"],
                "transaction": "committed", "missing_vlan_rollback": True, "unknown_command_rollback": True,
                "original_text_preserved": True, "chinese_goal": "ready", "plan_replay_matches": True,
                "automatic_audit": False, "audit_after_simulation": "explicit",
                "candidate_exports": ["json", "md", "html"]}
            for check in web_checks:
                resources = check["resources_sha256"]
                require(set(resources) == {"index.html", "style.css", "app.js", "simulator.js"}
                        and all(isinstance(sha, str) and re.fullmatch(r"[a-f0-9]{64}", sha)
                                for sha in resources.values()), "Incomplete simulator web resources")
                simulation = check.get("simulation", {})
                require(all(type(simulation.get(key)) is type(value) and simulation.get(key) == value
                            for key, value in expected_simulation.items()), "Incomplete simulator state acceptance")
                require("shutdown" in check, "Simulator server shutdown was not verified")
    return files, manifest


def validate_run(run, repository, commit):
    require(run and run["status"] == "completed" and run["conclusion"] == "success", "Build must be successful")
    require(run["head_sha"] == commit and run["head_branch"] == "main", "Wrong build source")
    require(run["repository"]["full_name"] == repository and run["head_repository"]["full_name"] == repository,
            "Build belongs to another repository")
    require(run["path"] == ".github/workflows/netaudit-windows.yml"
            and run["event"] in ("push", "workflow_dispatch"), "Wrong build workflow or event")


def notes(repository, tag, manifest, run_id, records_commit="main"):
    version = manifest["application_version"]
    version_parts = tuple(map(int, version.split(".")))
    has_rgos_remediation = version_parts >= (0, 2, 2)
    has_simulator = version_parts >= (1, 0, 0)
    vendor_choices = "Cisco、华为、H3C 或锐捷 RGOS" if has_rgos_remediation else "Cisco、华为或 H3C"
    vendor_coverage = "四厂商" if has_rgos_remediation else "三厂商"
    commit = manifest["source"]["commit"]
    portable = next(a["file"] for a in manifest["artifacts"] if a["file"].endswith("-portable.zip"))
    base = f"https://github.com/{repository}"
    archive = f"{base}/tree/{records_commit}/docs/releases/{tag}"
    rows = "\n".join(f"| `{a['file']}` | `{a['sha256']}` |" for a in manifest["artifacts"]
                     if a["file"].endswith(("-portable.zip", "-onefile.zip", "-onefile.exe")))
    env = manifest["environment"]
    check_count = sum(len(r["checks"]) for r in manifest["verification"].values())
    features = "" if version == "0.1.0" else """
### 本版升级

配置解析 → VLAN / STP / OSPF / ACL / NAT / Management Plane 架构检查 → 安全规则 → CVE / KEV 情报 → 可选 AI 解释与整改建议 → Markdown / HTML / JSON 报告。

- 新增 STP / OSPF 结构化解析与保守检查，报告显示各域覆盖、证据和确认程度。
- 随包提供 CISA 官方 KEV 离线快照及 CC0 来源说明；CVE 匹配需要精确设备 CPE 与导入的 NVD CVE 2.0 JSON。产品/版本不明时明确提示待核对，KEV 收录不代表设备已被入侵。
- 可显式启用本机 Ollama 模型解释结构化发现；常规便携审计无需模型。未启用或模型不可用时仍可查看规则建议与导出。本轮验证的是本机 HTTP 协议适配器，尚未连接真实 Ollama 模型。
- 本轮 NVD 适用性检查使用标明为合成的样例；本环境官方 NVD API 访问被网络代理拒绝。正式使用时需导入官方产品数据并核对来源，不能把测试样例作为实际设备漏洞证明。
- 网页保留文件导入、厂商选择、示例、严重度筛选和三种导出，并增加流程、架构、情报和 AI 状态。

"""
    ui_features = "" if version_parts < (0, 2, 1) else """
### 界面与使用体验

- 顶部概览与简短使用提示，左侧配置输入，右侧按安全发现、网络架构、漏洞情报、AI 建议、报告与清单、使用帮助分区。
- 保留可见的审计操作与状态，页签支持键盘切换，窄屏自动堆叠。
- 修改配置或情报/模型设置后需重新审计；旧报告不可继续导出，进行中的旧输入结果也不会覆盖当前状态。

"""
    remediation_features = "" if not has_rgos_remediation else """
### 配置解析与整改修复

- 可将单个配置文件拖入文本区域，或使用导入按钮，按内容自动识别厂商；无法可靠识别时提示手动选择，点击“开始审计”才运行审计。
- 新增锐捷 RGOS 识别与 `vlan range` 批量 VLAN 定义，支持单编号 VTY 与全局 `no spanning-tree` 解析。
- 同一缺失 VLAN 按 VLAN ID 合并，列出全部相关端口与引用角色；等价的同类风险合并展示，保留完整配置证据、严重度、确认程度和发生次数，不混合不同缺失 VLAN 或不同风险等级。
- 提供只读核查命令、已知参数的整改脚本，以及需填写参数或人工确认的候选模板；显示设备版本、业务、认证与备用管理路径等执行前提。命令保留完整模式进入与退出，工具不连接设备或自动执行整改。

"""
    theme_features = "" if version_parts < (0, 2, 3) else """
### 主题切换与重复风险折叠

- 顶部可切换“明亮”“暗黑”或“跟随系统”，浏览器记住主题偏好；默认跟随系统配色。配置内容不会随主题偏好保存。
- 安全发现按规则、严重度、分类、确认程度与标题集中为可展开的项目，显示项数与涉及处数；重复项目默认折叠，单项单处直接显示。展开后查看每项对象、证据和整改建议，也可一键展开或收起；不同 VLAN 等独立发现保留各自建议命令。
- 折叠仅调整网页展示，严重度筛选、审计统计和 JSON / Markdown / HTML 完整报告仍保留原有发现与证据。

"""
    simulator_features = "" if not has_simulator else """
### 配置模拟与学习练习

- 导入完整备份，输入中文目标获取命令草案，也可逐条或批量输入模拟命令；支持 Cisco、华为、H3C 和锐捷 RGOS 已建模的配置语法。
- 按配置视图、已有对象和依赖关系判断当前能否运行，逐条用简短语言解释结果与下一步；创建 VLAN、接口模式和 VLAN 引用等变更可查看候选状态及脱敏差异。
- 不满足前置条件、参数错误或未知命令会使整批配置与视图原子回滚；导入的未修改配置按原文保留，可重新开始练习或导出候选配置。
- 中文目标生成先经过同一模拟引擎校验，缺参数时给出问题，不猜测业务地址；本版采用本地有限目标模板，无需 AI 模型。
- 模拟不会自动审计。练习后可自行审计候选配置，继续使用原有安全规则、CVE / KEV、可选 AI 和三种报告导出。
- 这是离线配置状态模拟器，不是完整设备仿真；不模拟数据包转发、STP / OSPF 收敛、真实链路或业务中断。可运行表示本工具支持且前提满足，不保证实机固件接受。工具不连接设备执行命令。
- 候选配置及备份导出会保留原有凭据，请按敏感文件保管；页面命令结果与差异脱敏，浏览器不持久保存配置。

"""
    start_steps = (f"3. 浏览器打开后导入 UTF-8 备份，确认 {vendor_choices}，点击“载入模拟”。\n"
                   "4. 输入中文目标并点击“生成命令草案”→“将草案放入命令区”；也可在模拟命令行直接输入命令。\n"
                   "5. 点击“预览运行”，阅读结果、理由与差异，再点击“应用本次预览”；按需撤销、重置或导出模拟配置。\n"
                   "6. 如需审查，点击“审查当前模拟配置”，再导出 JSON、Markdown 或 HTML 报告。未应用的预览不参与导出和审查。") if has_simulator else (
                   f"3. 浏览器打开后导入 UTF-8 配置，选择 {vendor_choices}，点击“开始审计”；也可先载入示例。\n"
                   "4. 查看发现与严重度，导出 JSON、Markdown 或 HTML 报告。")
    return f"""下载后即可使用的 Windows x64 便携版，配置处理在本机完成。

**推荐下载：[便携 ZIP]({base}/releases/download/{tag}/{portable})**（下方 Assets 中名称以 `-portable.zip` 结尾的文件）。

1. 使用有权访问本私人仓库的 GitHub 账号下载便携 ZIP。
2. 解压一次，双击文件夹中的 `Start-NetAudit.bat` 或 `NetAudit.exe`。
{start_steps}

关闭：回到启动窗口按 Ctrl+C；关闭浏览器标签页不会停止服务。迁移：复制整个文件夹（包括 `_internal`）到另一台电脑。EXE 自带 Python 运行库，普通使用设计为无需安装 Python、无需管理员权限。端口占用时以启动窗口显示的实际地址为准。

`-onefile.zip` 提供单 EXE 与配套说明、示例、许可证和源码；`-onefile.exe` 可独立启动。再次分发仍需保留 GPL-3.0-only 许可证、归属说明与对应源码。普通用户无需下载 GitHub 自动生成的 “Source code”。

{simulator_features}{features}{ui_features}{remediation_features}{theme_features}

### 验证与来源

- 源码提交：[`{commit}`]({base}/commit/{commit})；标签指向该构建提交。
- [实际 Windows 构建与回归测试]({base}/actions/runs/{run_id})：{env['os']} / {env['architecture']}，Python {env['python']}，PyInstaller {manifest['build_dependencies']['pyinstaller']}。
- 源码、onedir、onefile 共 {check_count} 项真实进程检查通过：中文及空格路径、端口回退、完整网页资源、{vendor_coverage}及三种报告、退出码、无暂停与服务清理。EXE 子进程 PATH 排除 Python；构建主机仍安装构建 Python。
- 尚未人工验收资源管理器双击及默认浏览器界面、独立未安装 Python 的电脑、普通非管理员账户，也未实测 Windows 10/11 或其他架构。详细范围见[永久归档的构建与验收记录]({archive})中的 `manifest.json` 和三份 `smoke-*.json`。
- 发布复用已验收原始文件，下载回验通过后才公开 Release；没有重新构建或替换 EXE。

### 文件校验

下方仅提供三个可运行附件。[校验文件、构建清单和三份验收记录]({archive})永久保存在仓库 `docs/releases/{tag}/`，无需普通用户下载。原始 `SHA256SUMS.txt` 保留完整九文件交付时其余八个文件的校验值。Windows PowerShell 示例：`Get-FileHash .\\{portable} -Algorithm SHA256`。

| 文件 | SHA-256 |
|---|---|
{rows}

版本 {version}；两个分发 ZIP 内保留对应源码 ZIP、许可证与来源说明。也可从固定[版本标签]({base}/tree/{tag})查阅源码。
"""


def ensure_tag(api, tag, commit, allow_create=True):
    ref = api.repo("git/ref/tags/" + urllib.parse.quote(tag, safe=""))
    if ref:
        obj = ref["object"]
        for _ in range(10):
            if obj["type"] != "tag":
                break
            obj = api.repo("git/tags/" + obj["sha"])["object"]
        require(obj["type"] == "commit" and obj["sha"] == commit, "Existing version tag points to different source")
    else:
        require(allow_create, "Existing version tag is required for archival re-verification")
        api.repo("git/refs", method="POST", data={"ref": "refs/tags/" + tag, "sha": commit})


def runtime_names(tag, commit):
    prefix = f"NetAudit-{tag[1:]}-windows-x64-{commit[:12]}"
    return {prefix + "-portable.zip", prefix + "-onefile.zip", prefix + "-onefile.exe"}


def publish(api, tag, commit, files, body):
    require(set(files) == runtime_names(tag, commit), "Publisher accepts exactly the three runtime files")
    ensure_tag(api, tag, commit)
    releases = api.repo("releases?per_page=100")
    matches = [r for r in releases if r["tag_name"] == tag]
    require(len(matches) <= 1, "Duplicate version releases")
    release = matches[0] if matches else api.repo("releases", method="POST", data={
        "tag_name": tag, "target_commitish": commit, "name": f"NetAudit {tag[1:]} · Windows x64 便携版",
        "body": body, "draft": True, "prerelease": False})
    assets = {a["name"]: a for a in release["assets"]}
    require(len(assets) == len(release["assets"]), "Duplicate release assets")
    require(release["draft"] or not (set(assets) - set(files)),
            "Published release contains additional assets; explicit archival migration is required")
    require(set(assets) <= set(files), "Unexpected release assets")
    require(release["draft"] or set(assets) == set(files), "Published release is incomplete; refusing mutation")
    for name, data in sorted(files.items()):
        if name not in assets:
            base = release["upload_url"].split("{", 1)[0]
            expected = f"https://uploads.github.com/repos/{api.repository}/releases/{release['id']}/assets"
            require(base == expected, "Unexpected upload endpoint")
            assets[name] = api.request(base + "?name=" + urllib.parse.quote(name),
                                      method="POST", data=data, upload=True)
        asset = assets[name]
        downloaded = api.repo(f"releases/assets/{asset['id']}", binary=True,
                              accept="application/octet-stream")
        require(asset["size"] == len(data) and digest(downloaded) == digest(data), "Uploaded asset verification failed: " + name)
        print(f"Verified {name}: {digest(data)}")
    if release["draft"]:
        # The version stays a draft if any upload or verification above fails.
        release = api.repo(f"releases/{release['id']}", method="PATCH", data={
            "draft": False, "prerelease": False, "body": body, "make_latest": "true"})
    require(release["draft"] is False, "Release did not become downloadable")
    return release["html_url"]


def prepare_delivery(api, config, tag, commit, run_id):
    """Verify the original nine files and their permanent records before publication."""
    run = api.repo(f"actions/runs/{run_id}")
    validate_run(run, api.repository, commit)
    artifacts = api.repo(f"actions/runs/{run_id}/artifacts?per_page=100")["artifacts"]
    matches = [a for a in artifacts if a["name"] == "NetAudit-windows-x64-" + commit]
    require(len(matches) <= 1, "Duplicate verified build artifacts")
    artifact = matches[0] if matches else None
    from_records = artifact is None or artifact["expired"]
    if from_records:
        # An expired artifact can only re-verify an already published curated release.
        # The fixed archive commit identifies which records were actually read.
        reference = api.repo("git/ref/heads/main")["object"]["sha"]
        require(re.fullmatch(r"[a-f0-9]{40}", reference), "Invalid records reference")
        record, _ = records.load_records(api, tag, reference)
        require(record["repository"] == api.repository and record["tag"] == tag
                and record["source_commit"] == commit and record["run_id"] == str(run_id)
                and record["run_attempt"] == run["run_attempt"], "Archived build identity mismatch")
        archived_artifact = record["artifact"]
        require(archived_artifact["name"] == "NetAudit-windows-x64-" + commit,
                "Archived artifact name mismatch")
        if artifact:
            require(all(artifact[key] == archived_artifact[key] for key in ("id", "name", "digest")),
                    "Archived artifact differs from GitHub build identity")
        artifact = archived_artifact
        release = api.repo("releases/tags/" + urllib.parse.quote(tag, safe=""))
        require(release and release["draft"] is False, "Expired build requires an existing published release")
        names = [asset["name"] for asset in release["assets"]]
        require(len(names) == len(set(names)) and set(names) == runtime_names(tag, commit),
                "Expired build requires exactly three existing runtime assets")
        ensure_tag(api, tag, commit, allow_create=False)
    expected_digest = artifact.get("digest", "").removeprefix("sha256:")
    require(re.fullmatch(r"[a-f0-9]{64}", expected_digest), "GitHub artifact digest unavailable")
    if run_id == config["run_id"]:
        require(artifact["id"] == config["artifact_id"] and expected_digest == config["artifact_sha256"],
                "Initial acceptance artifact identity mismatch")
    if from_records:
        files = records.recover_files(api, tag, reference, release)
        files, manifest = verify_files(files, commit, run_id, run["run_attempt"])
        print("Verified original nine delivery files from permanent records and runtime packages; "
              "the expired outer artifact archive was not downloaded or re-verified.")
    else:
        archive = api.repo(f"actions/artifacts/{artifact['id']}/zip", binary=True)
        files, manifest = verify_bundle(archive, commit, run_id, run["run_attempt"], expected_digest)
    require(tag == "v" + manifest["application_version"], "Tag must match the built application version")
    records_commit = records.ensure_records(api, tag, files, manifest, artifact)
    require(re.fullmatch(r"[a-f0-9]{40}", records_commit), "Invalid permanent records commit")
    runtime = records.runnable_files(files, manifest)
    require(set(runtime) == runtime_names(tag, commit), "Permanent records runtime list mismatch")
    return runtime, manifest, records_commit, from_records


def main():
    config = json.loads((Path(__file__).resolve().parents[1] / ".github/release-source.json").read_text())
    repository = os.environ.get("GITHUB_REPOSITORY", config["repository"])
    require(repository == config["repository"], "Publisher repository mismatch")
    tag = os.environ.get("RELEASE_TAG") or config["tag"]
    commit = os.environ.get("RELEASE_SOURCE_COMMIT") or config["source_commit"]
    run_id = os.environ.get("RELEASE_RUN_ID") or config["run_id"]
    require(re.fullmatch(r"v\d+\.\d+\.\d+", tag) and re.fullmatch(r"[a-f0-9]{40}", commit)
            and re.fullmatch(r"\d+", run_id), "Invalid release inputs")
    api = GitHub(repository, os.environ.get("GITHUB_TOKEN", ""))
    require(api.repo("")["private"] is True, "Expected the existing private repository")
    runtime, manifest, records_commit, from_records = prepare_delivery(api, config, tag, commit, run_id)
    url = publish(api, tag, commit, runtime, notes(repository, tag, manifest, run_id, records_commit))
    print("Release: " + url)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"## Published NetAudit\n\n[Download {tag}]({url})\n\nSource: `{commit}`\n\n")
            f.write("All nine original delivery files passed the complete checksum, source and acceptance guards; "
                    "their records are permanently archived. All three runtime release assets were "
                    "downloaded and SHA-256 verified.\n\n")
            f.write(f"[Permanent verification records](https://github.com/{repository}/tree/{records_commit}/docs/releases/{tag})\n")
            if from_records:
                f.write("\nExpired outer build artifact was not downloaded or re-verified; "
                        "this existing release was reconstructed and verified from its permanent records "
                        "and original runtime packages.\n")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, RuntimeError, zipfile.BadZipFile) as exc:
        print("Release stopped: " + str(exc), file=sys.stderr)
        sys.exit(1)
