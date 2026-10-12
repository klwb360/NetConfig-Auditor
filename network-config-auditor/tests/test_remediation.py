import unittest

from netaudit import audit, parse_config
from netaudit.model import Config, Evidence, Finding, Interface, ManagementLine
from netaudit.privacy import redact
from netaudit.remediation import enrich_findings


def issues(text, rule, vendor="ruijie"):
    return [f for f in audit(parse_config(text, vendor))["findings"] if f["rule_id"] == rule]


def finding(rule, category="management", evidence=None, problem="laboratory finding"):
    return Finding(rule, "medium", category, "laboratory", problem, "risk", "advice", evidence or [])


class RemediationTests(unittest.TestCase):
    def assert_script(self, script, vendor="ruijie"):
        lines = script.splitlines()
        self.assertEqual(lines[0], "configure terminal" if vendor in {"cisco", "ruijie"} else "system-view")
        self.assertEqual(lines[-1], "end" if vendor in {"cisco", "ruijie"} else "return")
        self.assertNotIn("[REDACTED]", script)
        self.assertFalse(any(line.startswith(("write", "save", "copy running", "reload")) for line in lines))

    def test_rgosh_ssh_version_suggestion_has_modes_and_no_key_regeneration(self):
        value = issues("! RGOS version 11.4\nhostname LAB\nip ssh version 1", "MGMT-SSHV1")[0]
        self.assertEqual(value["commands"], ["configure terminal\nip ssh version 2\nend"])
        self.assertIn("show ip ssh", value["verification_commands"])
        self.assertNotIn("crypto", "\n".join(value["commands"]))
        self.assertEqual(value["command_templates"], [])

    def test_cisco_existing_global_suggestions_still_exist_in_complete_scripts(self):
        text = "hostname LAB\nip ssh version 1\nip ssh authentication-retries 9\nip http server"
        expected = {"MGMT-SSHV1": "ip ssh version 2", "MGMT-SSH-RETRIES": "ip ssh authentication-retries 3", "MGMT-HTTP": "no ip http server"}
        for rule, command in expected.items():
            with self.subTest(rule=rule):
                value = issues(text, rule, "cisco")[0]
                self.assert_script(value["commands"][0], "cisco")
                self.assertIn(command, value["commands"][0].splitlines())

    def test_telnet_ranges_and_timeout_ranges_each_keep_two_independent_scripts(self):
        text = """hostname LAB
line vty 0 4
 transport input telnet
 exec-timeout 0 0
!
line vty 5 35
 transport input all
 exec-timeout 60 0
"""
        for rule, command in (("MGMT-VTY-TELNET", "transport input ssh"), ("MGMT-VTY-TIMEOUT", "exec-timeout 10 0")):
            with self.subTest(rule=rule):
                values = issues(text, rule)
                self.assertEqual(len(values), 1)
                value = values[0]
                self.assertEqual(value["occurrences"], 2)
                self.assertEqual(value["affected_objects"], ["line vty 0 4", "line vty 5 35"])
                self.assertEqual(len(value["commands"]), 2)
                for scope, script in zip(value["affected_objects"], value["commands"]):
                    self.assertEqual(script.splitlines(), ["configure terminal", scope, command, "exit", "end"])
                self.assertEqual(value["verification_commands"].count("show version"), 1)

    def test_vty_unknown_candidate_does_not_become_confirmed_change(self):
        value = issues("hostname LAB\nline vty 0 4\n!\nline vty 5 35", "MGMT-VTY-UNKNOWN")[0]
        self.assertEqual(value["commands"], [])
        self.assertEqual(len(value["command_templates"]), 2)
        self.assertIn("默认值", value["command_notes"])
        for script in value["command_templates"]:
            self.assert_script(script)
            self.assertIn("transport input ssh", script)

    def test_vty_source_template_uses_actual_ranges_and_explicit_missing_parameters(self):
        text = "hostname LAB\ninterface Vlan10\n ip address 192.0.2.10 255.255.255.0\n!\nline vty 0 4\n!\nline vty 5 35"
        value = issues(text, "MGMT-VTY-SOURCE")[0]
        self.assertEqual(value["commands"], [])
        self.assertEqual(len(value["command_templates"]), 2)
        for scope, script in zip(value["affected_objects"], value["command_templates"]):
            self.assert_script(script)
            self.assertIn(scope + "\naccess-class <UNUSED_STANDARD_ACL_ID> in", script)
            self.assertIn("<ADMIN_NETWORK> <ADMIN_WILDCARD_MASK>", script)
            self.assertNotIn("192.0.2.10", script)
            self.assertEqual(script.splitlines().count("exit"), 2)
        self.assertIn("回退", value["command_notes"])

    def test_huawei_and_h3c_vty_template_mode_chain(self):
        for vendor in ("huawei", "h3c"):
            with self.subTest(vendor=vendor):
                text = "sysname LAB\nuser-interface vty 0 4\n protocol inbound telnet\n idle-timeout 0 0\n#"
                value = issues(text, "MGMT-VTY-SOURCE", vendor)[0]
                template = value["command_templates"][0]
                self.assert_script(template, vendor)
                self.assertEqual(template.splitlines().count("quit"), 2)
                self.assertIn("acl number <UNUSED_BASIC_ACL_ID>", template)
                self.assertIn("user-interface vty 0 4\nacl <UNUSED_BASIC_ACL_ID> inbound", template)
                timeout = issues(text, "MGMT-VTY-TIMEOUT", vendor)[0]
                self.assertEqual(timeout["commands"], ["system-view\nuser-interface vty 0 4\nidle-timeout 10 0\nquit\nreturn"])

    def test_credentials_are_grouped_and_new_secrets_stay_unfilled(self):
        text = """hostname LAB
username lab1 password 0 secret_lab_a
username lab2 privilege 15 password 7 secret_lab_b
enable password 0 secret_lab_c
line vty 0 4
 password 7 secret_lab_d
"""
        values = issues(text, "MGMT-CREDENTIAL")
        self.assertEqual(len(values), 1)
        value = values[0]
        self.assertEqual(value["occurrences"], 4)
        self.assertEqual(len(value["command_templates"]), 4)
        self.assertEqual(value["commands"], [])
        scripts = "\n".join(value["command_templates"])
        for secret in ("secret_lab_a", "secret_lab_b", "secret_lab_c", "secret_lab_d", "[REDACTED]"):
            self.assertNotIn(secret, scripts)
        self.assertIn("username lab1 secret 0 <NEW_STRONG_PASSWORD>", scripts)
        self.assertIn("username lab2 secret 0 <NEW_STRONG_PASSWORD>", scripts)
        self.assertIn("enable secret 0 <NEW_STRONG_PASSWORD>", scripts)
        self.assertIn("login local", scripts)
        self.assertIn("AAA", value["command_notes"])
        self.assertIn("MD5", value["command_notes"])
        for script in value["command_templates"]:
            self.assert_script(script)

    def test_enable_level_is_preserved_without_inventing_privilege(self):
        value = issues("hostname LAB\nenable password level 7 0 secret_lab", "MGMT-CREDENTIAL")[0]
        self.assertIn("enable secret level 7 0 <NEW_STRONG_PASSWORD>", value["command_templates"][0])
        self.assertNotIn("level 15", value["command_templates"][0])

    def test_enable_redaction_preserves_level_role_and_protection_metadata(self):
        for text, expected in (
            ("enable password level 7 0 secret_lab", "enable password level 7 0 [REDACTED]"),
            ("enable password level 2 7 secret_lab", "enable password level 2 7 [REDACTED]"),
            ("enable secret level 15 5 secret_lab", "enable secret level 15 5 [REDACTED]"),
            ("enable secret role Network-admin 8 secret_lab", "enable secret role Network-admin 8 [REDACTED]"),
            ("enable password secret_lab", "enable password [REDACTED]"),
        ):
            with self.subTest(text=text):
                self.assertEqual(redact(text), expected)

    def test_out_of_range_enable_level_is_not_silently_changed_to_default(self):
        value = finding("MGMT-CREDENTIAL", evidence=[Evidence(1, "enable password level 99 0 [REDACTED]")])
        enrich_findings([value], Config("ruijie", "explicit", "LAB"))
        self.assertIn("level <VERIFIED_ENABLE_LEVEL>", value.command_templates[0])

    def test_snmp_encryption_selector_is_not_mistaken_for_secret_value(self):
        for selector in ("", "0 ", "7 ", "secret 0 ", "secret 8 "):
            with self.subTest(selector=selector):
                text = "snmp-server community " + selector + "secret_lab rw LAB-ACL"
                result = redact(text)
                self.assertNotIn("secret_lab", result)
                self.assertEqual(result, "snmp-server community " + selector + "[REDACTED] rw LAB-ACL")
                value = issues("hostname LAB\n" + text, "MGMT-SNMP-COMMUNITY")[0]
                self.assertEqual(value["severity"], "high")

    def test_snmp_redacted_secret_is_never_suggested_as_a_real_argument(self):
        value = issues("hostname LAB\nsnmp-server community secret_lab ro", "MGMT-SNMP-COMMUNITY")[0]
        self.assertEqual(value["commands"], [])
        self.assertEqual(value["command_templates"], ["configure terminal\nno snmp-server community <OLD_COMMUNITY>\nend"])
        self.assertNotIn("secret_lab", "\n".join(value["command_templates"]))
        self.assertIn("SNMPv3 authPriv", value["command_notes"])
        self.assertIn("show snmp user", value["verification_commands"])

    def test_same_missing_vlan_has_one_concrete_create_script_for_all_ports(self):
        text = "hostname LAB\ninterface GigabitEthernet 0/1\n switchport access vlan 120\n!\ninterface GigabitEthernet 0/2\n switchport access vlan 120"
        values = issues(text, "VLAN-UNDEFINED")
        self.assertEqual(len(values), 1)
        value = values[0]
        self.assertEqual(value["occurrences"], 2)
        self.assertEqual(value["commands"], ["configure terminal\nvlan 120\nexit\nend"])
        self.assertIn("show vlan id 120", value["verification_commands"])
        self.assertNotIn("switchport access", "\n".join(value["commands"]))
        self.assertIn("设备确认", value["command_notes"])

    def test_distinct_missing_vlans_are_not_changed_to_one_guessed_business_vlan(self):
        text = "hostname LAB\ninterface Gi0/1\n switchport access vlan 120\n!\ninterface Gi0/2\n switchport access vlan 220"
        values = issues(text, "VLAN-UNDEFINED")
        self.assertEqual(len(values), 2)
        self.assertEqual({f["commands"][0] for f in values}, {"configure terminal\nvlan 120\nexit\nend", "configure terminal\nvlan 220\nexit\nend"})

    def test_missing_vlan_commands_use_vendor_configuration_modes(self):
        for vendor in ("huawei", "h3c"):
            with self.subTest(vendor=vendor):
                text = "sysname LAB\ninterface GigabitEthernet0/1\n port access vlan 120\n#"
                value = issues(text, "VLAN-UNDEFINED", vendor)[0]
                self.assertEqual(value["commands"], ["system-view\nvlan 120\nquit\nreturn"])
                self.assertIn("display vlan 120", value["verification_commands"])

    def test_already_defined_or_invalid_vlan_never_gets_a_create_suggestion(self):
        config = Config("ruijie", "explicit", "LAB")
        config.vlans[120] = {"name": "LAB"}
        for vid in (120, 0, 1, 4095, 9999):
            with self.subTest(vid=vid):
                value = finding("VLAN-UNDEFINED", "vlan", problem=f"VLAN {vid} missing")
                enrich_findings([value], config)
                self.assertEqual(value.commands, [])

    def test_ruijie_stp_reenable_is_a_conditional_template_with_no_guessed_mode(self):
        value = issues("hostname LAB\nno spanning-tree", "STP-DISABLED")[0]
        self.assertEqual(value["commands"], [])
        self.assertEqual(value["command_templates"], ["configure terminal\nspanning-tree\nend"])
        self.assertNotIn("mode", "\n".join(value["command_templates"]))
        self.assertIn("维护窗口", value["command_notes"])
        self.assertIn("根桥", value["command_notes"])

    def test_bpdu_filter_two_ports_have_complete_independent_contexts(self):
        text = "hostname LAB\ninterface Gi0/1\n spanning-tree bpdufilter enable\n!\ninterface Gi0/2\n spanning-tree bpdufilter enable"
        value = issues(text, "STP-BPDU-FILTER")[0]
        self.assertEqual(len(value["commands"]), 2)
        for scope, script in zip(value["affected_objects"], value["commands"]):
            self.assertEqual(script.splitlines(), ["configure terminal", "interface " + scope, "spanning-tree bpdufilter disabled", "exit", "end"])

    def test_trunk_business_values_only_appear_as_named_parameters(self):
        value = issues("hostname LAB\ninterface Gi0/1\n switchport mode trunk\n switchport trunk allowed vlan all", "VLAN-TRUNK-ALL")[0]
        self.assertEqual(value["commands"], [])
        self.assertIn("<APPROVED_VLAN_LIST>", value["command_templates"][0])
        self.assertIn("替换列表", value["command_notes"])

    def test_huawei_trunk_uses_allow_pass_and_h3c_uses_permit(self):
        for vendor, expected in (("huawei", "port trunk allow-pass vlan"), ("h3c", "port trunk permit vlan")):
            with self.subTest(vendor=vendor):
                text = "sysname LAB\ninterface GigabitEthernet0/1\n port link-type trunk\n " + expected + " all\n#"
                value = issues(text, "VLAN-TRUNK-ALL", vendor)[0]
                self.assertIn(expected + " <APPROVED_VLAN_LIST>", value["command_templates"][0])
                self.assert_script(value["command_templates"][0], vendor)
                self.assertIn("增量", value["command_notes"])

    def test_global_and_interface_stp_disabled_findings_keep_their_own_scopes(self):
        for vendor in ("huawei", "h3c"):
            with self.subTest(vendor=vendor):
                values = issues("sysname LAB\nstp disable\ninterface GigabitEthernet0/1\n stp disable\n#", "STP-DISABLED", vendor)
                self.assertEqual(len(values), 2)
                global_issue = next(f for f in values if f["problem"].startswith("全局"))
                port_issue = next(f for f in values if f["problem"].startswith("接口"))
                self.assertEqual(global_issue["command_templates"], ["system-view\nstp enable\nreturn"])
                self.assertEqual(port_issue["command_templates"], ["system-view\ninterface GigabitEthernet0/1\nstp enable\nquit\nreturn"])

    def test_cisco_vlan_stp_restore_is_not_attached_to_a_disabled_interface(self):
        text = "hostname LAB\nno spanning-tree vlan 120\ninterface Gi0/1\n stp disable\n!"
        values = issues(text, "STP-DISABLED", "cisco")
        for value in values:
            if value["problem"].startswith("接口"):
                self.assertEqual(value["command_templates"], [])
            else:
                self.assertEqual(value["command_templates"], ["configure terminal\nspanning-tree vlan 120\nend"])

    def test_unknown_route_does_not_invent_a_next_hop_or_use_source_command(self):
        text = "hostname LAB\ninterface Vlan10\n ip address 192.0.2.10 255.255.255.0\n!\nip route 0.0.0.0 0.0.0.0 192.0.2.10"
        value = issues(text, "ROUTE-SELF-NEXTHOP")[0]
        self.assertEqual(value["commands"], [])
        self.assertIn("<VERIFIED_NEXT_HOP_AND_OPTIONS>", value["command_templates"][0])
        self.assertNotIn("192.0.2.10", value["command_templates"][0])

    def test_undefined_acl_retains_typed_reference_but_does_not_permit_everything(self):
        text = "hostname LAB\ninterface Gi0/1\n ip access-group LAB-ACL in"
        value = issues(text, "ACL-UNDEFINED")[0]
        self.assertEqual(value["commands"], [])
        self.assertIn("LAB-ACL", value["command_templates"][0])
        self.assertIn("<APPROVED_PERMIT_AND_DENY_RULES>", value["command_templates"][0])
        self.assertNotIn("permit any", "\n".join(value["command_templates"]))

    def test_hostile_interface_and_vty_names_cannot_add_cli_lines_or_tokens(self):
        for hostile in ("Gi0/1\nreload", "Gi0/1;reload", "Gi0/1 reload", "Gi0/1\rreload", "Gi0/1\x00reload"):
            with self.subTest(hostile=repr(hostile)):
                config = Config("ruijie", "explicit", "LAB")
                interface = Interface(hostile, 1, evidence=[Evidence(1, "interface " + hostile)])
                config.interfaces[hostile] = interface
                value = finding("STP-BPDU-FILTER", "stp", interface.evidence)
                value.affected_objects = [hostile]
                enrich_findings([value], config)
                self.assertEqual(value.commands, [])
        for hostile in ("line vty 0 4\nreload", "line vty 0 4;reload", "line vty 0 4 reload", "line vty 4 0", "line vty 0 999"):
            with self.subTest(hostile=repr(hostile)):
                config = Config("ruijie", "explicit", "LAB")
                config.management_lines = [ManagementLine(hostile, 1, evidence=[Evidence(1, hostile)])]
                value = finding("MGMT-VTY-TIMEOUT", evidence=config.management_lines[0].evidence)
                value.affected_objects = [hostile]
                enrich_findings([value], config)
                self.assertEqual(value.commands, [])

    def test_hostile_user_and_acl_names_are_not_replayed(self):
        config = Config("ruijie", "explicit", "LAB")
        value = finding("MGMT-CREDENTIAL", evidence=[Evidence(1, "username lab;reload password [REDACTED]")])
        enrich_findings([value], config)
        self.assertEqual(value.command_templates, [])
        config.interfaces["Gi0/1"] = Interface("Gi0/1", 2, acl_bindings={"in": "LAB;reload"}, evidence=[Evidence(2, "interface Gi0/1")])
        value = finding("ACL-UNDEFINED", "acl", [Evidence(2, "interface Gi0/1")])
        enrich_findings([value], config)
        self.assertEqual(value.command_templates, [])

    def test_http_vendor_syntax_uses_matching_observed_command_family(self):
        for vendor, enabled, disabled in (("ruijie", "ip http server", "no ip http server"), ("cisco", "ip http server", "no ip http server"), ("huawei", "http server enable", "undo http server enable"), ("h3c", "http enable", "undo http enable")):
            with self.subTest(vendor=vendor):
                value = issues(("hostname LAB" if vendor in {"cisco", "ruijie"} else "sysname LAB") + "\n" + enabled, "MGMT-HTTP", vendor)[0]
                self.assert_script(value["commands"][0], vendor)
                self.assertIn(disabled, value["commands"][0].splitlines())

    def test_unsupported_vendor_has_no_automatic_ios_fallback(self):
        value = finding("MGMT-SSHV1")
        value.commands = ["ip ssh version 2"]
        enrich_findings([value], Config("unknown", "unknown", "LAB"))
        self.assertEqual(value.commands, [])
        self.assertEqual(value.verification_commands, [])
        self.assertIn("厂商未识别", value.command_notes)

    def test_enrichment_is_repeatable_without_duplicate_scripts(self):
        config = parse_config("hostname LAB\nline vty 0 4\n transport input telnet", "ruijie")
        value = finding("MGMT-VTY-TELNET", evidence=config.management_lines[0].evidence)
        enrich_findings([value], config)
        first = value.to_dict()
        enrich_findings([value], config)
        self.assertEqual(first, value.to_dict())


if __name__ == "__main__":
    unittest.main()
