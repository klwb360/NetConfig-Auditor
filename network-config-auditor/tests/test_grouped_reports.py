"""Keep grouped scope and usable command contexts in every export format."""
import copy
import html
import json
import unittest
from html.parser import HTMLParser

from netaudit.reports import render


def grouped_report():
    evidence = [
        {"line": index * 3, "text": "interface GigabitEthernet0/" + str(index)}
        for index in range(1, 13)
    ]
    return {
        "device": {"hostname": "SYNTHETIC-LAB", "vendor": "ruijie"},
        "summary": {
            "total": 1, "occurrences_total": 12, "merged_count": 11,
            "severity": {"critical": 0, "high": 0, "medium": 1, "low": 0, "info": 0},
            "recognized_lines": 37, "relevant_lines": 37, "unsupported_lines": 0,
        },
        "findings": [{
            "rule_id": "VLAN-UNDEFINED", "severity": "medium", "category": "vlan",
            "title": "多个端口引用同一未见定义的 VLAN", "problem": "VLAN 120 在输入中未见定义。",
            "risk": "配置可能不完整。", "recommendation": "先检查定义，再核对业务创建 VLAN。",
            "confidence": "needs-review", "evidence": evidence,
            "affected_objects": ["GigabitEthernet0/" + str(index) for index in range(1, 13)],
            "occurrences": 12,
            "verification_commands": ["show vlan id 120"],
            "commands": ["configure terminal\nvlan 120\nexit\nend"],
            "command_templates": ["configure terminal\nvlan 120\n name <BUSINESS_NAME>\nexit\nend"],
            "command_notes": "仅在确认输入完整且 VLAN 120 确实缺失后使用；保存配置另行核对。",
        }],
        "inventory": {"interfaces": {}, "vlans": {}, "routes": [], "acls": {}, "nat": [], "warnings": []},
        "limitations": "静态审计不能证明设备运行状态。",
    }


class TextAndTags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)

    def handle_data(self, data):
        self.text.append(data)


class GroupedReportTests(unittest.TestCase):
    def test_json_preserves_every_scope_evidence_and_command_field(self):
        report = grouped_report()
        decoded = json.loads(render(report, "json"))
        self.assertEqual(decoded, report)
        self.assertEqual(len(decoded["findings"]), 1)
        self.assertEqual(len(decoded["findings"][0]["affected_objects"]), 12)
        self.assertEqual(len(decoded["findings"][0]["evidence"]), 12)

    def test_markdown_and_html_keep_all_scope_lines_beyond_web_fold_limit(self):
        report = grouped_report()
        for format_ in ("md", "html"):
            with self.subTest(format_=format_):
                exported = render(report, format_)
                self.assertIn("12 处", exported)
                for item in report["findings"][0]["evidence"]:
                    self.assertIn(f"L{item['line']}: ", exported)
                    self.assertIn(item["text"], exported)
                for name in report["findings"][0]["affected_objects"]:
                    self.assertIn(name, exported)

    def test_grouped_summary_keeps_findings_distinct_from_affected_occurrences(self):
        report = grouped_report()
        for format_ in ("md", "html"):
            with self.subTest(format_=format_):
                exported = render(report, format_)
                self.assertIn("发现 1 项", exported)
                self.assertIn("1 类发现，涉及 12 处", exported)
                self.assertNotIn("发现 12 项", exported)

    def test_commands_remain_multiline_and_separate_from_read_only_and_templates(self):
        report = grouped_report()
        for format_ in ("md", "html"):
            with self.subTest(format_=format_):
                exported = render(report, format_)
                self.assertIn("检查与验证命令（只读）", exported)
                self.assertIn("建议整改命令（核对设备版本与业务后使用）", exported)
                self.assertIn("命令模板（填写参数并核对后使用）", exported)
                self.assertIn("命令前提", exported)
                for key in ("verification_commands", "commands", "command_templates"):
                    for script in report["findings"][0][key]:
                        self.assertIn(html.escape(script), exported)

    def test_untrusted_object_evidence_commands_and_notes_are_literal_text(self):
        report = grouped_report()
        finding = report["findings"][0]
        hostile = "</pre><script>alert('lab')</script><img src=x onerror=alert(1)>"
        finding["affected_objects"] = [hostile]
        finding["evidence"] = [{"line": 9, "text": hostile}]
        finding["commands"] = ["configure terminal\n" + hostile + "\nend"]
        finding["verification_commands"] = [hostile]
        finding["command_templates"] = ["name <INPUT>\n" + hostile]
        finding["command_notes"] = hostile
        for format_ in ("md", "html"):
            with self.subTest(format_=format_):
                exported = render(report, format_)
                self.assertNotIn(hostile, exported)
                self.assertIn(html.escape(hostile), exported)
                parsed = TextAndTags()
                parsed.feed(exported)
                self.assertNotIn("script", parsed.tags)
                self.assertNotIn("img", parsed.tags)
                self.assertIn(hostile, "".join(parsed.text))

    def test_legacy_report_without_grouping_or_new_command_fields_still_exports(self):
        report = copy.deepcopy(grouped_report())
        for key in ("occurrences_total", "merged_count"):
            report["summary"].pop(key)
        for key in ("occurrences", "affected_objects", "verification_commands", "command_templates", "command_notes"):
            report["findings"][0].pop(key)
        report["findings"][0]["commands"] = []
        for format_ in ("json", "md", "html"):
            with self.subTest(format_=format_):
                exported = render(report, format_)
                self.assertIn("SYNTHETIC-LAB", exported)
                self.assertNotIn("同类问题已合并", exported)
                self.assertNotIn("检查与验证命令（只读）", exported)


if __name__ == "__main__":
    unittest.main()
