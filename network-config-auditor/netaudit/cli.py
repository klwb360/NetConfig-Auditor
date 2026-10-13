from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from . import __version__
from .branding import APPLICATION_NAME
from .parser import MAX_BYTES, VENDORS
from .reports import render
from .rules import SEVERITIES
from .pipeline import audit_configuration
from .intelligence import load_intelligence_file
from .config_io import ENCODINGS, decode_config_bytes

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
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as out:
            out.write(text)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # A double-click has no arguments. Also allow the convenient
    # `NetConfig-Auditor.exe --no-browser` form without changing audit arguments.
    if not argv or argv[0] in ("--no-browser", "--port") or argv[0].startswith("--port="):
        argv.insert(0, "serve")
    p = argparse.ArgumentParser(description="华为/Cisco/H3C/锐捷 RGOS 离线配置练习与审计；无参数时打开本地网页")
    p.add_argument("--version", action="version", version=f"{APPLICATION_NAME} {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("audit", help="审计配置文件或标准输入")
    a.add_argument("input", help="配置文件；- 表示标准输入")
    a.add_argument("--vendor", choices=VENDORS, default="auto")
    a.add_argument("--encoding", choices=ENCODINGS, default="auto", help="配置编码；auto 先识别 BOM，再严格尝试 UTF-8 / GB18030")
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
    batch = sub.add_parser("audit-batch", help="逐文件离线审计配置目录并输出 JSON / HTML 汇总")
    batch.add_argument("input", type=Path, help="输入配置目录")
    batch.add_argument("--out-dir", type=Path, required=True, help="报告目录，不能位于输入目录内")
    batch.add_argument("--recursive", action="store_true", help="递归扫描子目录")
    batch.add_argument("--vendor", choices=VENDORS, default="auto")
    batch.add_argument("--encoding", choices=ENCODINGS, default="auto")
    batch.add_argument("--strict", action="store_true", help="存在未建模行则退出码为 2")
    batch.add_argument("--fail-on", choices=tuple(SEVERITIES), help="达到此严重度时退出码为 1；输入错误优先为 2")
    simulation = sub.add_parser("simulate", help="在配置副本中练习命令，输出 JSON；失败批次全部回滚")
    simulation.add_argument("input", help="UTF-8 备份文件；- 表示标准输入")
    simulation.add_argument("--vendor", choices=VENDORS, default="auto")
    commands = simulation.add_mutually_exclusive_group()
    commands.add_argument("--commands", type=Path, help="UTF-8 命令文件，最大 64 KiB / 200 行")
    commands.add_argument("--command", dest="command_lines", action="append", help="命令，可重复指定；省略时查看当前状态")
    simulation.add_argument("--context", type=Path, help="上次结果中的 context 对象 JSON 文件")
    simulation.add_argument("--out", type=Path, help="成功时保存完整候选配置；含原有敏感信息，请妥善保管")
    plan = sub.add_parser("plan", help="根据单个中文目标生成并验证命令草案，不应用修改")
    plan.add_argument("input", help="UTF-8 备份文件；- 表示标准输入")
    plan.add_argument("--vendor", choices=VENDORS, default="auto")
    plan.add_argument("--goal", required=True, help="例如：创建 VLAN 20")
    plan.add_argument("--context", type=Path, help="当前 context 对象 JSON 文件")
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
            # Keep the existing cache directory so prior downloads remain usable.
            output = args.out or Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "NetAudit" / "kev.json"
            fetch_official_kev(destination=output)
            print(f"KEV 已更新：{output}；审计时使用 --kev-file 指定该文件。")
            return 0
        if args.command == "audit-batch":
            from .batch import audit_directory
            result = audit_directory(args.input, args.out_dir, vendor=args.vendor,
                                     encoding=args.encoding, recursive=args.recursive,
                                     strict=args.strict, fail_on=args.fail_on)
            summary = result["summary"]
            print(f"批量审计：共 {summary['total']} 个文件，完成 {summary['succeeded']}，失败 {summary['failed']}，待复核 {summary['review_required']}；无告警不表示安全。")
            for error in result["errors"]:
                print("错误：" + error["message"], file=sys.stderr)
            if result["devices"]:
                print(f"汇总报告：{args.out_dir / 'batch.json'} / {args.out_dir / 'batch.html'}")
            return result["exit_code"]
        if args.input == "-":
            data = sys.stdin.buffer.read(MAX_BYTES + 1)
        else:
            with Path(args.input).open("rb") as f:
                data = f.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("配置超过 2 MiB 限制")
        if args.command in ("simulate", "plan"):
            from .simulator import simulate_configuration
            from .simulation_goals import plan_goal
            config = data.decode("utf-8-sig")
            context = _load_json(args.context, "命令行上下文", 4096)
            if args.command == "plan":
                result = plan_goal(config, args.vendor, args.goal, context)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 0 if result["status"] == "ready" else 2
            if args.out:
                protected = [Path(args.input) if args.input != "-" else None, args.commands, args.context]
                if any(path and args.out.resolve() == path.resolve() for path in protected):
                    raise ValueError("模拟输出不能覆盖输入配置、命令或上下文文件")
            if args.commands:
                with args.commands.open("rb") as stream:
                    raw = stream.read(65537)
                if len(raw) > 65536:
                    raise ValueError("命令文件超过 64 KiB 限制")
                script = raw.decode("utf-8-sig")
            else:
                script = "\n".join(args.command_lines or [])
            result = simulate_configuration(config, args.vendor, script, context)
            failed = result["summary"]["rolled_back"]
            if args.out and not failed:
                _write_private(args.out, result["config"])
                print(f"模拟配置已导出：{args.out}；未修改设备或原备份。", file=sys.stderr)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2 if failed else 0
        if args.out:
            if args.input != "-" and args.out.resolve() == Path(args.input).resolve():
                raise ValueError("报告输出不能覆盖输入配置")
            if any(path and args.out.resolve() == path.resolve()
                   for path in (args.asset_info, args.kev_file, args.nvd_file)):
                raise ValueError("报告输出不能覆盖设备信息或情报文件")
        config, used_encoding = decode_config_bytes(data, args.encoding)
        result = audit_configuration(
            config, args.vendor,
            asset=_load_json(args.asset_info, "设备信息", 65536),
            kev=load_intelligence_file(args.kev_file, "kev") if args.kev_file else None,
            nvd=load_intelligence_file(args.nvd_file, "nvd") if args.nvd_file else None,
            ai={"enabled": bool(args.ai_model), "provider": "ollama", "model": args.ai_model or "",
                "endpoint": args.ai_endpoint, "timeout": args.ai_timeout})
        result["source"] = {"path": "stdin" if args.input == "-" else Path(args.input).name,
                            "sha256": hashlib.sha256(data).hexdigest(), "encoding": used_encoding}
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
