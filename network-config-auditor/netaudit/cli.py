from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

from .parser import MAX_BYTES, VENDORS, parse_config
from .reports import render
from .rules import SEVERITIES, audit


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
    p = argparse.ArgumentParser(description="华为/Cisco/H3C 离线网络配置审计；无参数时打开本地网页")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("audit", help="审计配置文件或标准输入")
    a.add_argument("input", help="UTF-8 配置文件；- 表示标准输入")
    a.add_argument("--vendor", choices=VENDORS, default="auto")
    a.add_argument("--format", choices=("json", "md", "html"), default="md")
    a.add_argument("--out", type=Path)
    a.add_argument("--fail-on", choices=tuple(SEVERITIES), help="达到此严重度时退出码为 1")
    a.add_argument("--strict", action="store_true", help="存在未建模行则退出码为 2（仍输出报告）")
    web = sub.add_parser("serve", help="启动本地网页界面，仅绑定 127.0.0.1")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--no-browser", action="store_true", help="启动服务但不自动打开浏览器")
    args = p.parse_args(argv)
    try:
        if args.command == "serve":
            from .server import serve
            if not 0 <= args.port <= 65535:
                raise ValueError("端口必须在 0–65535 范围内")
            serve(args.port, open_browser=not args.no_browser)
            return 0
        if args.input == "-":
            data = sys.stdin.buffer.read(MAX_BYTES + 1)
        else:
            with Path(args.input).open("rb") as f:
                data = f.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("配置超过 2 MiB 限制")
        result = audit(parse_config(data.decode("utf-8-sig"), args.vendor))
        output = render(result, args.format)
        if args.out:
            if args.input != "-" and args.out.resolve() == Path(args.input).resolve():
                raise ValueError("报告输出不能覆盖输入配置")
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
