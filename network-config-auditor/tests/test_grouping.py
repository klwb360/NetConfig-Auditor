import copy
import unittest

from netaudit.grouping import group_findings
from netaudit.model import Evidence, Finding


def issue(rule="MGMT-VTY-TELNET", scope="line vty 0 4", line=1, **changes):
    row = Finding(rule, "high", "management", "Shared risk", scope + " allows Telnet",
                  "Cleartext remote access", "Verify SSH, then restrict each affected range",
                  [Evidence(line, scope)])
    row.affected_objects = [scope]
    for key, value in changes.items():
        setattr(row, key, value)
    return row


class GroupingTests(unittest.TestCase):
    def test_complete_command_scripts_preserve_every_context_and_exit(self):
        first = issue(commands=["configure terminal", "line vty 0 4", "transport input ssh", "exit", "end"],
                      verification_commands=["show version", "show running-config"],
                      command_templates=["configure terminal", "line vty 0 4", "access-class <ACL> in", "exit", "end"],
                      command_notes="Confirm the first management range")
        second = issue(scope="line vty 5 15", line=5,
                       commands=["configure terminal", "line vty 5 15", "transport input ssh", "exit", "end"],
                       verification_commands=["show version", "show running-config"],
                       command_templates=["configure terminal", "line vty 5 15", "access-class <ACL> in", "exit", "end"],
                       command_notes="Confirm the second management range")
        before = copy.deepcopy([first, second])
        values = group_findings([first, second])
        self.assertEqual(len(values), 1)
        grouped = values[0]
        self.assertEqual(grouped.commands, first.commands + second.commands)
        self.assertEqual(grouped.commands.count("exit"), 2)
        self.assertEqual(grouped.commands.count("configure terminal"), 2)
        self.assertEqual(grouped.command_templates, first.command_templates + second.command_templates)
        self.assertEqual(grouped.verification_commands, ["show version", "show running-config"])
        self.assertIn(first.command_notes, grouped.command_notes)
        self.assertIn(second.command_notes, grouped.command_notes)
        self.assertEqual([first, second], before)

    def test_identical_whole_scripts_removed_without_losing_evidence(self):
        commands = ["configure terminal", "no ip http server", "end"]
        first = issue(rule="MGMT-CREDENTIAL", commands=commands)
        second = issue(rule="MGMT-CREDENTIAL", scope="account second", line=4, commands=commands)
        values = group_findings([first, second])
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].commands, commands)
        self.assertEqual(values[0].occurrences, 2)
        self.assertEqual([e.line for e in values[0].evidence], [1, 4])
        self.assertEqual(values[0].affected_objects, ["line vty 0 4", "account second"])

    def test_different_confidence_severity_or_remediation_never_merge(self):
        for changes in ({"severity": "low"}, {"confidence": "needs-review"},
                        {"risk": "A different risk"}, {"recommendation": "A different plan"},
                        {"category": "coverage"}):
            with self.subTest(changes=changes):
                self.assertEqual(len(group_findings([issue(), issue(line=5, **changes)])), 2)

    def test_acl_shadow_pairs_and_missing_vlans_are_not_generic_groups(self):
        for rule in ("ACL-SHADOW", "ACL-PERMIT-ANY", "VLAN-UNDEFINED",
                     "OSPF-AUTH-REVIEW", "ROUTE-SELF-NEXTHOP", "NAT-INBOUND-MAPPING"):
            with self.subTest(rule=rule):
                self.assertEqual(len(group_findings([issue(rule=rule), issue(rule=rule, line=5)])), 2)

    def test_stp_global_vlan_and_interface_scopes_remain_distinct(self):
        rows = [issue(rule="STP-DISABLED", problem="全局配置显式关闭生成树协议。"),
                issue(rule="STP-DISABLED", problem="下列 VLAN 的 STP 被显式关闭：10", line=3),
                issue(rule="STP-DISABLED", problem="接口 Gi0/1 显式关闭 STP。", scope="Gi0/1", line=5),
                issue(rule="STP-DISABLED", problem="接口 Gi0/2 显式关闭 STP。", scope="Gi0/2", line=8)]
        grouped = group_findings(rows)
        self.assertEqual(len(grouped), 3)
        self.assertEqual(grouped[-1].affected_objects, ["Gi0/1", "Gi0/2"])
        self.assertEqual(grouped[-1].occurrences, 2)
        self.assertIn("Gi0/1", grouped[-1].problem)
        self.assertIn("Gi0/2", grouped[-1].problem)

    def test_missing_object_scope_prevents_untraceable_grouping(self):
        rows = [issue(affected_objects=[]), issue(line=5, affected_objects=[])]
        self.assertEqual(len(group_findings(rows)), 2)

    def test_evidence_keeps_same_line_with_distinct_redacted_text(self):
        first = issue(evidence=[Evidence(1, "line vty 0 4"), Evidence(2, "first state")])
        second = issue(evidence=[Evidence(1, "line vty 0 4"), Evidence(2, "second state")])
        grouped = group_findings([first, second])[0]
        self.assertEqual([(e.line, e.text) for e in grouped.evidence],
                         [(1, "line vty 0 4"), (2, "first state"), (2, "second state")])


if __name__ == "__main__":
    unittest.main()
