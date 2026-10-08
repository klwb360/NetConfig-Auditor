import json
import unittest

from netaudit import audit, parse_config
from netaudit.reports import render


def findings(text, vendor="cisco", rule=None):
    values = audit(parse_config(text, vendor))["findings"]
    return [f for f in values if rule is None or f["rule_id"] == rule]


class RuleTests(unittest.TestCase):
    def test_disabled_http_not_reported(self):
        self.assertEqual(findings("hostname X\nno ip http server", rule="MGMT-HTTP"), [])

    def test_http_last_command_wins(self):
        self.assertEqual(findings("hostname X\nip http server\nno ip http server", rule="MGMT-HTTP"), [])
        self.assertEqual(len(findings("hostname X\nno ip http server\nip http server", rule="MGMT-HTTP")), 1)

    def test_http_absence_not_guessed_as_enabled(self):
        self.assertEqual(findings("hostname X", rule="MGMT-HTTP"), [])

    def test_huawei_disabled_telnet(self):
        self.assertEqual(findings("sysname X\ntelnet server enable\nundo telnet server enable", "huawei", "MGMT-TELNET-SERVER"), [])

    def test_mixed_vty_ranges_checked_independently(self):
        text = "hostname X\nline vty 0 4\n transport input ssh\n!\nline vty 5 15\n transport input telnet ssh"
        fs = findings(text, rule="MGMT-VTY-TELNET")
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]["evidence"][0]["line"], 5)

    def test_vty_none_not_reported_as_telnet_or_no_source(self):
        fs = findings("hostname X\nline vty 0 4\n transport input none")
        self.assertFalse(any(f["rule_id"] in ("MGMT-VTY-TELNET", "MGMT-VTY-SOURCE") for f in fs))

    def test_no_auth_and_timeout(self):
        fs = findings("hostname X\nline vty 0 4\n transport input ssh\n no login\n exec-timeout 0 0")
        self.assertIn("critical", [f["severity"] for f in fs])
        self.assertIn("MGMT-VTY-TIMEOUT", [f["rule_id"] for f in fs])

    def test_ssh_retry_integer_conversion(self):
        self.assertFalse(findings("hostname X\nip ssh authentication-retries 3", rule="MGMT-SSH-RETRIES"))
        self.assertTrue(findings("hostname X\nip ssh authentication-retries 10", rule="MGMT-SSH-RETRIES"))
        self.assertTrue(findings("hostname X\nip ssh authentication-retries abc", rule="PARSE-NUMBER"))

    def test_password_hash_vs_type7(self):
        for kind in ("5", "8", "9"):
            self.assertFalse(findings(f"hostname X\nusername test secret {kind} VALUE", rule="MGMT-CREDENTIAL"))
        for kind in ("0", "7", "simple", "plain"):
            self.assertTrue(findings(f"hostname X\nusername test password {kind} VALUE", rule="MGMT-CREDENTIAL"))

    def test_vty_password_type7_reported(self):
        fs = findings("hostname X\nline vty 0 4\n transport input ssh\n password 7 SENSITIVEVTYX\n login", rule="MGMT-CREDENTIAL")
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]["evidence"][0]["line"], 4)
        self.assertNotIn("SENSITIVEVTYX", json.dumps(fs))

    def test_credentials_removed_from_inventory_and_exports(self):
        text = "hostname X\nusername a secret 9 sensitiveHashZ\nsnmp-server community sensitiveCommunityZ RO\ninterface Gi0/1\n radius-server key 7 sensitiveRadiusZ\n!\nline vty 0 4\n password 7 sensitiveVTYZ"
        result = audit(parse_config(text, "cisco"))
        for fmt in ("json", "md", "html"):
            out = render(result, fmt)
            for secret in ("sensitiveHashZ", "sensitiveCommunityZ", "sensitiveRadiusZ", "sensitiveVTYZ"):
                self.assertNotIn(secret, out)
            self.assertIn("REDACTED", out)

    def test_huawei_community_and_authkey_redacted(self):
        c = parse_config("sysname X\nsnmp-agent community read cipher TOPSECRETX\nntp-service authentication-keyid 1 authentication-mode md5 cipher KEYX", "huawei")
        self.assertNotIn("TOPSECRETX", json.dumps(c.to_dict()))
        self.assertNotIn("KEYX", json.dumps(c.to_dict()))

    def test_acl_shadow_detected_by_order(self):
        fs = findings("hostname X\nip access-list extended A\n 10 permit ip any any\n 20 deny tcp any host 10.0.0.1 eq 23", rule="ACL-SHADOW")
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]["evidence"][0]["line"], 3)

    def test_shadowed_permit_any_does_not_generate_risk(self):
        text = "hostname X\nip access-list extended A\n 10 deny ip any any\n 20 permit ip any any\n!\ninterface Gi0/1\n ip access-group A in"
        self.assertTrue(findings(text, rule="ACL-SHADOW"))
        self.assertFalse(findings(text, rule="ACL-PERMIT-ANY"))

    def test_unknown_acl_options_disable_shadow_inference(self):
        text = "hostname X\nip access-list extended A\n permit tcp any any established\n deny tcp any any eq 23"
        self.assertFalse(findings(text, rule="ACL-SHADOW"))

    def test_auto_order_disables_shadow_inference(self):
        text = "sysname X\nacl number 3000 match-order auto\n rule 5 permit ip\n rule 10 deny tcp"
        self.assertFalse(findings(text, "huawei", "ACL-SHADOW"))

    def test_tcp_does_not_cover_all_ip(self):
        text = "hostname X\nip access-list extended A\n permit tcp any any\n deny ip any any"
        self.assertFalse(findings(text, rule="ACL-SHADOW"))

    def test_host_does_not_cover_subnet(self):
        text = "hostname X\nip access-list extended A\n permit ip host 10.0.0.1 any\n deny ip 10.0.0.0 0.0.0.255 any"
        self.assertFalse(findings(text, rule="ACL-SHADOW"))

    def test_restricted_port_does_not_cover_other_port(self):
        text = "hostname X\nip access-list extended A\n permit tcp any any eq 80\n deny tcp any any eq 443"
        self.assertFalse(findings(text, rule="ACL-SHADOW"))

    def test_nat_selection_acl_not_high_risk_filter(self):
        fs = findings("hostname X\naccess-list 10 permit any\nip nat inside source list 10 interface Gi0/1 overload", rule="ACL-PERMIT-ANY")
        self.assertEqual(fs[0]["severity"], "low")
        self.assertIn("NAT 选流", fs[0]["problem"])

    def test_bound_acl_has_high_severity(self):
        text = "hostname X\nip access-list extended A\n permit ip any any\n!\ninterface Gi0/1\n ip access-group A in"
        self.assertEqual(findings(text, rule="ACL-PERMIT-ANY")[0]["severity"], "high")

    def test_undefined_acl_reported(self):
        self.assertTrue(findings("hostname X\ninterface Gi0/1\n ip access-group MISSING in", rule="ACL-UNDEFINED"))

    def test_duplicate_addresses_scoped_by_vrf(self):
        text = "hostname X\ninterface Gi0/1\n ip address 10.0.0.1 255.255.255.0\n!\ninterface Gi0/2\n ip address 10.0.0.1 255.255.255.0"
        self.assertTrue(findings(text, rule="IF-DUPLICATE-IP"))
        self.assertFalse(findings(text + "\n vrf forwarding BLUE", rule="IF-DUPLICATE-IP"))

    def test_route_to_self_and_valid_ecmp(self):
        self.assertTrue(findings("hostname X\ninterface Gi0/1\n ip address 10.0.0.1 255.255.255.0\n!\nip route 0.0.0.0 0.0.0.0 10.0.0.1", rule="ROUTE-SELF-NEXTHOP"))
        fs = findings("hostname X\nip route 0.0.0.0 0.0.0.0 10.0.0.1\nip route 0.0.0.0 0.0.0.0 10.0.0.2")
        self.assertFalse(fs)

    def test_nat_static_needs_review_not_exposure_assertion(self):
        fs = findings("hostname X\nip nat inside source static 10.0.0.2 192.0.2.2", rule="NAT-INBOUND-MAPPING")
        self.assertEqual(fs[0]["confidence"], "needs-review")
        self.assertIn("不能确认", fs[0]["risk"])

    def test_html_and_markdown_escape_untrusted_text(self):
        r = audit(parse_config("hostname <script>alert(1)</script>\ninterface Gi0/1\n ip access-group <img/src=x/onerror=alert(1)> in", "cisco"))
        for fmt in ("html", "md"):
            out = render(r, fmt)
            self.assertNotIn("<script>", out)
            self.assertNotIn("<img/src", out)
        self.assertIn("&lt;script&gt;", render(r, "html"))

    def test_plugin_state_does_not_accumulate(self):
        c = parse_config("hostname X\nip http server", "cisco")
        self.assertEqual(audit(c), audit(c))

    def test_missing_vlan_group_keeps_all_ports_roles_and_evidence(self):
        text = ("hostname X\ninterface Gi0/1\n switchport access vlan 20\n"
                " switchport trunk native vlan 20\n!\ninterface Gi0/2\n"
                " switchport access vlan 20")
        fs = findings(text, rule="VLAN-UNDEFINED")
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]["occurrences"], 2)
        self.assertEqual(fs[0]["affected_objects"], ["Gi0/1", "Gi0/2"])
        self.assertIn("VLAN 20", fs[0]["problem"])
        self.assertIn("Gi0/1（Access、native/PVID）", fs[0]["problem"])
        self.assertIn("Gi0/2（Access）", fs[0]["problem"])
        self.assertEqual({e["line"] for e in fs[0]["evidence"]}, {2, 3, 4, 6, 7})

    def test_defined_vlan_not_reported_across_multiple_ports(self):
        text = ("hostname X\nvlan 20\n name USERS\n!\ninterface Gi0/1\n"
                " switchport access vlan 20\n!\ninterface Gi0/2\n switchport access vlan 20")
        self.assertEqual(findings(text, rule="VLAN-UNDEFINED"), [])

    def test_distinct_missing_vlan_ids_remain_distinct(self):
        text = ("hostname X\ninterface Gi0/1\n switchport access vlan 20\n"
                " switchport trunk native vlan 30\n!\ninterface Gi0/2\n"
                " switchport access vlan 20")
        fs = findings(text, rule="VLAN-UNDEFINED")
        self.assertEqual(len(fs), 2)
        self.assertEqual([f["occurrences"] for f in fs], [2, 1])
        self.assertIn("VLAN 20", fs[0]["problem"])
        self.assertIn("VLAN 30", fs[1]["problem"])

    def test_grouped_report_counters_preserve_original_occurrences(self):
        text = ("hostname X\ninterface Gi0/1\n switchport access vlan 20\n!\n"
                "interface Gi0/2\n switchport access vlan 20")
        result = audit(parse_config(text, "cisco"))
        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["summary"]["severity"]["medium"], 1)
        self.assertEqual(result["summary"]["occurrences_total"], 2)
        self.assertEqual(result["summary"]["merged_count"], 1)

    def test_vty_unknown_and_source_groups_preserve_every_range(self):
        text = "hostname X\nline vty 0 4\n!\nline vty 5 15"
        result = audit(parse_config(text, "cisco"))
        for rule in ("MGMT-VTY-UNKNOWN", "MGMT-VTY-SOURCE"):
            rows = [f for f in result["findings"] if f["rule_id"] == rule]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["occurrences"], 2)
            self.assertEqual(rows[0]["affected_objects"], ["line vty 0 4", "line vty 5 15"])
            self.assertEqual({e["line"] for e in rows[0]["evidence"]}, {2, 4})
            self.assertEqual(rows[0]["confidence"], "needs-review")
            self.assertIn("line vty 0 4", rows[0]["problem"])
            self.assertIn("line vty 5 15", rows[0]["problem"])

    def test_grouped_credentials_keep_all_accounts_and_redacted_lines(self):
        text = ("hostname X\nusername alice password 0 PrivateAliceSecret\n"
                "username bob password 7 PrivateBobSecret")
        fs = findings(text, rule="MGMT-CREDENTIAL")
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]["occurrences"], 2)
        self.assertEqual(fs[0]["affected_objects"], ["账号 alice", "账号 bob"])
        self.assertEqual({e["line"] for e in fs[0]["evidence"]}, {2, 3})
        self.assertNotIn("PrivateAliceSecret", json.dumps(fs))
        self.assertNotIn("PrivateBobSecret", json.dumps(fs))

    def test_snmp_read_and_write_severity_do_not_merge(self):
        fs = findings("hostname X\nsnmp-server community ReadOnlySecret RO\n"
                      "snmp-server community ReadWriteSecret RW", rule="MGMT-SNMP-COMMUNITY")
        self.assertEqual(len(fs), 2)
        self.assertEqual({f["severity"] for f in fs}, {"high", "medium"})


if __name__ == "__main__":
    unittest.main()
