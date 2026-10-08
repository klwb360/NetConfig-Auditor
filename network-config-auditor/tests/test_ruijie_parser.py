"""Synthetic RGOS fixtures: no user-provided configuration is stored here."""

import unittest

from netaudit import audit, parse_config
from netaudit.model import Evidence, Finding


class RuijieParsingTests(unittest.TestCase):
    def test_rgos_marker_overrides_shared_ios_syntax(self):
        cfg = parse_config("version S29_RGOS 11.4(1)B12\nhostname SAMPLE\n"
                           "interface GigabitEthernet 0/1\n switchport access vlan 50")
        self.assertEqual(cfg.vendor, "ruijie")
        self.assertEqual(cfg.detection, "auto: RGOS version marker")
        self.assertEqual(cfg.interfaces["GigabitEthernet0/1"].access_vlan, 50)

    def test_rgos_marker_is_case_insensitive_and_requires_whole_header(self):
        cfg = parse_config("version s29_rgos 11.4\nhostname SAMPLE")
        self.assertEqual(cfg.vendor, "ruijie")
        for text in ("hostname SAMPLE\ndescription version S29_RGOS 11.4",
                     "version S29_RGOS_EXTRA 11.4\nhostname SAMPLE"):
            with self.subTest(text=text):
                self.assertEqual(parse_config(text).vendor, "cisco")

    def test_explicit_ruijie_without_version_header(self):
        self.assertEqual(parse_config("hostname SAMPLE", "ruijie").vendor, "ruijie")

    def test_rgos_mixed_with_other_vendor_markers_is_rejected(self):
        for foreign in ("interface Vlanif50", "port trunk allow-pass vlan 50",
                        "interface Vlan-interface50", "port trunk permit vlan 50"):
            with self.subTest(foreign=foreign), self.assertRaisesRegex(ValueError, "混合厂商"):
                parse_config("version S29_RGOS 11.4\nhostname SAMPLE\n" + foreign)

    def test_vlan_range_mixed_separators_and_evidence(self):
        cfg = parse_config("version S29_RGOS 11.4\n"
                           "vlan range 1,10 20,100,300-301\n name SEGMENT")
        self.assertEqual(set(cfg.vlans), {1, 10, 20, 100, 300, 301})
        self.assertTrue(all(v["evidence"].line == 2 for v in cfg.vlans.values()))
        self.assertTrue(all(v["name"] == "SEGMENT" for v in cfg.vlans.values()))
        self.assertEqual(cfg.unsupported_count, 0)

    def test_invalid_vlan_range_keeps_warning_and_no_partial_definition(self):
        for value in ("50,301-300", "50,4095", "range", ""):
            cfg = parse_config("version S29_RGOS 11.4\nvlan range " + value +
                               "\ninterface Gi0/1\n switchport access vlan 50")
            with self.subTest(value=value):
                self.assertEqual(cfg.vlans, {})
                self.assertEqual(cfg.interfaces["Gi0/1"].access_vlan, 50)
                self.assertEqual(cfg.warnings[0]["line"], 2)
                self.assertEqual(cfg.unsupported_count, 1)

    def test_vlan_declaration_removal_and_later_recreation(self):
        cfg = parse_config("version S29_RGOS 11.4\nvlan range 10-12,50\n"
                           "no vlan range 10-11\nundo vlan 50\nvlan 11")
        self.assertEqual(set(cfg.vlans), {11, 12})
        self.assertEqual(cfg.vlans[11]["evidence"].line, 5)
        self.assertEqual(cfg.unsupported_count, 0)
        cfg = parse_config("sysname SAMPLE\nvlan batch 10 11\nundo vlan batch 11", "huawei")
        self.assertEqual(set(cfg.vlans), {10})

    def test_invalid_vlan_removal_is_atomic(self):
        cfg = parse_config("version S29_RGOS 11.4\nvlan range 10-12\nno vlan range 10,20-19")
        self.assertEqual(set(cfg.vlans), {10, 11, 12})
        self.assertEqual(cfg.warnings[0]["line"], 3)

    def test_invalid_declaration_does_not_reuse_previous_vlan_context(self):
        cfg = parse_config("version S29_RGOS 11.4\nvlan 10\n name OLD\n"
                           " vlan range 4095\n name NEW")
        self.assertEqual(cfg.vlans[10]["name"], "OLD")
        self.assertEqual(cfg.unsupported_count, 2)

    def test_global_spanning_tree_enabled_and_disabled_states(self):
        cfg = parse_config("version S29_RGOS 11.4\nno spanning-tree")
        self.assertIs(cfg.stp["enabled"], False)
        self.assertEqual(cfg.stp["evidence"][0].line, 2)
        self.assertEqual(cfg.unsupported_count, 0)
        cfg = parse_config("version S29_RGOS 11.4\nno spanning-tree\nspanning-tree")
        self.assertIs(cfg.stp["enabled"], True)
        # Do not broaden support to another platform without establishing its
        # command semantics.
        cfg = parse_config("hostname SAMPLE\nno spanning-tree", "cisco")
        self.assertIsNone(cfg.stp["enabled"])
        self.assertEqual(cfg.unsupported_count, 1)

    def test_protected_port_is_modeled_without_inventing_stp_protection(self):
        cfg = parse_config("version S29_RGOS 11.4\ninterface Gi0/1\n switchport protected\n"
                           "interface Gi0/2\n switchport protected\n no switchport protected")
        self.assertIs(cfg.interfaces["Gi0/1"].protected, True)
        self.assertIs(cfg.interfaces["Gi0/2"].protected, False)
        self.assertIsNone(cfg.interfaces["Gi0/1"].bpdu_guard)
        self.assertIsNone(cfg.interfaces["Gi0/1"].stp_enabled)
        self.assertEqual(cfg.unsupported_count, 0)
        self.assertIs(cfg.to_dict()["interfaces"]["Gi0/1"]["protected"], True)

    def test_rgos_bpdufilter_suggestion_roundtrip_clears_only_the_target_risk(self):
        text = "version S29_RGOS 11.4\ninterface Gi0/1\n spanning-tree bpdufilter enabled"
        cfg = parse_config(text)
        self.assertIs(cfg.interfaces["Gi0/1"].bpdu_filter, True)
        self.assertEqual(cfg.unsupported_count, 0)
        finding = next(f for f in audit(cfg)["findings"] if f["rule_id"] == "STP-BPDU-FILTER")
        command = finding["commands"][0].splitlines()[2]
        self.assertEqual(command, "spanning-tree bpdufilter disabled")
        changed = parse_config(text + "\n " + command)
        self.assertIs(changed.interfaces["Gi0/1"].bpdu_filter, False)
        self.assertEqual(changed.unsupported_count, 0)
        self.assertFalse(any(f["rule_id"] == "STP-BPDU-FILTER" for f in audit(changed)["findings"]))

    def test_rgos_filter_variants_do_not_expand_cisco_syntax(self):
        cfg = parse_config("hostname SAMPLE\ninterface Gi0/1\n spanning-tree bpdufilter disabled", "cisco")
        self.assertIsNone(cfg.interfaces["Gi0/1"].bpdu_filter)
        self.assertEqual(cfg.unsupported_count, 1)

    def test_single_vty_and_explicit_disabled_or_ssh_transport(self):
        cfg = parse_config("version S29_RGOS 11.4\nline vty 0\n transport input none\n"
                           "line vty 1 4\n transport input ssh")
        self.assertEqual(len(cfg.management_lines), 2)
        self.assertEqual(cfg.management_lines[0].name, "line vty 0")
        self.assertEqual(cfg.management_lines[0].transport, ["none"])
        self.assertEqual(cfg.management_lines[1].transport, ["ssh"])
        self.assertEqual(cfg.unsupported_count, 0)

    def test_shared_ios_address_acl_route_and_nat_parsing(self):
        cfg = parse_config("version S29_RGOS 11.4\n"
                           "ip access-list extended SAMPLE_ACL\n"
                           " 10 permit tcp 192.0.2.0 0.0.0.255 any eq 443\n"
                           "interface GigabitEthernet 0/1\n"
                           " ip address 192.0.2.1 255.255.255.0\n"
                           " ip access-group SAMPLE_ACL in\n ip nat inside\n"
                           "ip route 0.0.0.0 0.0.0.0 192.0.2.254\n"
                           "ip nat inside source static 192.0.2.2 198.51.100.2")
        iface = cfg.interfaces["GigabitEthernet0/1"]
        self.assertEqual(iface.addresses, ["192.0.2.1/24"])
        self.assertEqual(iface.acl_bindings, {"in": "SAMPLE_ACL"})
        self.assertEqual(iface.nat_role, "inside")
        self.assertEqual(cfg.acls["SAMPLE_ACL"].rules[0].source, "192.0.2.0/24")
        self.assertEqual(cfg.acls["SAMPLE_ACL"].rules[0].destination_port, "eq 443")
        self.assertTrue(cfg.acls["SAMPLE_ACL"].rules[0].complete)
        self.assertEqual(cfg.routes[0].destination, "0.0.0.0/0")
        self.assertEqual(cfg.nat[0].kind, "static")
        self.assertEqual(cfg.unsupported_count, 0)

    def test_shared_ios_trunk_replace_add_remove_and_default(self):
        cfg = parse_config("version S29_RGOS 11.4\ninterface Gi0/1\n"
                           " switchport trunk allowed vlan 10-12\n"
                           " switchport trunk allowed vlan 50\n"
                           " switchport trunk allowed vlan add 60-61\n"
                           " switchport trunk allowed vlan remove 60")
        self.assertEqual(cfg.interfaces["Gi0/1"].allowed_vlans, [50, 61])
        cfg = parse_config("version S29_RGOS 11.4\ninterface Gi0/1\n"
                           " switchport trunk allowed vlan remove 1-4093")
        self.assertEqual(cfg.interfaces["Gi0/1"].allowed_vlans, [4094])

    def test_synthetic_many_port_switch_does_not_report_declared_vlans_missing(self):
        lines = ["version S29_RGOS 11.4", "no spanning-tree",
                 "vlan range 1,10,20,100,300-301", "!"]
        for port in range(1, 49):
            vlan = 100 if port <= 24 else 301
            lines.extend([f"interface GigabitEthernet 0/{port}",
                          " switchport protected", f" switchport access vlan {vlan}", "!"])
        for port in range(49, 53):
            lines.extend([f"interface TenGigabitEthernet 0/{port}", " switchport mode trunk", "!"])
        for vid in (1, 10, 20, 300):
            lines.extend([f"interface VLAN {vid}", "!"])
        cfg = parse_config("\n".join(lines))
        self.assertEqual(set(cfg.vlans), {1, 10, 20, 100, 300, 301})
        self.assertEqual(len(cfg.interfaces), 56)
        self.assertEqual(sum(i.access_vlan == 100 for i in cfg.interfaces.values()), 24)
        self.assertEqual(sum(i.access_vlan == 301 for i in cfg.interfaces.values()), 24)
        self.assertEqual(cfg.unsupported_count, 0)
        self.assertFalse(any(f["rule_id"] == "VLAN-UNDEFINED" for f in audit(cfg)["findings"]))

    def test_finding_defaults_preserve_previous_positional_construction(self):
        finding = Finding("TEST", "info", "VLAN", "title", "problem", "risk",
                          "recommendation", [Evidence(1, "vlan 10")],
                          "needs-review", ["show vlan"])
        self.assertEqual(finding.commands, ["show vlan"])
        self.assertEqual(finding.to_dict()["verification_commands"], [])
        self.assertEqual(finding.command_templates, [])
        self.assertEqual(finding.affected_objects, [])
        self.assertEqual(finding.occurrences, 1)


if __name__ == "__main__":
    unittest.main()
