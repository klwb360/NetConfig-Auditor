import json
from pathlib import Path
import unittest

from netaudit import audit, parse_config
from netaudit.parser import MAX_BYTES, vlan_ids


class ParsingTests(unittest.TestCase):
    def test_vendor_examples(self):
        for vendor in ("cisco", "huawei", "h3c"):
            with self.subTest(vendor=vendor):
                c = parse_config((Path(__file__).parents[1] / "examples" / (vendor + ".cfg")).read_text())
                self.assertEqual(c.vendor, vendor)
                self.assertEqual(len(c.interfaces), 3)
                self.assertEqual(len(c.acls), 2)
                self.assertEqual(len(c.routes), 1)
                self.assertEqual(len(c.nat), 2)
                self.assertEqual(c.routes[0].destination, "0.0.0.0/0")
                self.assertTrue(any(f["rule_id"] == "MGMT-HTTP" for f in audit(c)["findings"]))

    def test_uncertain_vendor_requires_override(self):
        with self.assertRaisesRegex(ValueError, "无法可靠识别"):
            parse_config("sysname X\ninterface GigabitEthernet0/1\n")
        self.assertEqual(parse_config("sysname X", "huawei").vendor, "huawei")

    def test_mixed_vendor_rejected(self):
        with self.assertRaises(ValueError):
            parse_config("hostname X\nport trunk permit vlan all")

    def test_vlan_ranges(self):
        self.assertEqual(vlan_ids("10,20-22 30 to 31"), {10, 20, 21, 22, 30, 31})
        self.assertEqual(vlan_ids("none"), set())
        for value in ("0", "4095", "20-10", "all 10", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                vlan_ids(value)

    def test_cisco_vlan_add_remove_except(self):
        c = parse_config("hostname X\ninterface Gi0/1\n switchport trunk allowed vlan 10-12\n switchport trunk allowed vlan add 20\n switchport trunk allowed vlan remove 11\n", "cisco")
        self.assertEqual(c.interfaces["Gi0/1"].allowed_vlans, [10, 12, 20])
        c = parse_config("hostname X\ninterface Gi0/1\n switchport trunk allowed vlan except 1-4093", "cisco")
        self.assertEqual(c.interfaces["Gi0/1"].allowed_vlans, [4094])

    def test_huawei_vlan_accumulation_and_undo(self):
        c = parse_config("sysname X\ninterface GE0/1\n port trunk allow-pass vlan 10\n port trunk allow-pass vlan 20 to 22\n undo port trunk allow-pass vlan 1 21", "huawei")
        self.assertEqual(c.interfaces["GE0/1"].allowed_vlans, [10, 20, 22])

    def test_vlan_wire_format_uses_compact_ranges(self):
        c = parse_config("hostname X\ninterface Gi0/1\n switchport trunk allowed vlan all", "cisco")
        wire = c.to_dict()["interfaces"]["Gi0/1"]
        self.assertEqual(wire["allowed_vlan_ranges"], [[1, 4094]])
        self.assertNotIn("allowed_vlans", wire)

    def test_h3c_line_vty_not_misdetected_as_cisco(self):
        c = parse_config("sysname X\nversion 7.1.070\ninterface Vlan-interface10\n ip address 10.0.0.1 24\n#\nline vty 0 4\n protocol inbound ssh")
        self.assertEqual(c.vendor, "h3c")

    def test_interface_last_shutdown_wins(self):
        c = parse_config("hostname X\ninterface Gi0/1\n shutdown\n no shutdown", "cisco")
        self.assertFalse(c.interfaces["Gi0/1"].shutdown)

    def test_vty_acl_not_misparsed_as_acl_header(self):
        c = parse_config("sysname X\nuser-interface vty 0 4\n acl 2000 inbound\n protocol inbound ssh\n#\nacl number 2000\n rule 5 permit source 10.0.0.0 0.0.0.255", "huawei")
        self.assertEqual(c.management_lines[0].acl_bindings, {"inbound": "2000"})
        self.assertEqual(c.acls["2000"].kind, "standard")
        self.assertEqual(c.acls["2000"].rules[0].source, "10.0.0.0/24")

    def test_ipv4_addresses_and_secondary(self):
        c = parse_config("hostname X\ninterface Gi0/1\n ip address 10.0.0.1 255.255.255.0\n ip address 10.0.1.1 255.255.255.0 secondary\n ip address 10.0.2.1 255.255.255.0", "cisco")
        self.assertEqual(c.interfaces["Gi0/1"].addresses, ["10.0.2.1/24", "10.0.1.1/24"])

    def test_address_undo(self):
        c = parse_config("hostname X\ninterface Gi0/1\n ip address 10.0.0.1 255.255.255.0\n no ip address", "cisco")
        self.assertEqual(c.interfaces["Gi0/1"].addresses, [])

    def test_acl_network_ports_and_provenance(self):
        c = parse_config("hostname X\nip access-list extended A\n 20 permit tcp 10.0.0.0 0.0.0.255 eq 1024 host 192.0.2.2 range 443 444 log\n 10 deny ip any any", "cisco")
        r = c.acls["A"].rules[1]
        self.assertEqual(r.sequence, 20)
        self.assertEqual(r.source, "10.0.0.0/24")
        self.assertEqual(r.destination, "192.0.2.2/32")
        self.assertEqual(r.source_port, "eq 1024")
        self.assertEqual(r.destination_port, "range 443 444")
        self.assertEqual(r.evidence.line, 3)
        self.assertTrue(r.complete)

    def test_non_contiguous_wildcard_not_fabricated_as_cidr(self):
        c = parse_config("hostname X\naccess-list 10 permit 10.0.0.0 0.255.0.255", "cisco")
        self.assertIn("wildcard", c.acls["10"].rules[0].source)

    def test_huawei_acl_conditions(self):
        c = parse_config("sysname X\nacl number 3000\n rule 5 permit tcp source 10.0.0.0 0.0.0.255 destination 192.0.2.0 0.0.0.255 destination-port eq 443", "huawei")
        r = c.acls["3000"].rules[0]
        self.assertTrue(r.complete)
        self.assertEqual(r.destination, "192.0.2.0/24")
        self.assertEqual(r.destination_port, "eq 443")

    def test_unknown_acl_modifier_not_guessed(self):
        c = parse_config("hostname X\nip access-list extended A\n permit tcp any any established", "cisco")
        self.assertFalse(c.acls["A"].rules[0].complete)
        self.assertTrue(c.warnings)

    def test_acl_undo(self):
        c = parse_config("sysname X\nacl number 3000\n rule 5 permit ip\n undo rule 5", "h3c")
        self.assertEqual(c.acls["3000"].rules, [])

    def test_static_routes_vrf_null0_and_distance(self):
        c = parse_config("hostname X\nip route vrf BLUE 10.0.0.0 255.255.255.0 192.0.2.1 200\nip route 10.1.0.0 255.255.0.0 Null0", "cisco")
        self.assertEqual(c.routes[0].vrf, "BLUE")
        self.assertEqual(c.routes[0].distance, 200)
        self.assertEqual(c.routes[1].interface, "Null0")
        self.assertIsNone(c.routes[1].next_hop)

    def test_h3c_vpn_route(self):
        c = parse_config("sysname X\nip route-static vpn-instance BLUE 10.0.0.0 24 192.0.2.1 preference 100", "h3c")
        self.assertEqual(c.routes[0].destination, "10.0.0.0/24")
        self.assertEqual(c.routes[0].distance, 100)

    def test_cisco_nat_ports_and_pool(self):
        c = parse_config("hostname X\nip nat pool P 192.0.2.2 192.0.2.4 netmask 255.255.255.0\nip nat inside source list 10 pool P overload\nip nat inside source static tcp 10.0.0.2 22 192.0.2.2 2222", "cisco")
        self.assertIn("P", c.nat_pools)
        self.assertEqual(c.nat[0].acl, "10")
        self.assertEqual(c.nat[0].pool, "P")
        self.assertEqual(c.nat[1].inside, "10.0.0.2:22")
        self.assertEqual(c.nat[1].outside_port, "2222")

    def test_nat_undo_and_role(self):
        c = parse_config("hostname X\ninterface Gi0/1\n ip nat inside\n no ip nat inside\n!\nip nat inside source static 10.0.0.2 192.0.2.2\nno ip nat inside source static 10.0.0.2 192.0.2.2", "cisco")
        self.assertIsNone(c.interfaces["Gi0/1"].nat_role)
        self.assertEqual(c.nat, [])

    def test_malformed_line_reported_without_exception(self):
        c = parse_config("hostname X\ninterface Gi0/1\n ip address not-ip not-mask\n!\nip route 0.0.0.0", "cisco")
        self.assertEqual(len(c.warnings), 2)
        self.assertEqual(c.interfaces["Gi0/1"].addresses, [])

    def test_banner_not_executed_as_config(self):
        c = parse_config("hostname X\nbanner motd ^C\nip http server\nusername bad password dangerous\n^C\nno ip http server", "cisco")
        self.assertFalse(any(f["rule_id"] == "MGMT-CREDENTIAL" for f in audit(c)["findings"]))
        self.assertNotIn("dangerous", json.dumps(c.to_dict()))

    def test_interface_range_is_explicitly_unsupported(self):
        c = parse_config("hostname X\ninterface range Gi0/1 - 2\n shutdown", "cisco")
        self.assertFalse(c.interfaces)
        self.assertGreater(c.unsupported_count, 0)

    def test_limits_and_controls(self):
        for text in ("", "x" * (MAX_BYTES + 1), "hostname X\x00", "\n" * 30001):
            with self.subTest(length=len(text)), self.assertRaises(ValueError):
                parse_config(text, "cisco")

    def test_acl_resource_ceiling(self):
        text = "hostname X\nip access-list extended A\n" + "\n".join(f" {i} permit ip any any" for i in range(257))
        with self.assertRaisesRegex(ValueError, "ACL 规则超过限制"):
            parse_config(text, "cisco")

    def test_warnings_bounded(self):
        c = parse_config("hostname X\n" + "unsupported command\n" * 400, "cisco")
        self.assertEqual(c.unsupported_count, 400)
        self.assertEqual(len(c.warnings), 200)


if __name__ == "__main__":
    unittest.main()
