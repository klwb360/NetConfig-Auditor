"""Partial route/NAT parsing must not establish a complete configuration fact."""

import unittest

from netaudit import audit, parse_config
from netaudit.model import Evidence, NAT, Route


class ParserCompletenessTests(unittest.TestCase):
    def parse(self, command, vendor="cisco"):
        header = "hostname SAMPLE" if vendor in ("cisco", "ruijie") else "sysname SAMPLE"
        return parse_config(header + "\n" + command, vendor)

    def assert_incomplete(self, cfg, line=2):
        self.assertGreater(cfg.unsupported_count, 0)
        self.assertEqual(cfg.warnings[0]["line"], line)
        finding = next(f for f in audit(cfg)["findings"] if f["rule_id"] == "PARSE-INCOMPLETE")
        self.assertEqual(finding["confidence"], "needs-review")
        self.assertFalse(finding["commands"])

    def test_route_modifiers_are_retained_as_incomplete(self):
        for vendor, prefix, suffix in (
            ("cisco", "ip route", "track 10"),
            ("cisco", "ip route", "UNKNOWN_TAIL"),
            ("cisco", "ip route", "global"),
            ("ruijie", "ip route", "track 10"),
            ("huawei", "ip route-static", "vpn-instance BLUE"),
            ("h3c", "ip route-static", "track 10"),
        ):
            with self.subTest(vendor=vendor, suffix=suffix):
                cfg = self.parse(f"{prefix} 10.0.0.0 255.255.255.0 192.0.2.1 {suffix}", vendor)
                self.assert_incomplete(cfg)
                self.assertFalse(cfg.routes[0].complete)
                self.assertEqual(cfg.routes[0].unparsed_tokens, suffix.split())

    def test_partial_self_route_cannot_generate_route_conclusion_or_template(self):
        cfg = self.parse("interface Gi0/1\n ip address 192.0.2.1 255.255.255.0\n!\n"
                         "ip route 10.0.0.0 255.255.255.0 192.0.2.1 track 10")
        self.assert_incomplete(cfg, 5)
        self.assertFalse(any(f["rule_id"] == "ROUTE-SELF-NEXTHOP" for f in audit(cfg)["findings"]))

    def test_supported_routes_consume_the_whole_command(self):
        for vendor, command, distance in (
            ("cisco", "ip route vrf BLUE 10.0.0.0/24 Gi0/1 192.0.2.1 200", 200),
            ("ruijie", "ip route 10.0.0.0 255.255.255.0 Null0", None),
            ("huawei", "ip route-static vpn-instance BLUE 10.0.0.0 24 192.0.2.1 preference 100", 100),
            ("h3c", "ip route-static 10.0.0.0 24 GigabitEthernet1/0/1 192.0.2.1 preference 100", 100),
        ):
            with self.subTest(vendor=vendor):
                cfg = self.parse(command, vendor)
                self.assertEqual(cfg.unsupported_count, 0)
                self.assertTrue(cfg.routes[0].complete)
                self.assertEqual(cfg.routes[0].unparsed_tokens, [])
                self.assertEqual(cfg.routes[0].distance, distance)

    def test_invalid_route_hops_and_distances_are_not_complete_routes(self):
        for hop in ("999.0.0.1", "192.0.2.999", "192.0.2.1 0", "192.0.2.1 256", "192.0.2.1 -1"):
            with self.subTest(hop=hop):
                cfg = self.parse("ip route 10.0.0.0 255.255.255.0 " + hop)
                self.assert_incomplete(cfg)
                self.assertFalse(any(getattr(r, "complete", True) for r in cfg.routes))

    def test_route_and_pool_netmask_cannot_be_interpreted_as_acl_wildcard(self):
        for command in ("ip route 10.0.0.0 0.0.0.255 192.0.2.1",
                        "ip route 10.0.0.0/0.0.0.255 192.0.2.1",
                        "ip nat pool PUBLIC 192.0.2.2 192.0.2.5 netmask 0.0.0.255"):
            with self.subTest(command=command):
                cfg = self.parse(command)
                self.assert_incomplete(cfg)
                self.assertFalse(any(r.complete for r in cfg.routes))
                self.assertFalse(cfg.nat_pools)

    def test_route_unsupported_removal_does_not_delete_known_route(self):
        for vendor, prefix, inverse in (("cisco", "ip route", "no"), ("h3c", "ip route-static", "undo")):
            with self.subTest(vendor=vendor):
                route = prefix + " 10.0.0.0 255.255.255.0 192.0.2.1"
                cfg = self.parse(route + "\n" + inverse + " " + route + " track 10", vendor)
                self.assert_incomplete(cfg, 3)
                self.assertEqual(len(cfg.routes), 1)

    def test_route_removal_matches_distance(self):
        route = "ip route 10.0.0.0 255.255.255.0 192.0.2.1"
        cfg = self.parse(route + " 100\n" + route + " 200\nno " + route + " 100")
        self.assertEqual([r.distance for r in cfg.routes], [200])
        self.assertEqual(cfg.unsupported_count, 0)

    def test_route_modifiers_cannot_be_guessed_as_interfaces_or_duplicate_distances(self):
        for vendor, command in (
            ("cisco", "ip route 10.0.0.0 24 track10"),
            ("cisco", "ip route 10.0.0.0 24 UNKNOWN_INTERFACE0"),
            ("h3c", "ip route-static 10.0.0.0 24 192.0.2.1 100 preference 200"),
        ):
            with self.subTest(command=command):
                cfg = self.parse(command, vendor)
                self.assert_incomplete(cfg)
                self.assertFalse(any(r.complete for r in cfg.routes))

    def test_nat_static_interface_form_is_never_an_interface_literal_mapping(self):
        for vendor in ("cisco", "ruijie"):
            with self.subTest(vendor=vendor):
                cfg = self.parse("ip nat inside source static tcp 10.0.0.2 22 interface Gi0/1 2222", vendor)
                self.assert_incomplete(cfg)
                nat = cfg.nat[0]
                self.assertFalse(nat.complete)
                self.assertIsNone(nat.outside)
                self.assertEqual(nat.outside_interface, "Gi0/1")
                self.assertEqual(nat.outside_port, "2222")
                self.assertFalse(any(f["rule_id"] == "NAT-INBOUND-MAPPING" for f in audit(cfg)["findings"]))

    def test_nat_modifiers_are_not_silently_discarded(self):
        for suffix in ("vrf BLUE", "route-map POLICY", "extendable", "UNKNOWN_TAIL"):
            with self.subTest(suffix=suffix):
                cfg = self.parse("ip nat inside source static 10.0.0.2 192.0.2.2 " + suffix)
                self.assert_incomplete(cfg)
                self.assertFalse(cfg.nat[0].complete)
                self.assertEqual(cfg.nat[0].unparsed_tokens, suffix.split())

    def test_invalid_or_unmodeled_nat_addresses_and_ports_never_create_a_mapping(self):
        for value in (
            "999.0.0.1 192.0.2.2", "10.0.0.2 192.0.2.999",
            "tcp 10.0.0.2 0 192.0.2.2 2222", "udp 10.0.0.2 53 192.0.2.2 65536",
            "tcp 10.0.0.2 ssh 192.0.2.2 2222", "tcp 10.0.0.2 22 192.0.2.2",
        ):
            with self.subTest(value=value):
                cfg = self.parse("ip nat inside source static " + value)
                self.assert_incomplete(cfg)
                self.assertFalse(any(f["rule_id"] == "NAT-INBOUND-MAPPING" for f in audit(cfg)["findings"]))

    def test_supported_nat_forms_still_parse_completely(self):
        for command in (
            "ip nat inside source static 10.0.0.2 192.0.2.2",
            "ip nat inside source static tcp 10.0.0.2 22 192.0.2.2 2222",
            "ip nat inside source static udp 10.0.0.2 53 192.0.2.2 53",
            "ip nat inside source list SELECT interface Gi0/1 overload",
            "ip nat inside source list SELECT pool PUBLIC overload",
        ):
            with self.subTest(command=command):
                cfg = self.parse(command)
                self.assertEqual(cfg.unsupported_count, 0)
                self.assertTrue(cfg.nat[0].complete)

    def test_partial_nat_reference_does_not_generate_a_complete_acl_or_pool_conclusion(self):
        cfg = self.parse("ip nat inside source list MISSING pool UNKNOWN vrf BLUE")
        self.assert_incomplete(cfg)
        self.assertFalse(any(f["rule_id"] in ("NAT-ACL-UNDEFINED", "NAT-POOL-UNDEFINED")
                             for f in audit(cfg)["findings"]))

    def test_incomplete_nat_does_not_change_acl_filter_risk_to_nat_only(self):
        cfg = self.parse("access-list 10 permit any\n"
                         "ip nat inside source list 10 pool UNKNOWN vrf BLUE")
        finding = next(f for f in audit(cfg)["findings"] if f["rule_id"] == "ACL-PERMIT-ANY")
        self.assertNotIn("NAT 选流", finding["problem"])

    def test_nat_removal_does_not_remove_prefix_matching_or_unsupported_mapping(self):
        base = "ip nat inside source static 10.0.0.2 192.0.2.2"
        cfg = self.parse(base + "2\nno " + base)
        self.assertEqual(len(cfg.nat), 1)
        self.assertEqual(cfg.nat[0].outside, "192.0.2.22")
        for tail in (" UNKNOWN_TAIL", " vrf BLUE"):
            with self.subTest(tail=tail):
                cfg = self.parse(base + "\nno " + base + tail)
                self.assert_incomplete(cfg, 3)
                self.assertEqual(len(cfg.nat), 1)

    def test_nat_pool_removal_does_not_accept_arbitrary_tail(self):
        cfg = self.parse("ip nat pool PUBLIC 192.0.2.2 192.0.2.5 netmask 255.255.255.0\n"
                         "no ip nat pool PUBLIC UNKNOWN_TAIL")
        self.assert_incomplete(cfg, 3)
        self.assertIn("PUBLIC", cfg.nat_pools)

    def test_invalid_pool_addresses_and_unknown_tail_are_not_defined(self):
        for tail in ("999.0.0.1 192.0.2.5 netmask 255.255.255.0",
                     "192.0.2.5 192.0.2.2 netmask 255.255.255.0",
                     "192.0.2.2 192.0.2.5 netmask 255.0.255.0",
                     "192.0.2.2 192.0.2.5 netmask 255.255.255.0 UNKNOWN_TAIL"):
            with self.subTest(tail=tail):
                cfg = self.parse("ip nat pool PUBLIC " + tail)
                self.assert_incomplete(cfg)
                self.assertNotIn("PUBLIC", cfg.nat_pools)

    def test_huawei_nat_server_validates_and_consumes_all_fields(self):
        base = "interface GigabitEthernet0/0/1\n nat server protocol tcp global 192.0.2.2 2222 inside 10.0.0.2 22"
        cfg = self.parse(base, "huawei")
        self.assertEqual(cfg.unsupported_count, 0)
        self.assertTrue(cfg.nat[0].complete)
        self.assertEqual(cfg.nat[0].outside_port, "2222")
        self.assertEqual(cfg.nat[0].inside, "10.0.0.2:22")
        for suffix in (" vpn-instance BLUE", " UNKNOWN_TAIL"):
            with self.subTest(suffix=suffix):
                cfg = self.parse(base + suffix, "huawei")
                self.assert_incomplete(cfg, 3)
                self.assertFalse(cfg.nat[0].complete)
        for outside in ("192.0.2.999", "192.0.2.2 65536"):
            with self.subTest(outside=outside):
                cfg = self.parse("interface GigabitEthernet0/0/1\n nat server protocol tcp global "
                                 + outside + " inside 10.0.0.2 22", "huawei")
                self.assert_incomplete(cfg, 3)
                self.assertFalse(any(f["rule_id"] == "NAT-INBOUND-MAPPING" for f in audit(cfg)["findings"]))

    def test_huawei_nat_server_preserves_protocol_mapping_and_default_inside_port(self):
        for command, inside, port in (
            ("nat server protocol tcp global 192.0.2.2 inside 10.0.0.2", "10.0.0.2", None),
            ("nat server protocol tcp global 192.0.2.2 2222 inside 10.0.0.2", "10.0.0.2:2222", "2222"),
        ):
            with self.subTest(command=command):
                cfg = self.parse("interface GigabitEthernet0/0/1\n " + command, "huawei")
                self.assertEqual(cfg.unsupported_count, 0)
                self.assertTrue(cfg.nat[0].complete)
                self.assertEqual(cfg.nat[0].inside, inside)
                self.assertEqual(cfg.nat[0].outside_port, port)

    def test_huawei_outbound_nat_tail_and_removal_are_checked(self):
        outbound = "nat outbound 3000 address-group 1"
        cfg = self.parse("interface GigabitEthernet0/0/1\n " + outbound, "huawei")
        self.assertEqual(cfg.unsupported_count, 0)
        self.assertTrue(cfg.nat[0].complete)
        cfg = self.parse("interface GigabitEthernet0/0/1\n " + outbound + " no-pat", "huawei")
        self.assert_incomplete(cfg, 3)
        self.assertFalse(cfg.nat[0].complete)
        cfg = self.parse("interface GigabitEthernet0/0/1\n " + outbound + "\n undo " + outbound + " UNKNOWN_TAIL", "huawei")
        self.assert_incomplete(cfg, 4)
        self.assertEqual(len(cfg.nat), 1)

    def test_h3c_nat_server_undo_selects_the_external_endpoint_without_inside(self):
        cfg = self.parse("interface GE1/0/1\n"
                         " nat server protocol tcp global 203.0.113.10 443 inside 10.0.0.50 443\n"
                         " undo nat server protocol tcp global 203.0.113.10 443", "h3c")
        self.assertEqual(cfg.unsupported_count, 0)
        self.assertEqual(cfg.nat, [])
        self.assertFalse(any(f["rule_id"].startswith("NAT-") for f in audit(cfg)["findings"]))

    def test_h3c_nat_server_undo_matches_owner_protocol_address_and_port(self):
        cfg = self.parse("interface GE1/0/1\n"
                         " nat server protocol tcp global 203.0.113.10 443 inside 10.0.0.50 443\n"
                         " nat server protocol udp global 203.0.113.10 443 inside 10.0.0.51 443\n"
                         " nat server protocol tcp global 203.0.113.10 444 inside 10.0.0.52 444\n"
                         " nat server protocol tcp global 203.0.113.100 443 inside 10.0.0.53 443\n"
                         "interface GE1/0/2\n"
                         " nat server protocol tcp global 203.0.113.10 443 inside 10.0.0.54 443\n"
                         "interface GE1/0/1\n"
                         " undo nat server protocol 6 global 203.0.113.10 443", "h3c")
        self.assertEqual(cfg.unsupported_count, 0)
        self.assertEqual({n.inside for n in cfg.nat},
                         {"10.0.0.51:443", "10.0.0.52:444", "10.0.0.53:443", "10.0.0.54:443"})

    def test_h3c_nat_server_undo_unknown_or_invalid_selector_is_atomic(self):
        base = "interface GE1/0/1\n nat server protocol tcp global 203.0.113.10 443 inside 10.0.0.50 443\n"
        for selector in ("203.0.113.10 443 UNKNOWN_TAIL", "203.0.113.10 443 vpn-instance BLUE",
                         "203.0.113.999 443", "203.0.113.10 65536",
                         "203.0.113.10 443 inside 10.0.0.50 443"):
            with self.subTest(selector=selector):
                cfg = self.parse(base + " undo nat server protocol tcp global " + selector, "h3c")
                self.assert_incomplete(cfg, 4)
                self.assertEqual(len(cfg.nat), 1)

    def test_huawei_nat_server_undo_still_requires_the_inside_endpoint(self):
        mapping = "nat server protocol tcp global 203.0.113.10 443 inside 10.0.0.50 443"
        base = "interface GE1/0/1\n " + mapping + "\n"
        cfg = self.parse(base + " undo nat server protocol tcp global 203.0.113.10 443", "huawei")
        self.assert_incomplete(cfg, 4)
        self.assertEqual(len(cfg.nat), 1)
        cfg = self.parse(base + " undo " + mapping, "huawei")
        self.assertEqual(cfg.unsupported_count, 0)
        self.assertEqual(cfg.nat, [])

    def test_h3c_outbound_undo_selects_owner_and_acl_without_the_pool(self):
        cfg = self.parse("interface GE1/0/1\n"
                         " nat outbound 2001 address-group 5\n"
                         " nat outbound 2002 address-group 6\n"
                         "interface GE1/0/2\n"
                         " nat outbound 2001 address-group 7\n"
                         "interface GE1/0/1\n undo nat outbound 2001", "h3c")
        self.assertEqual(cfg.unsupported_count, 0)
        self.assertEqual([(n.interface, n.acl, n.pool) for n in cfg.nat],
                         [("GE1/0/1", "2002", "6"), ("GE1/0/2", "2001", "7")])
        cfg = self.parse("interface GE1/0/1\n nat outbound 2001 address-group 5\n undo nat outbound 2001", "h3c")
        self.assertEqual(cfg.nat, [])
        self.assertFalse(any(f["rule_id"].startswith("NAT-") for f in audit(cfg)["findings"]))

    def test_h3c_outbound_undo_without_acl_selects_only_the_unfiltered_rule(self):
        cfg = self.parse("interface GE1/0/1\n"
                         " nat outbound address-group 5\n"
                         " nat outbound 2001 address-group 6\n"
                         "interface GE1/0/2\n nat outbound address-group 7\n"
                         "interface GE1/0/1\n undo nat outbound", "h3c")
        self.assertEqual(cfg.unsupported_count, 0)
        self.assertEqual([(n.interface, n.acl, n.pool) for n in cfg.nat],
                         [("GE1/0/1", "2001", "6"), ("GE1/0/2", None, "7")])

    def test_h3c_outbound_undo_extra_parameters_cannot_remove_a_rule(self):
        for selector in ("2001 UNKNOWN_TAIL", "2001 address-group 5", "2001 vpn-instance BLUE", "9999"):
            with self.subTest(selector=selector):
                cfg = self.parse("interface GE1/0/1\n nat outbound 2001 address-group 5\n"
                                 " undo nat outbound " + selector, "h3c")
                self.assert_incomplete(cfg, 4)
                self.assertEqual(len(cfg.nat), 1)

    def test_legacy_positional_model_construction_remains_supported(self):
        evidence = Evidence(1, "synthetic")
        route = Route("10.0.0.0/24", "192.0.2.1", None, "default", None, evidence)
        nat = NAT("static", None, None, None, None, "10.0.0.2", "192.0.2.2", None, evidence)
        self.assertTrue(route.complete)
        self.assertTrue(nat.complete)


if __name__ == "__main__":
    unittest.main()
