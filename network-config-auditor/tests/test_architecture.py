import json
import unittest

from netaudit.architecture import architecture_summary, check_architecture
from netaudit.parser import parse_config


class ArchitectureTests(unittest.TestCase):
    def findings(self, text, vendor="cisco"):
        config = parse_config(text, vendor)
        return config, check_architecture(config)

    def ids(self, findings):
        return [finding.rule_id for finding in findings]

    def test_missing_state_is_unknown_and_never_disabled(self):
        config, findings = self.findings("hostname X\ninterface Gi0/1\n switchport mode trunk")
        self.assertIsNone(config.stp["enabled"])
        self.assertIsNone(config.interfaces["Gi0/1"].stp_enabled)
        self.assertIsNone(config.interfaces["Gi0/1"].stp_edge)
        self.assertEqual(findings, [])
        summary = architecture_summary(config, findings)
        domains = {d["domain"]: d for d in summary["domains"]}
        self.assertEqual(set(domains), {"vlan", "stp", "ospf", "acl", "nat", "management_plane"})
        self.assertEqual(domains["stp"]["status"], "not-observed")
        self.assertTrue(all(isinstance(d["observed"], int) for d in domains.values()))

    def test_cisco_stp_vlan_last_setting_wins(self):
        config, findings = self.findings("hostname X\nspanning-tree mode rapid-pvst\n"
            "no spanning-tree vlan 10-12\nspanning-tree vlan 11\n")
        self.assertEqual(config.stp["mode"], "rapid-pvst")
        self.assertEqual(config.stp["vlan_enabled"], {10: False, 11: True, 12: False})
        self.assertEqual(self.ids(findings), ["STP-DISABLED"])
        self.assertIn("10, 12", findings[0].problem)
        self.assertEqual(findings[0].confidence, "confirmed-config")

    def test_cisco_explicit_portfast_trunk_and_bpdu_filter(self):
        config, findings = self.findings("hostname X\ninterface Gi0/1\n switchport mode trunk\n"
            " spanning-tree portfast trunk\n spanning-tree bpduguard enable\n spanning-tree bpdufilter enable")
        interface = config.interfaces["Gi0/1"]
        self.assertTrue(interface.stp_edge)
        self.assertTrue(interface.bpdu_guard)
        self.assertTrue(interface.bpdu_filter)
        self.assertEqual(set(self.ids(findings)), {"STP-EDGE-TRUNK", "STP-BPDU-FILTER"})
        self.assertTrue(all(f.confidence == "needs-review" for f in findings))

    def test_cisco_no_portfast_restores_unknown_not_disabled(self):
        config, findings = self.findings("hostname X\nspanning-tree portfast default\ninterface Gi0/1\n"
            " switchport mode trunk\n spanning-tree portfast trunk\n no spanning-tree portfast\n"
            " spanning-tree bpdufilter enable\n spanning-tree bpdufilter disable\n"
            " spanning-tree bpduguard enable\n no spanning-tree bpduguard enable")
        interface = config.interfaces["Gi0/1"]
        self.assertIsNone(interface.stp_edge)
        self.assertIsNone(interface.bpdu_guard)
        self.assertFalse(interface.bpdu_filter)
        self.assertEqual(findings, [])
        self.assertTrue(config.stp["edge_default"])

    def test_global_portfast_default_does_not_imply_edge_trunk(self):
        _, findings = self.findings("hostname X\nspanning-tree portfast default\ninterface Gi0/1\n switchport mode trunk")
        self.assertNotIn("STP-EDGE-TRUNK", self.ids(findings))

    def test_global_bpdu_filter_default_is_separate_review(self):
        _, findings = self.findings("hostname X\nspanning-tree portfast bpdufilter default")
        self.assertEqual(self.ids(findings), ["STP-BPDU-FILTER-DEFAULT"])
        self.assertEqual(findings[0].severity, "low")

    def test_huawei_stp_enable_disable_and_undo(self):
        config, findings = self.findings("sysname X\nstp disable\nstp enable\nstp mode mstp\n"
            "interface GE0/1\n port link-type trunk\n stp edged-port enable\n stp bpdu-filter enable\n"
            " undo stp bpdu-filter enable", "huawei")
        self.assertTrue(config.stp["enabled"])
        self.assertEqual(config.stp["mode"], "mstp")
        self.assertIsNone(config.interfaces["GE0/1"].bpdu_filter)
        self.assertEqual(self.ids(findings), ["STP-EDGE-TRUNK"])
        config, findings = self.findings("sysname X\nstp enable\nundo stp enable", "huawei")
        self.assertFalse(config.stp["enabled"])
        self.assertIn("STP-DISABLED", self.ids(findings))

    def test_h3c_edge_disable_and_stp_disable(self):
        config, findings = self.findings("sysname X\nstp enable\ninterface GE1/0/1\n port link-type trunk\n"
            " stp edged-port\n stp edged-port disable\n stp disable", "h3c")
        self.assertFalse(config.interfaces["GE1/0/1"].stp_edge)
        self.assertEqual(self.ids(findings), ["STP-DISABLED"])

    def test_shutdown_and_routed_ports_do_not_get_l2_alarm(self):
        _, findings = self.findings("hostname X\ninterface Gi0/1\n shutdown\n"
            " spanning-tree portfast trunk\n spanning-tree bpdufilter enable\n"
            "interface Gi0/2\n no switchport\n stp disable")
        self.assertEqual(findings, [])

    def test_unknown_stp_stays_unknown_with_warning(self):
        config, findings = self.findings("hostname X\nspanning-tree unusual-mode disabled\ninterface Gi0/1\n spanning-tree portfast strange")
        self.assertIsNone(config.stp["enabled"])
        self.assertIsNone(config.interfaces["Gi0/1"].stp_edge)
        self.assertEqual(findings, [])
        self.assertEqual(len(config.warnings), 2)
        self.assertEqual(architecture_summary(config, findings)["domains"][1]["status"], "needs-review")

    def test_cisco_ospf_process_network_area_and_passive(self):
        config, findings = self.findings("hostname X\nrouter ospf 10\n router-id 192.0.2.1\n"
            " network 10.0.0.0 0.0.0.255 area 0\n area 0 authentication message-digest\n"
            " passive-interface default\n no passive-interface Gi0/1\ninterface Gi0/1\n ip address 10.0.0.1 255.255.255.0")
        process = config.routing_processes[0]
        self.assertEqual(process["router_id"], "192.0.2.1")
        self.assertEqual(process["networks"][0]["prefix"], "10.0.0.0/24")
        self.assertEqual(process["areas"]["0"]["authentication"], "message-digest")
        self.assertTrue(process["passive_default"])
        self.assertFalse(process["passive_interfaces"]["Gi0/1"])
        self.assertEqual(findings, [])
        self.assertEqual(config.unsupported_count, 0)

    def test_huawei_area_quit_restores_process_context(self):
        config, findings = self.findings("sysname X\nospf 10 router-id 192.0.2.10\n area 0.0.0.1\n"
            "  network 10.0.0.0 0.0.0.255\n  authentication-mode md5 1 cipher TopSecretA\n quit\n"
            " silent-interface all\n undo silent-interface GE0/1\n#\ninterface GE0/1\n ip address 10.0.0.1 24", "huawei")
        process = config.routing_processes[0]
        self.assertEqual(process["areas"]["1"]["authentication"], "md5")
        self.assertTrue(process["passive_default"])
        self.assertFalse(process["passive_interfaces"]["GE0/1"])
        self.assertNotIn("TopSecretA", json.dumps(config.to_dict()))
        self.assertEqual(config.unsupported_count, 0)
        self.assertEqual(findings, [])

    def test_h3c_ospf_header_vrf_and_interface_binding(self):
        config, findings = self.findings("sysname X\nospf 2 vpn-instance BLUE router-id 192.0.2.2\n"
            " area 0\n  authentication-mode hmac-sha-256 1 cipher SuperSecretB\n#\n"
            "interface Vlan-interface20\n ip binding vpn-instance BLUE\n ospf enable 2 area 0\n"
            " ospf authentication-mode md5 7 cipher SuperSecretC", "h3c")
        self.assertEqual(config.routing_processes[0]["vrf"], "BLUE")
        interface = config.interfaces["Vlan-interface20"]
        self.assertEqual(interface.ospf_binding["process_id"], "2")
        self.assertEqual(interface.ospf_authentication, "md5")
        self.assertNotIn("SuperSecret", json.dumps(config.to_dict()))
        self.assertEqual(findings, [])

    def test_vrp_implicit_process_id_and_cisco_missing_id(self):
        config, _ = self.findings("sysname X\nospf router-id 192.0.2.1\n silent-interface all", "huawei")
        self.assertEqual(config.routing_processes[0]["process_id"], "1")
        config, _ = self.findings("hostname X\nrouter ospf")
        self.assertEqual(config.routing_processes, [])
        self.assertTrue(config.warnings)

    def test_vty_authentication_evidence_never_stores_auth_tail_secret(self):
        config, _ = self.findings("sysname X\nuser-interface vty 0 4\n authentication-mode password cipher HiddenAuthTail", "huawei")
        self.assertNotIn("HiddenAuthTail", json.dumps(config.to_dict()))

    def test_ospf_keys_do_not_enable_authentication_and_are_redacted(self):
        config, findings = self.findings("hostname X\nrouter ospf 1\n network 10.0.0.0 0.0.0.255 area 0\n"
            "interface Gi0/1\n ip address 10.0.0.1 255.255.255.0\n ip ospf message-digest-key 1 md5 HideThisKey")
        self.assertIsNone(config.interfaces["Gi0/1"].ospf_authentication)
        self.assertEqual(self.ids(findings), ["OSPF-AUTH-REVIEW"])
        self.assertNotIn("HideThisKey", json.dumps(config.to_dict()))
        self.assertEqual(findings[0].confidence, "needs-review")

    def test_ospf_interface_authentication_override_and_inheritance(self):
        text = "hostname X\nrouter ospf 1\n area 0 authentication message-digest\ninterface Gi0/1\n ip ospf 1 area 0\n"
        config, findings = self.findings(text + " ip ospf authentication null")
        self.assertEqual(config.interfaces["Gi0/1"].ospf_authentication, "none")
        self.assertIn("OSPF-AUTH-REVIEW", self.ids(findings))
        config, findings = self.findings(text + " ip ospf authentication null\n no ip ospf authentication")
        self.assertIsNone(config.interfaces["Gi0/1"].ospf_authentication)
        self.assertEqual(findings, [])

    def test_ospf_area_authentication_undo_restores_unknown(self):
        config, findings = self.findings("sysname X\nospf 1\n area 0\n"
            "  authentication-mode md5 1 cipher secret\n  undo authentication-mode", "huawei")
        self.assertIsNone(config.routing_processes[0]["areas"]["0"]["authentication"])
        self.assertEqual(self.ids(findings), ["OSPF-AUTH-REVIEW"])

    def test_ospf_area_removal_discards_associated_networks(self):
        config, _ = self.findings("sysname X\nospf 1\n area 0\n network 10.0.0.0 0.0.0.255\n"
            " quit\n undo area 0", "h3c")
        self.assertEqual(config.routing_processes[0]["areas"], {})
        self.assertEqual(config.routing_processes[0]["networks"], [])

    def test_repeated_process_header_merges_and_last_router_id_wins(self):
        config, findings = self.findings("hostname X\nrouter ospf 1\n router-id 192.0.2.1\n"
            " network 10.0.0.0 0.0.0.255 area 0\n!\nrouter ospf 1\n router-id 192.0.2.2\n"
            " no network 10.0.0.0 0.0.0.255 area 0\n area 0 authentication message-digest")
        self.assertEqual(len(config.routing_processes), 1)
        self.assertEqual(config.routing_processes[0]["router_id"], "192.0.2.2")
        self.assertEqual(config.routing_processes[0]["networks"], [])
        self.assertNotIn("OSPF-DUPLICATE-ROUTER-ID", self.ids(findings))

    def test_process_and_interface_binding_removal(self):
        config, findings = self.findings("hostname X\nrouter ospf 1\n router-id 192.0.2.1\n"
            "no router ospf 1\ninterface Gi0/1\n ip ospf 1 area 0\n no ip ospf 1 area 0")
        self.assertEqual(config.routing_processes, [])
        self.assertIsNone(config.interfaces["Gi0/1"].ospf_binding)
        self.assertEqual(findings, [])

    def test_router_id_removal_returns_unknown_not_zero(self):
        config, findings = self.findings("hostname X\nrouter ospf 1\n router-id 0.0.0.0\n no router-id\n passive-interface default")
        self.assertIsNone(config.routing_processes[0]["router_id"])
        self.assertNotIn("OSPF-ROUTER-ID", self.ids(findings))

    def test_invalid_router_id_flagged_with_original_line(self):
        for router_id in ("not-an-ip", "0.0.0.0", "999.0.0.1"):
            with self.subTest(router_id=router_id):
                _, findings = self.findings("hostname X\nrouter ospf 1\n router-id " + router_id)
                finding = next(f for f in findings if f.rule_id == "OSPF-ROUTER-ID")
                self.assertEqual(finding.confidence, "confirmed-config")
                self.assertEqual(finding.evidence[0].line, 3)

    def test_duplicate_router_id_only_within_same_vrf_and_review(self):
        _, findings = self.findings("hostname X\nrouter ospf 1\n router-id 192.0.2.1\n"
            "router ospf 2\n router-id 192.0.2.1\nrouter ospf 3 vrf BLUE\n router-id 192.0.2.1")
        duplicates = [f for f in findings if f.rule_id == "OSPF-DUPLICATE-ROUTER-ID"]
        self.assertEqual(len(duplicates), 1)
        self.assertEqual(len(duplicates[0].evidence), 2)
        self.assertEqual(duplicates[0].confidence, "needs-review")

    def test_broad_network_is_selection_not_advertisement(self):
        _, findings = self.findings("hostname X\nrouter ospf 1\n network 0.0.0.0 255.255.255.255 area 0")
        finding = next(f for f in findings if f.rule_id == "OSPF-BROAD-NETWORK")
        self.assertIn("选择接口", finding.risk)
        self.assertIn("不等同于发布", finding.risk)
        self.assertEqual(finding.confidence, "needs-review")

    def test_noncontiguous_wildcard_retained_warned_not_broad_cidr(self):
        config, findings = self.findings("hostname X\nrouter ospf 1\n network 10.0.0.0 0.255.0.255 area 0")
        network = config.routing_processes[0]["networks"][0]
        self.assertEqual(network["wildcard"], "0.255.0.255")
        self.assertIsNone(network["prefix"])
        self.assertTrue(config.warnings)
        self.assertNotIn("OSPF-BROAD-NETWORK", self.ids(findings))

    def test_explicit_passive_default_and_exception(self):
        base = "hostname X\nrouter ospf 1\n passive-interface default\n network 10.0.0.0 0.0.0.255 area 0\n"
        _, findings = self.findings(base)
        self.assertNotIn("OSPF-AUTH-REVIEW", self.ids(findings))
        _, findings = self.findings(base + " no passive-interface Gi0/1\ninterface Gi0/1\n ip address 10.0.0.1 255.255.255.0")
        self.assertIn("OSPF-AUTH-REVIEW", self.ids(findings))

    def test_unmodeled_authentication_warns_and_secret_not_retained(self):
        config, findings = self.findings("sysname X\nospf 1\n area 0\n authentication-mode future-alg 1 cipher HiddenSecret", "huawei")
        self.assertTrue(config.warnings)
        self.assertNotIn("HiddenSecret", json.dumps(config.to_dict()))
        self.assertIn("OSPF-AUTH-REVIEW", self.ids(findings))

    def test_other_routing_protocols_keep_original_coverage_warning(self):
        config, findings = self.findings("hostname X\nrouter bgp 65000\n neighbor 192.0.2.1 remote-as 65001")
        self.assertEqual(config.routing_processes[0]["protocol"], "bgp")
        self.assertTrue(config.warnings)
        self.assertEqual(findings, [])

    def test_vlan_acl_nat_are_summarized_without_duplicate_findings(self):
        config, findings = self.findings("hostname X\nvlan 10\n!\nip access-list extended TEST\n permit ip any any\n"
            "!\nip nat inside source static 10.0.0.2 192.0.2.2\ninterface Gi0/1\n switchport mode trunk\n switchport trunk allowed vlan all")
        self.assertEqual(findings, [])
        domains = {d["domain"]: d for d in architecture_summary(config, findings)["domains"]}
        for domain in ("vlan", "acl", "nat"):
            self.assertEqual(domains[domain]["status"], "checked")
            self.assertGreater(domains[domain]["observed"], 0)

    def test_summary_accepts_finding_objects_or_wire_dicts(self):
        config, findings = self.findings("hostname X\nno spanning-tree vlan 10")
        self.assertEqual(architecture_summary(config, findings),
                         architecture_summary(config, [f.to_dict() for f in findings]))

    def test_ai_safe_fields_do_not_contain_configuration_values(self):
        _, findings = self.findings("hostname SensitiveDevice\ninterface SensitivePort\n switchport mode trunk\n"
            " spanning-tree portfast trunk\n spanning-tree bpdufilter enable\nrouter ospf 1\n"
            " router-id 999.0.0.1\n network 10.0.0.0 0.255.255.255 area 0")
        safe = json.dumps([{k: getattr(f, k) for k in ("title", "risk", "recommendation")} for f in findings])
        for secret in ("SensitiveDevice", "SensitivePort", "999.0.0.1", "10.0.0.0"):
            self.assertNotIn(secret, safe)


if __name__ == "__main__":
    unittest.main()
