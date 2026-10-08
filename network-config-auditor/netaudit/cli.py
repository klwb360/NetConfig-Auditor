from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from . import __version__
from .parser import MAX_BYTES, VENDORS
from .reports import render
from .rules import SEVERITIES
from .pipeline import audit_configuration
from .intelligence import load_intelligence_file

MAX_INTELLIGENCE_BYTES = 16 * 1024 * 1024


def _load_json(path, label, limit=MAX_INTELLIGENCE_BYTES):
    if path is None:
        return None
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"{label} 文件超过大小限制")
    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ValueError(f"{label} 必须为 UTF-8 JSON 文件") from None
    if not isinstance(value, dict):
        raise ValueError(f"{label} 必须为 JSON 对象")
    return value


def _write_private(path: Path, text: str):
    # Atomic output, mode 0600 on platforms supporting POSIX permissions.
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".netaudit-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(text)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # A double-click has no arguments. Also allow the convenient
    # `NetAudit.exe --no-browser` form without changing audit arguments.
    if not argv or argv[0] in ("--no-browser", "--port") or argv[0].startswith("--port="):
        argv.insert(0, "serve")
    p = argparse.ArgumentParser(description="华为/Cisco/H3C/锐捷 RGOS 离线网络配置审计；无参数时打开本地网页")
    p.add_argument("--version", action="version", version=f"NetAudit {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("audit", help="审计配置文件或标准输入")
    a.add_argument("input", help="UTF-8 配置文件；- 表示标准输入")
    a.add_argument("--vendor", choices=VENDORS, default="auto")
    a.add_argument("--format", choices=("json", "md", "html"), default="md")
    a.add_argument("--out", type=Path)
    a.add_argument("--fail-on", choices=tuple(SEVERITIES), help="达到此严重度时退出码为 1")
    a.add_argument("--strict", action="store_true", help="存在未建模行则退出码为 2（仍输出报告）")
    a.add_argument("--asset-info", type=Path, help="设备 CPE / 候选 CVE 信息 JSON 文件")
    a.add_argument("--kev-file", type=Path, help="本地 CISA KEV JSON；默认使用随包快照")
    a.add_argument("--nvd-file", type=Path, help="本地 NVD CVE 2.0 JSON 子集，最大 16 MiB")
    a.add_argument("--ai-model", help="显式启用本机 Ollama 模型进行解释")
    a.add_argument("--ai-endpoint", default="http://127.0.0.1:11434", help="Ollama 本机地址")
    a.add_argument("--ai-timeout", type=float, default=30, help="AI 请求超时秒数（默认 30）")
    web = sub.add_parser("serve", help="启动本地网页界面，仅绑定 127.0.0.1")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--no-browser", action="store_true", help="启动服务但不自动打开浏览器")
    update = sub.add_parser("intel-update", help="显式联网获取 CISA 官方 KEV，不上传配置")
    update.add_argument("--out", type=Path, help="保存位置；默认在用户缓存目录")
    args = p.parse_args(argv)
    try:
        if args.command == "serve":
            from .server import serve
            if not 0 <= args.port <= 65535:
                raise ValueError("端口必须在 0–65535 范围内")
            serve(args.port, open_browser=not args.no_browser)
            return 0
        if args.command == "intel-update":
            from .intelligence import fetch_official_kev
            output = args.out or Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "NetAudit" / "kev.json"
            fetch_official_kev(destination=output)
            print(f"KEV 已更新：{output}；审计时使用 --kev-file 指定该文件。")
            return 0
        if args.input == "-":
            data = sys.stdin.buffer.read(MAX_BYTES + 1)
        else:
            with Path(args.input).open("rb") as f:
                data = f.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("配置超过 2 MiB 限制")
        if args.out:
            if args.input != "-" and args.out.resolve() == Path(args.input).resolve():
                raise ValueError("报告输出不能覆盖输入配置")
            if any(path and args.out.resolve() == path.resolve()
                   for path in (args.asset_info, args.kev_file, args.nvd_file)):
                raise ValueError("报告输出不能覆盖设备信息或情报文件")
        result = audit_configuration(
            data.decode("utf-8-sig"), args.vendor,
            asset=_load_json(args.asset_info, "设备信息", 65536),
            kev=load_intelligence_file(args.kev_file, "kev") if args.kev_file else None,
            nvd=load_intelligence_file(args.nvd_file, "nvd") if args.nvd_file else None,
            ai={"enabled": bool(args.ai_model), "provider": "ollama", "model": args.ai_model or "",
                "endpoint": args.ai_endpoint, "timeout": args.ai_timeout})
        output = render(result, args.format)
        if args.out:
            _write_private(args.out, output)
            print(f"报告已生成：{args.out}", file=sys.stderr)
        else:
            print(output, end="")
        if args.strict and result["summary"]["unsupported_lines"]:
            return 2
        if args.fail_on and any(SEVERITIES[f["severity"]] >= SEVERITIES[args.fail_on] for f in result["findings"]):
            return 1
        return 0
    except (OSError, ValueError, UnicodeError) as exc:
        print("错误：" + (str(exc) if not isinstance(exc, UnicodeError) else "配置必须为 UTF-8 文本"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
