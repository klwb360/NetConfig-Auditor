import html
import json


def _md(value) -> str:
    return html.escape(str(value)).replace("`", "&#96;").replace("|", "&#124;").replace("\n", "<br>")


def markdown(report: dict) -> str:
    d, s = report["device"], report["summary"]
    lines = ["# 网络配置审计报告", "", f"设备：{_md(d['hostname'])} · 厂商：{d['vendor']}", "",
             f"发现 {s['total']} 项；识别 {s['recognized_lines']}/{s['relevant_lines']} 行，未建模 {s['unsupported_lines']} 行。", "",
             report["limitations"], "", "| 严重度 | 数量 |", "|---|---:|"]
    lines.extend(f"| {k} | {v} |" for k, v in s["severity"].items())
    for i, f in enumerate(report["findings"], 1):
        lines.extend(["", f"## {i}. [{f['severity'].upper()}] {_md(f['title'])}", "",
                      f"规则：{f['rule_id']} · 判断：{f['confidence']}", "",
                      "**配置问题：** " + _md(f["problem"]), "",
                      "**安全风险：** " + _md(f["risk"]), "",
                      "**修改建议：** " + _md(f["recommendation"]), ""])
        for e in f["evidence"]:
            lines.append(f"- L{e['line']}: <code>{_md(e['text'])}</code>")
        if f["commands"]:
            lines.extend(["", "建议命令（核对设备版本与业务后使用）：", ""])
            lines.extend("- <code>" + _md(cmd) + "</code>" for cmd in f["commands"])
    inv = report["inventory"]
    lines.extend(["", "## 配置清单", "", f"接口 {len(inv['interfaces'])} · VLAN {len(inv['vlans'])} · 静态路由 {len(inv['routes'])} · ACL {len(inv['acls'])} · NAT {len(inv['nat'])}", "",
                  "完整结构化清单见 JSON 导出或网页界面的配置清单。", "", "## 未建模与格式问题", ""])
    lines.extend(f"- L{w['line']}: <code>{_md(w['text'])}</code> — {_md(w['reason'])}" for w in inv["warnings"])
    return "\n".join(lines) + "\n"


def html_report(report: dict) -> str:
    esc = html.escape
    cards = []
    for f in report["findings"]:
        evidence = "\n".join(f"L{e['line']}: {e['text']}" for e in f["evidence"])
        cards.append(f"<article><span>{esc(f['severity'].upper())} · {esc(f['rule_id'])} · {esc(f['confidence'])}</span><h2>{esc(f['title'])}</h2>"
                     + "".join(f"<p><strong>{label}</strong>{esc(f[key])}</p>" for label, key in (("配置问题：", "problem"), ("安全风险：", "risk"), ("修改建议：", "recommendation")))
                     + f"<pre>{esc(evidence)}</pre>" + ("<h3>建议命令（需核对平台与管理回退）</h3><pre>" + esc("\n".join(f["commands"])) + "</pre>" if f["commands"] else "") + "</article>")
    inv = esc(json.dumps(report["inventory"], ensure_ascii=False, indent=2))
    s = report["summary"]
    return ("<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
            "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
            "<title>网络配置审计报告</title><style>body{font:16px/1.7 system-ui;background:#f3f6fa;color:#17293c;max-width:1000px;margin:40px auto;padding:20px}article{background:white;border:1px solid #dce4ed;padding:24px;margin:20px 0;border-radius:12px}span{color:#627388;font-size:13px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef3f8;padding:16px}h1{font-size:30px}h2{font-size:21px}</style>"
            f"<h1>网络配置审计报告</h1><p>{esc(report['device']['hostname'])} · {esc(report['device']['vendor'])}</p>"
            f"<p>发现 {s['total']} 项 · 识别 {s['recognized_lines']}/{s['relevant_lines']} 行 · 未建模 {s['unsupported_lines']} 行</p>"
            + "<p>" + esc(report["limitations"]) + "</p>" + "".join(cards)
            + "<details><summary>查看完整配置清单与未建模行</summary><pre>" + inv + "</pre></details></html>")


def render(report: dict, format_: str) -> str:
    if format_ == "json":
        return json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if format_ == "html":
        return html_report(report)
    if format_ == "md":
        return markdown(report)
    raise ValueError("未知报告格式")
