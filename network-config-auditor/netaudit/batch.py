"""Sequential offline directory audits with independent source provenance."""
from __future__ import annotations

import hashlib
import html
import json
import os
from pathlib import Path
import stat
import tempfile

from . import __version__
from .config_io import ENCODINGS, MAX_CONFIG_BYTES, decode_config_bytes
from .parser import VENDORS
from .pipeline import audit_configuration
from .reports import render
from .rules import SEVERITIES

CONFIG_EXTENSIONS = frozenset((".cfg", ".conf", ".config", ".txt", ""))
LIMITATIONS = "单设备离线静态审计；待复核表示配置证据或解析覆盖需要人工核对。无告警不表示安全，不能证明运行状态、拓扑或完整合规。"


def _linked(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def _linked_component(path: Path) -> bool:
    return any(_linked(component) for component in (path, *path.parents))


def _write_atomic(path: Path, content: str) -> None:
    if _linked_component(path):
        raise ValueError("报告输出不能使用符号链接或目录联接")
    descriptor, temporary = tempfile.mkstemp(prefix=".netaudit-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _error(code: str, message: str) -> dict:
    return {"code": code, "message": message}


def _report_basename(relative: str) -> str:
    return "device-" + hashlib.sha256(relative.encode("utf-8")).hexdigest()


def _discover(root: Path, recursive: bool) -> list[tuple[Path, bool]]:
    """Finish discovery before reading or producing any device reports."""
    selected = []
    if not recursive:
        for path in root.iterdir():
            if path.suffix.lower() in CONFIG_EXTENSIONS and (_linked(path) or not path.is_dir()):
                selected.append((path, _linked(path)))
    else:
        def unreadable(_error):
            raise OSError("无法扫描输入目录") from None
        for directory, subdirectories, filenames in os.walk(root, followlinks=False, onerror=unreadable):
            parent = Path(directory)
            for name in list(subdirectories):
                path = parent / name
                if _linked(path):
                    subdirectories.remove(name)
                    selected.append((path, True))
            for name in filenames:
                path = parent / name
                if path.suffix.lower() in CONFIG_EXTENSIONS:
                    selected.append((path, _linked(path)))
    return sorted(selected, key=lambda item: item[0].relative_to(root).as_posix())


def _read_configuration(path: Path) -> bytes:
    metadata = path.lstat()
    if _linked_component(path) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("输入必须为普通文件，不能使用符号链接或目录联接")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or (metadata.st_dev, metadata.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError("输入文件在读取前发生变化")
        return stream.read(MAX_CONFIG_BYTES + 1)


def _review_required(report: dict) -> bool:
    return bool(report["summary"]["unsupported_lines"] or
                any(finding.get("confidence") == "needs-review" for finding in report["findings"]) or
                any(domain.get("status") == "needs-review" for domain in report.get("architecture", {}).get("domains", [])))


def _html_device(device: dict) -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    source = device["source"]
    provenance = ("<section><h2>配置文件来源</h2><p>路径：" + esc(source["path"]) +
                  "</p><p>SHA-256：" + esc(source["sha256"] or "不可用") +
                  "</p><p>编码：" + esc(source["encoding"] or "未解码") + "</p></section>")
    if device["report"]:
        output = render(device["report"], "html")
        return output.replace("<h1>", provenance + "<h1>", 1)
    return ("<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
            "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; base-uri 'none'; form-action 'none'\">"
            "<title>配置审计失败</title><h1>配置审计失败</h1>" + provenance +
            "<p>" + esc(device["error"]["message"]) + "</p><p>" + esc(LIMITATIONS) + "</p></html>")


def _html_batch(result: dict) -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    summary = result["summary"]
    parts = ["<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width'>",
             "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">",
             "<title>批量配置审计汇总</title><style>body{font:16px/1.7 system-ui;max-width:1100px;margin:32px auto;padding:20px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:8px;text-align:left;overflow-wrap:anywhere}p{overflow-wrap:anywhere}</style>",
             "<h1>批量配置审计汇总</h1><p>" + esc(LIMITATIONS) + "</p>",
             f"<p>配置文件 {summary['total']}；完成 {summary['succeeded']}；失败 {summary['failed']}；待复核 {summary['review_required']}。</p>",
             "<p>严重度：" + esc(" / ".join(f"{name}: {count}" for name, count in summary["severity"].items())) + "</p>",
             "<table><thead><tr><th>配置路径</th><th>状态</th><th>待复核</th><th>编码</th><th>SHA-256</th><th>报告或错误</th></tr></thead><tbody>"]
    for device in result["devices"]:
        source, outputs = device["source"], device.get("outputs", {})
        if outputs:
            detail = f'<a href="{esc(outputs["html"])}">HTML</a> · <a href="{esc(outputs["json"])}">JSON</a>'
            if device["error"]:
                detail += "<p>" + esc(device["error"]["message"]) + "</p>"
        else:
            detail = esc(device["error"]["message"])
        values = (source["path"], "完成" if device["status"] == "ok" else "失败",
                  "需人工核对" if device.get("review_required") else "—", source["encoding"] or "未解码", source["sha256"] or "不可用")
        parts.append("<tr>" + "".join("<td>" + esc(value) + "</td>" for value in values) + "<td>" + detail + "</td></tr>")
    parts.append("</tbody></table>")
    parts.extend("<p>" + esc(error["message"]) + "</p>" for error in result["errors"])
    parts.append("</html>")
    return "".join(parts)


def audit_directory(input_dir: Path, out_dir: Path, *, vendor: str = "auto",
                    encoding: str = "auto", recursive: bool = False,
                    strict: bool = False, fail_on: str | None = None) -> dict:
    """Audit a snapshot of candidate filenames and atomically write local reports.

    No network, stdout or process exit is used. The returned schema is independent
    of the unchanged schema 1.1 reports nested under each device's report field.
    Exit 2 takes precedence for input/output errors and strict coverage failures;
    exit 1 signals a configured finding threshold, and exit 0 means completion.
    """
    result = {"schema_version": "1.0", "tool_version": __version__, "exit_code": 0,
              "summary": {"total": 0, "succeeded": 0, "failed": 0, "review_required": 0,
                          "severity": {severity: 0 for severity in SEVERITIES}},
              "limitations": LIMITATIONS, "devices": [], "errors": []}
    try:
        if vendor not in VENDORS or encoding not in ENCODINGS or (fail_on is not None and fail_on not in SEVERITIES):
            raise ValueError("厂商、编码或严重度选项无效")
        source_root, destination = Path(input_dir).absolute(), Path(out_dir).absolute()
        if _linked_component(source_root) or _linked_component(destination):
            raise ValueError("输入或输出目录不能使用符号链接或目录联接")
        source_root, destination = source_root.resolve(), destination.resolve()
        if not source_root.is_dir():
            raise ValueError("输入必须为存在的目录")
        if destination == source_root or destination.is_relative_to(source_root):
            raise ValueError("输出目录不能位于输入目录中，防止重复扫描或覆盖配置")
        if destination.exists() and not destination.is_dir():
            raise ValueError("输出必须为目录")
        files = _discover(source_root, recursive)
        if not files:
            raise ValueError("输入目录中未找到配置文件")
        output_names = ["batch.json", "batch.html"]
        for path, _ in files:
            base = _report_basename(path.relative_to(source_root).as_posix())
            output_names.extend((base + ".json", base + ".html"))
        for name in output_names:
            target = destination / name
            if _linked_component(target) or (target.exists() and not target.is_file()):
                raise ValueError("报告输出必须为普通文件，不能使用符号链接或目录联接")
        destination.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as exc:
        result["exit_code"] = 2
        result["errors"].append(_error("invalid_directory", str(exc) if isinstance(exc, ValueError) else "无法读取输入目录或创建输出目录"))
        return result

    result["summary"]["total"] = len(files)
    for path, linked in files:
        relative = path.relative_to(source_root).as_posix()
        base = _report_basename(relative)
        device = {"source": {"path": relative, "sha256": None, "encoding": None},
                  "status": "error", "report": None, "error": None, "review_required": False,
                  "outputs": {"json": base + ".json", "html": base + ".html"}}
        try:
            if linked:
                raise ValueError("输入不能使用符号链接或目录联接")
            raw = _read_configuration(path)
            if len(raw) > MAX_CONFIG_BYTES:
                raise ValueError("配置超过 2 MiB 限制")
            device["source"]["sha256"] = hashlib.sha256(raw).hexdigest()
            text, used = decode_config_bytes(raw, encoding)
            device["source"]["encoding"] = used
        except (OSError, ValueError):
            device["error"] = _error("invalid_input", "配置读取或解码失败；请检查文件、编码、控制字符及 2 MiB 限制")
        else:
            try:
                report = audit_configuration(text, vendor)
                device.update(status="ok", report=report, review_required=_review_required(report))
            except Exception:
                # Isolate a device failure without exposing parser/configuration
                # details. BaseException still permits user cancellation.
                device.update(status="error", report=None, review_required=False)
                device["error"] = _error("audit_failed", "配置审计失败；请检查配置格式或单独审计该文件")
        try:
            _write_atomic(destination / device["outputs"]["json"], json.dumps(device, ensure_ascii=False, indent=2) + "\n")
            _write_atomic(destination / device["outputs"]["html"], _html_device(device))
        except (OSError, ValueError):
            device.update(status="error", report=None, outputs={}, error=_error("output_failed", "无法安全写入设备报告"))
        result["devices"].append(device)
        if device["status"] == "error":
            result["summary"]["failed"] += 1
            result["exit_code"] = 2
            continue
        result["summary"]["succeeded"] += 1
        result["summary"]["review_required"] += int(device["review_required"])
        for severity, count in device["report"]["summary"]["severity"].items():
            result["summary"]["severity"][severity] += count
        if strict and device["report"]["summary"]["unsupported_lines"]:
            result["exit_code"] = 2
        if result["exit_code"] != 2 and fail_on and any(SEVERITIES[finding["severity"]] >= SEVERITIES[fail_on] for finding in device["report"]["findings"]):
            result["exit_code"] = 1
    try:
        _write_atomic(destination / "batch.html", _html_batch(result))
    except (OSError, ValueError):
        result["exit_code"] = 2
        result["errors"].append(_error("output_failed", "无法安全写入批量 HTML 汇总报告"))
    try:
        _write_atomic(destination / "batch.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    except (OSError, ValueError):
        result["exit_code"] = 2
        result["errors"].append(_error("output_failed", "无法安全写入批量 JSON 汇总报告"))
    return result
