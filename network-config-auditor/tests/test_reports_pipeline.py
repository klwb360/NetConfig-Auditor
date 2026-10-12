import copy
import json
import unittest

from netaudit import audit, parse_config
from netaudit.reports import render


def base_report():
    report = audit(parse_config("hostname LAB\nip http server", "cisco"))
    for key in ("architecture", "pipeline", "intelligence", "ai"):
        report.pop(key, None)
    return report


def enriched_report():
    report = base_report()
    report["pipeline"] = [
        {"stage": "配置解析器", "status": "completed", "detail": "解析输入配置"},
        {"stage": "AI解释", "status": "disabled", "detail": "默认关闭"},
    ]
    report["architecture"] = {"domains": [
        {"domain": domain, "status": "checked" if index == 0 else "not-observed", "observed": index,
         "coverage": "只检查静态证据", "finding_ids": ["MGMT-HTTP"] if index == 5 else []}
        for index, domain in enumerate(("vlan", "stp", "ospf", "acl", "nat", "management_plane"))
    ]}
    report["intelligence"] = {
        "status": "needs-review", "message": "未匹配不表示安全", "asset": {"cpe": "cpe:2.3:o:vendor:product:1.0:*:*:*:*:*:*:*"},
        "sources": [{"kind": "kev", "name": "CISA KEV", "source_url": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
                     "catalog_version": "2026.10.03", "date_released": "2026-10-03", "sha256": "abc123", "origin": "bundled",
                     "stale": False, "age_days": 0, "license": "CISA attribution"}],
        "matches": [{"cve_id": "CVE-2025-12345", "title": "精确 CPE 示例", "description": "需核对适用条件", "severity": "high",
                     "known_exploited": True, "confidence": "cpe-version-match", "match_basis": "精确版本配置匹配",
                     "source_url": "https://nvd.nist.gov/vuln/detail/CVE-2025-12345", "kev": {"requiredAction": "Apply vendor updates"}}],
        "candidates": [{"cve_id": "CVE-2024-12345", "title": "候选示例", "description": "手工编号不能证明适用性", "severity": "unknown",
                        "known_exploited": False, "confidence": "user-provided-candidate", "match_basis": "用户提供编号",
                        "source_url": "https://nvd.nist.gov/vuln/detail/CVE-2024-12345", "kev": None}],
        "limitations": ["没有动态漏洞验证"],
    }
    report["ai"] = {"status": "completed", "provider": "ollama", "model": "local-model", "message": "本机辅助解释",
                    "items": [{"rule_id": "MGMT-HTTP", "explanation": "管理 HTTP 缺少加密", "remediation": "核对后关闭 HTTP"}]}
    return report


class PipelineReportTests(unittest.TestCase):
    def test_legacy_report_has_original_findings_and_inventory(self):
        for format_ in ("md", "html"):
            output = render(base_report(), format_)
            self.assertIn("MGMT-HTTP", output)
            self.assertIn("配置问题", output)
            self.assertIn("配置清单", output)
            self.assertNotIn("CVE / KEV 情报", output)
        self.assertIn("| 严重度 | 数量 |", render(base_report(), "md"))

    def test_empty_optional_sections_and_null_architecture_are_supported(self):
        report = base_report()
        report.update(pipeline=[], architecture=None, intelligence={}, ai={})
        for format_ in ("md", "html"):
            self.assertIn("MGMT-HTTP", render(report, format_))

    def test_all_six_domains_and_evidence_counts_are_displayed(self):
        for format_ in ("md", "html"):
            output = render(enriched_report(), format_)
            for domain in ("VLAN", "STP", "OSPF", "ACL", "NAT", "Management Plane"):
                self.assertIn(domain, output)
            self.assertIn("未观察到配置", output)
            self.assertIn("只检查静态证据", output)
            self.assertIn("未观察到或未匹配不表示设备安全", output)

    def test_enrichment_follows_architecture_and_original_findings(self):
        for format_ in ("md", "html"):
            output = render(enriched_report(), format_)
            self.assertLess(output.index("审计流程"), output.index("网络架构检查"))
            self.assertLess(output.index("网络架构检查"), output.index("配置问题"))
            self.assertLess(output.index("配置问题"), output.index("CVE / KEV 情报"))
            self.assertLess(output.index("CVE / KEV 情报"), output.index("AI 解释与整改建议"))

    def test_wire_pipeline_stage_identifiers_have_chinese_labels(self):
        report = base_report()
        report["pipeline"] = [{"stage": stage, "status": "completed", "detail": "已完成"}
                              for stage in ("parser", "architecture", "security", "intelligence", "ai", "reports")]
        for format_ in ("md", "html"):
            output = render(report, format_)
            for label in ("配置解析器", "网络架构检查", "安全规则引擎", "CVE / KEV 情报", "AI 解释与整改建议", "Markdown / HTML 报告"):
                self.assertIn(label, output)
        self.assertNotIn("| security |", render(report, "md"))

    def test_exact_matches_and_candidates_are_distinct(self):
        for format_ in ("md", "html"):
            output = render(enriched_report(), format_)
            self.assertIn("精确版本匹配", output)
            self.assertIn("候选项（不能作为已确认漏洞）", output)
            self.assertIn("CVE-2025-12345", output)
            self.assertIn("CVE-2024-12345", output)
            self.assertIn("KEV 已知利用：是", output)
            self.assertIn("KEV 已知利用：未收录", output)
            self.assertIn("Apply vendor updates", output)
            self.assertIn("没有动态漏洞验证", output)

    def test_source_freshness_hash_and_attribution_are_preserved(self):
        for format_ in ("md", "html"):
            output = render(enriched_report(), format_)
            self.assertIn("2026.10.03", output)
            self.assertIn("2026-10-03", output)
            self.assertIn("abc123", output)
            self.assertIn("CISA attribution", output)
            self.assertIn("快照年龄（天）：0", output)

    def test_disabled_and_failed_ai_have_readable_status(self):
        report = enriched_report()
        for status, label in (("disabled", "未启用"), ("failed", "失败"), ("not-needed", "无需解释")):
            report["ai"].update(status=status, items=[])
            for format_ in ("md", "html"):
                output = render(report, format_)
                self.assertIn("AI 解释与整改建议", output)
                self.assertIn(label, output)
                self.assertIn("不能替代规则证据", output)

    def test_model_text_cannot_inject_html_or_markdown_links(self):
        report = enriched_report()
        hostile = '<script>alert(1)</script><img src=x onerror=alert(1)> [点击](javascript:alert(1)) **伪造标题** | `命令`'
        report["ai"]["items"][0].update(explanation=hostile, remediation=hostile)
        report["intelligence"]["matches"][0]["description"] = hostile
        report["architecture"]["domains"][0]["coverage"] = hostile
        for format_ in ("md", "html"):
            output = render(report, format_)
            self.assertNotIn("<script>", output)
            self.assertNotIn("<img src=", output)
            self.assertIn("&lt;script&gt;", output)
        output = render(report, "md")
        self.assertNotIn("[点击](javascript:", output)
        self.assertIn(r"\[点击\]\(javascript:alert\(1\)\)", output)
        self.assertIn(r"\*\*伪造标题\*\*", output)
        self.assertIn("&#124;", output)
        self.assertIn("&#96;命令&#96;", output)

    def test_only_https_sources_become_clickable(self):
        report = enriched_report()
        for value in ("javascript:alert(1)", "data:text/html,<script>x</script>", "http://example.test", "https://user:password@example.test", "https://example.test\nmalformed"):
            report["intelligence"]["sources"][0]["source_url"] = value
            report["intelligence"]["matches"][0]["source_url"] = value
            for format_ in ("md", "html"):
                self.assertNotIn('href="' + value, render(report, format_))
        report["intelligence"]["sources"][0]["source_url"] = 'https://example.test/?q="quoted"&a=1'
        for format_ in ("md", "html"):
            self.assertIn('href="https://example.test/?q=&quot;quoted&quot;&amp;a=1"', render(report, format_))

    def test_rendering_does_not_mutate_findings_or_report_json(self):
        report = enriched_report()
        before = copy.deepcopy(report)
        for format_ in ("md", "html", "json"):
            render(report, format_)
        self.assertEqual(report, before)
        self.assertEqual(json.loads(render(report, "json")), report)
        self.assertEqual(report["findings"], base_report()["findings"])


if __name__ == "__main__":
    unittest.main()
