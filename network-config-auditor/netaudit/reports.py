import html
import json
import re
from urllib.parse import urlsplit


DOMAIN_LABELS = {"vlan": "VLAN", "stp": "STP", "ospf": "OSPF", "acl": "ACL", "nat": "NAT", "management_plane": "Management Plane / 管理平面"}
STAGE_LABELS = {"parser": "配置解析器", "parse": "配置解析器", "architecture": "网络架构检查", "security": "安全规则引擎", "rules": "安全规则引擎", "intelligence": "CVE / KEV 情报", "ai": "AI 解释与整改建议", "reports": "Markdown / HTML 报告"}
STATUS_LABELS = {
    "completed": "已完成", "passed": "已完成", "checked": "已检查", "findings": "存在发现",
    "needs-review": "需人工核对", "not-observed": "未观察到配置", "not-configured": "未配置",
    "no-matches": "未匹配", "matched": "已匹配", "disabled": "未启用", "error": "失败",
    "unavailable": "不可用", "skipped": "已跳过", "not-requested": "未启用", "failed": "失败", "not-needed": "无需解释",
}
CONFIDENCE_LABELS = {"cpe-version-match": "精确 CPE 版本关联，仍需核对适用条件", "needs-review": "需人工核对", "user-provided-candidate": "用户提供候选编号"}
ORIGIN_LABELS = {"bundled-official-snapshot": "随包官方快照", "bundled": "随包快照", "user-import": "本地导入（未核实来源）", "caller-provided-unverified": "用户提供（未核实来源）", "official-download": "官方地址下载"}


def _text(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value) if value is not None else "—"


def _safe_md(value) -> str:
    """Keep model and intelligence text literal, including Markdown links."""
    text = html.escape(_text(value)).replace("\\", "\\\\")
    text = re.sub(r"([*_[\]{}()#+!~])", r"\\\1", text)
    return text.replace("`", "&#96;").replace("|", "&#124;").replace("\n", "<br>")


def _https_url(value) -> str | None:
    if not isinstance(value, str) or any(ord(char) < 32 for char in value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() == "https" and parsed.hostname and not parsed.username and not parsed.password:
            return value
    except ValueError:
        pass
    return None


def _source_link(value, html_format=False) -> str:
    url = _https_url(value)
    if url:
        escaped = html.escape(url, quote=True)
        return f'<a href="{escaped}" rel="noreferrer noopener">{escaped}</a>'
    return html.escape(_text(value)) if html_format else _safe_md(value)


def _status(value) -> str:
    return STATUS_LABELS.get(value, _text(value))


def _architecture_markdown(report: dict) -> list[str]:
    lines = []
    if report.get("pipeline"):
        lines.extend(["", "## 审计流程", "", "| 阶段 | 状态 | 说明 |", "|---|---|---|"])
        for item in report["pipeline"]:
            lines.append("| " + " | ".join(_safe_md(value) for value in (STAGE_LABELS.get(item.get("stage"), item.get("stage")), _status(item.get("status")), item.get("detail"))) + " |")
    domains = (report.get("architecture") or {}).get("domains", [])
    if domains:
        lines.extend(["", "## 网络架构检查", "", "状态仅反映输入配置中的证据；未观察到或未匹配不表示设备安全。", "", "| 检查域 | 状态 | 已观察配置 | 检查覆盖 / 限制 | 相关规则 |", "|---|---|---|---|---|"])
        for item in domains:
            domain = item.get("domain")
            values = (DOMAIN_LABELS.get(domain, domain), _status(item.get("status")), item.get("observed"), item.get("coverage"), ", ".join(item.get("finding_ids", [])))
            lines.append("| " + " | ".join(_safe_md(value) for value in values) + " |")
    return lines


def _enrichment_markdown(report: dict) -> list[str]:
    lines = []
    intel = report.get("intelligence")
    if intel:
        lines.extend(["", "## CVE / KEV 情报", "", f"状态：{_safe_md(_status(intel.get('status')))}", "", _safe_md(intel.get("message", "")), "", "资产标识：" + _safe_md(intel.get("asset", {}))])
        for label, key in (("精确版本匹配", "matches"), ("候选项（不能作为已确认漏洞）", "candidates")):
            lines.extend(["", "### " + label, ""])
            if not intel.get(key):
                lines.append("无。未匹配不表示安全；设备版本、适用条件和厂商公告仍需核对。")
            for item in intel.get(key, []):
                lines.extend([f"- **{_safe_md(item.get('cve_id'))}** · {_safe_md(item.get('title', ''))}",
                              "  - 严重度：" + _safe_md(item.get("severity")) + "；KEV 已知利用：" + ("是" if item.get("known_exploited") else "未收录"),
                              "  - 判断：" + _safe_md(CONFIDENCE_LABELS.get(item.get("confidence"), item.get("confidence", ""))) + "；匹配依据：" + _safe_md(item.get("match_basis", "")),
                              "  - 说明：" + _safe_md(item.get("description", "")),
                              "  - 来源：" + _source_link(item.get("source_url", ""))])
                if item.get("kev"):
                    lines.append("  - CISA 要求：" + _safe_md(item["kev"].get("requiredAction", "")))
        if intel.get("sources"):
            lines.extend(["", "### 情报来源与时效", ""])
            for source in intel["sources"]:
                lines.extend(["- " + _safe_md(source.get("name", source.get("kind"))) + " · " + _source_link(source.get("source_url", "")),
                              "  - 发布日期：" + _safe_md(source.get("date_released")) + "；目录版本：" + _safe_md(source.get("catalog_version")) + "；来源：" + _safe_md(ORIGIN_LABELS.get(source.get("origin"), source.get("origin"))),
                              "  - SHA-256：" + _safe_md(source.get("sha256")) + "；快照过期：" + ("是" if source.get("stale") else "否"),
                              "  - 快照年龄（天）：" + _safe_md(source.get("age_days")) + "；目录条目：" + _safe_md(source.get("count")) + "；许可 / 归属：" + _safe_md(source.get("license"))])
        for limitation in intel.get("limitations", []):
            lines.append("- 适用限制：" + _safe_md(limitation))
    ai = report.get("ai")
    if ai:
        lines.extend(["", "## AI 解释与整改建议", "", f"状态：{_safe_md(_status(ai.get('status')))} · 提供方：{_safe_md(ai.get('provider'))} · 模型：{_safe_md(ai.get('model'))}", "", _safe_md(ai.get("message", "")), "", "模型内容仅供辅助理解，不能替代规则证据、厂商公告和变更审批。"])
        for item in ai.get("items", []):
            lines.extend(["", "### " + _safe_md(item.get("rule_id")), "", "**解释：** " + _safe_md(item.get("explanation", "")), "", "**整改建议：** " + _safe_md(item.get("remediation", ""))])
    return lines


def _pipeline_html(report: dict, enrichment=False) -> str:
    """Render literal text through one escaping boundary, never model HTML."""
    esc = lambda value: html.escape(_text(value), quote=True)
    parts = []
    if not enrichment:
        if report.get("pipeline"):
            parts.append("<section><h2>审计流程</h2><ol>")
            for item in report["pipeline"]:
                parts.append(f"<li><strong>{esc(STAGE_LABELS.get(item.get('stage'), item.get('stage')))}</strong> · {esc(_status(item.get('status')))}：{esc(item.get('detail'))}</li>")
            parts.append("</ol></section>")
        domains = (report.get("architecture") or {}).get("domains", [])
        if domains:
            parts.append("<section><h2>网络架构检查</h2><p>状态仅反映输入配置中的证据；未观察到或未匹配不表示设备安全。</p><table><thead><tr><th>检查域</th><th>状态</th><th>已观察配置</th><th>检查覆盖 / 限制</th><th>相关规则</th></tr></thead><tbody>")
            for item in domains:
                domain = item.get("domain")
                values = (DOMAIN_LABELS.get(domain, domain), _status(item.get("status")), item.get("observed"), item.get("coverage"), ", ".join(item.get("finding_ids", [])))
                parts.append("<tr>" + "".join("<td>" + esc(value) + "</td>" for value in values) + "</tr>")
            parts.append("</tbody></table></section>")
        return "".join(parts)
    intel = report.get("intelligence")
    if intel:
        parts.append(f"<section><h2>CVE / KEV 情报</h2><p>状态：{esc(_status(intel.get('status')))}</p><p>{esc(intel.get('message', ''))}</p><p>资产标识：{esc(intel.get('asset', {}))}</p>")
        for label, key in (("精确版本匹配", "matches"), ("候选项（不能作为已确认漏洞）", "candidates")):
            parts.append("<h3>" + label + "</h3>")
            if not intel.get(key):
                parts.append("<p>无。未匹配不表示安全；设备版本、适用条件和厂商公告仍需核对。</p>")
            for item in intel.get(key, []):
                parts.append(f"<article><h3>{esc(item.get('cve_id'))} · {esc(item.get('title', ''))}</h3><p>严重度：{esc(item.get('severity'))}；KEV 已知利用：{'是' if item.get('known_exploited') else '未收录'}</p><p>判断：{esc(CONFIDENCE_LABELS.get(item.get('confidence'), item.get('confidence', '')))}；匹配依据：{esc(item.get('match_basis', ''))}</p><p>{esc(item.get('description', ''))}</p><p>来源：{_source_link(item.get('source_url', ''), True)}</p>")
                if item.get("kev"):
                    parts.append("<p>CISA 要求：" + esc(item["kev"].get("requiredAction", "")) + "</p>")
                parts.append("</article>")
        if intel.get("sources"):
            parts.append("<h3>情报来源与时效</h3><ul>")
            for source in intel["sources"]:
                parts.append(f"<li>{esc(source.get('name', source.get('kind')))} · {_source_link(source.get('source_url', ''), True)}<br>发布日期：{esc(source.get('date_released'))}；目录版本：{esc(source.get('catalog_version'))}；来源：{esc(ORIGIN_LABELS.get(source.get('origin'), source.get('origin')))}<br>SHA-256：{esc(source.get('sha256'))}；快照过期：{'是' if source.get('stale') else '否'}<br>快照年龄（天）：{esc(source.get('age_days'))}；目录条目：{esc(source.get('count'))}；许可 / 归属：{esc(source.get('license'))}</li>")
            parts.append("</ul>")
        if intel.get("limitations"):
            parts.append("<ul>" + "".join("<li>适用限制：" + esc(item) + "</li>" for item in intel["limitations"]) + "</ul>")
        parts.append("</section>")
    ai = report.get("ai")
    if ai:
        parts.append(f"<section><h2>AI 解释与整改建议</h2><p>状态：{esc(_status(ai.get('status')))} · 提供方：{esc(ai.get('provider'))} · 模型：{esc(ai.get('model'))}</p><p>{esc(ai.get('message', ''))}</p><p>模型内容仅供辅助理解，不能替代规则证据、厂商公告和变更审批。</p>")
        for item in ai.get("items", []):
            parts.append(f"<article><h3>{esc(item.get('rule_id'))}</h3><p><strong>解释：</strong>{esc(item.get('explanation', ''))}</p><p><strong>整改建议：</strong>{esc(item.get('remediation', ''))}</p></article>")
        parts.append("</section>")
    return "".join(parts)


def _md(value) -> str:
    return html.escape(str(value)).replace("`", "&#96;").replace("|", "&#124;").replace("\n", "<br>")


def markdown(report: dict) -> str:
    d, s = report["device"], report["summary"]
    lines = ["# 网络配置审计报告", "", f"设备：{_md(d['hostname'])} · 厂商：{d['vendor']}", "",
             f"发现 {s['total']} 项；识别 {s['recognized_lines']}/{s['relevant_lines']} 行，未建模 {s['unsupported_lines']} 行。", "",
             report["limitations"], "", "| 严重度 | 数量 |", "|---|---:|"]
    if s.get("merged_count", 0):
        lines[4:4] = [f"同类问题已合并：{s['total']} 类发现，涉及 {s['occurrences_total']} 处；完整对象与证据仍保留。", ""]
    lines.extend(f"| {k} | {v} |" for k, v in s["severity"].items())
    lines.extend(_architecture_markdown(report))
    for i, f in enumerate(report["findings"], 1):
        lines.extend(["", f"## {i}. [{f['severity'].upper()}] {_md(f['title'])}", "",
                      f"规则：{f['rule_id']} · 判断：{f['confidence']}", "",
                      "**配置问题：** " + _md(f["problem"]), "",
                      "**安全风险：** " + _md(f["risk"]), "",
                      "**修改建议：** " + _md(f["recommendation"]), ""])
        if f.get("occurrences", 1) > 1 or f.get("affected_objects"):
            lines.extend(["**影响范围：** " + str(f.get("occurrences", 1)) + " 处；"
                          + _md("、".join(f.get("affected_objects", []))), ""])
        for e in f["evidence"]:
            lines.append(f"- L{e['line']}: <code>{_md(e['text'])}</code>")
        if f.get("command_notes"):
            lines.extend(["", "**命令前提：** " + _md(f["command_notes"]), ""])
        for key, label in (("verification_commands", "检查与验证命令（只读）"),
                           ("commands", "建议整改命令（核对设备版本与业务后使用）"),
                           ("command_templates", "命令模板（填写参数并核对后使用）")):
            if f.get(key):
                lines.extend(["", "**" + label + "：**", ""])
                lines.extend("<pre><code>" + html.escape(cmd) + "</code></pre>" for cmd in f[key])
    lines.extend(_enrichment_markdown(report))
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
        scope = ("<p><strong>影响范围：</strong>" + str(f.get("occurrences", 1)) + " 处；"
                 + esc("、".join(f.get("affected_objects", []))) + "</p>"
                 if f.get("occurrences", 1) > 1 or f.get("affected_objects") else "")
        commands = ("<p><strong>命令前提：</strong>" + esc(f["command_notes"]) + "</p>"
                    if f.get("command_notes") else "")
        for key, label in (("verification_commands", "检查与验证命令（只读）"),
                           ("commands", "建议整改命令（核对设备版本与业务后使用）"),
                           ("command_templates", "命令模板（填写参数并核对后使用）")):
            if f.get(key):
                commands += "<h3>" + label + "</h3>" + "".join("<pre>" + esc(cmd) + "</pre>" for cmd in f[key])
        cards.append(f"<article><span>{esc(f['severity'].upper())} · {esc(f['rule_id'])} · {esc(f['confidence'])}</span><h2>{esc(f['title'])}</h2>"
                     + "".join(f"<p><strong>{label}</strong>{esc(f[key])}</p>" for label, key in (("配置问题：", "problem"), ("安全风险：", "risk"), ("修改建议：", "recommendation")))
                     + scope + f"<pre>{esc(evidence)}</pre>" + commands + "</article>")
    inv = esc(json.dumps(report["inventory"], ensure_ascii=False, indent=2))
    s = report["summary"]
    return ("<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
            "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
            "<title>网络配置审计报告</title><style>body{font:16px/1.7 system-ui;background:#f3f6fa;color:#17293c;max-width:1000px;margin:40px auto;padding:20px}article,section{background:white;border:1px solid #dce4ed;padding:24px;margin:20px 0;border-radius:12px}span{color:#627388;font-size:13px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef3f8;padding:16px}h1{font-size:30px}h2{font-size:21px}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #dce4ed;padding:8px;text-align:left;vertical-align:top;overflow-wrap:anywhere}p,li,a{overflow-wrap:anywhere}</style>"
            f"<h1>网络配置审计报告</h1><p>{esc(report['device']['hostname'])} · {esc(report['device']['vendor'])}</p>"
            f"<p>发现 {s['total']} 项 · 识别 {s['recognized_lines']}/{s['relevant_lines']} 行 · 未建模 {s['unsupported_lines']} 行</p>"
            + (f"<p>同类问题已合并：{s['total']} 类发现，涉及 {s['occurrences_total']} 处；完整对象与证据仍保留。</p>" if s.get("merged_count", 0) else "")
            + "<p>" + esc(report["limitations"]) + "</p>" + _pipeline_html(report) + "".join(cards) + _pipeline_html(report, enrichment=True)
            + "<details><summary>查看完整配置清单与未建模行</summary><pre>" + inv + "</pre></details></html>")


def render(report: dict, format_: str) -> str:
    if format_ == "json":
        return json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if format_ == "html":
        return html_report(report)
    if format_ == "md":
        return markdown(report)
    raise ValueError("未知报告格式")
