import json
import unittest
from unittest.mock import patch

from netaudit.parser import IOS_VENDORS, parse_config
from netaudit.simulation_goals import MAX_GOAL_CHARS, plan_goal
from netaudit.simulator import simulate_configuration


VENDORS = ("cisco", "huawei", "h3c", "ruijie")
PORT = "GigabitEthernet0/1"


def backup(vendor, *, interface_lines=" description lab", with_vty=True):
    headers = {"cisco": "hostname PRIVATE-DEVICE", "huawei": "!Software Version TEST\nsysname PRIVATE-DEVICE",
               "h3c": "# H3C Comware\nsysname PRIVATE-DEVICE", "ruijie": "version TEST_RGOS 11.4\nhostname PRIVATE-DEVICE"}
    ios = vendor in IOS_VENDORS
    sep = "!" if ios else "#"
    vty = ("line vty 0 4\n transport input telnet ssh\n login local" if ios else
           "user-interface vty 0 4\n protocol inbound telnet ssh\n authentication-mode " + ("aaa" if vendor == "huawei" else "scheme"))
    return (headers[vendor] + "\n" + ("username admin secret PRIVATE-CREDENTIAL" if ios else "local-user admin password irreversible-cipher PRIVATE-CREDENTIAL")
            + f"\n{sep}\nvlan 10\n{sep}\ninterface {PORT}\n{interface_lines}\n{sep}\n"
            + (vty + f"\n{sep}\n" if with_vty else ""))


class SimulationGoalTests(unittest.TestCase):
    def replay(self, config, vendor, goal, context=None):
        before = config
        value = plan_goal(config, vendor, goal, context)
        self.assertEqual(value["status"], "ready", value)
        self.assertTrue(value["commands"])
        self.assertEqual(value["questions"], [])
        self.assertEqual(value["commands"], "\n".join(row["command"] for row in value["steps"]))
        self.assertTrue(all(row["reason"] for row in value["steps"]))
        self.assertNotIn("config", value)
        self.assertNotIn("inventory", value)
        serialized = json.dumps(value, ensure_ascii=False)
        self.assertNotIn("PRIVATE-CREDENTIAL", serialized)
        self.assertNotIn("PRIVATE-DEVICE", serialized)
        result = simulate_configuration(config, vendor, value["commands"], context)
        self.assertFalse(result["summary"]["rolled_back"], result["results"])
        self.assertEqual(result["summary"], {key: value["validation"][key] for key in result["summary"]})
        self.assertEqual(result["context"], {"mode": "exec", "target": ""})
        self.assertEqual(before, config)
        return value, result, parse_config(result["config"], vendor)

    def test_create_vlan_and_detect_four_vendors(self):
        for vendor in VENDORS:
            with self.subTest(vendor=vendor):
                value, result, cfg = self.replay(backup(vendor), "auto", "请创建 VLAN 20。")
                self.assertEqual(result["vendor"], vendor)
                self.assertIn(20, cfg.vlans)
                self.assertIn("尚未应用", value["summary"])

    def test_same_action_vlan_list_and_range(self):
        for vendor in VENDORS:
            with self.subTest(vendor=vendor):
                _, _, cfg = self.replay(backup(vendor), vendor, "创建 VLAN 20、22至24和26")
                self.assertTrue({20, 22, 23, 24, 26} <= set(cfg.vlans))

    def test_access_creates_missing_vlan_before_interface_reference(self):
        for vendor in VENDORS:
            with self.subTest(vendor=vendor):
                value, _, cfg = self.replay(backup(vendor), vendor, f"把接口 {PORT} 加入 VLAN 20")
                self.assertLess(value["commands"].index("vlan 20"), value["commands"].index("interface " + PORT))
                self.assertEqual(cfg.interfaces[PORT].access_vlan, 20)
                self.assertEqual(cfg.interfaces[PORT].mode, "access")
                self.assertTrue(any("先创建" in row["reason"] for row in value["steps"]))

    def test_access_does_not_duplicate_existing_vlan_creation(self):
        value, _, cfg = self.replay(backup("cisco"), "cisco", f"把接口 {PORT} 加入 VLAN 10")
        self.assertNotIn("\nvlan 10\n", value["commands"])
        self.assertEqual(cfg.interfaces[PORT].access_vlan, 10)

    def test_case_only_interface_resolution_never_expands_abbreviations(self):
        value, _, _ = self.replay(backup("cisco"), "cisco", f"开启接口 {PORT.lower()}")
        self.assertIn("interface " + PORT, value["commands"])
        for name in ("Gi0/1", "GigabitEthernet9/99"):
            with self.subTest(name=name):
                value = plan_goal(backup("cisco"), "cisco", f"把接口 {name} 加入 VLAN 20")
                self.assertEqual(value["status"], "blocked")
                self.assertEqual(value["commands"], "")

    def test_full_view_script_works_from_existing_interface_vlan_and_vty(self):
        for vendor in VENDORS:
            config = backup(vendor)
            for context in ({"mode": "interface", "target": PORT}, {"mode": "vlan", "target": "10"},
                            {"mode": "vty", "target": "line vty 0 4" if vendor in IOS_VENDORS else "user-interface vty 0 4"}):
                with self.subTest(vendor=vendor, context=context):
                    value, _, _ = self.replay(config, vendor, "创建 VLAN 20", context)
                    self.assertEqual(value["commands"].splitlines()[0], "end" if vendor in IOS_VENDORS else "return")

    def test_delete_referenced_vlan_is_blocked_by_actual_engine(self):
        for vendor in VENDORS:
            lines = " switchport mode access\n switchport access vlan 10" if vendor in IOS_VENDORS else " port link-type access\n " + ("port default vlan 10" if vendor == "huawei" else "port access vlan 10")
            with self.subTest(vendor=vendor):
                value = plan_goal(backup(vendor, interface_lines=lines), vendor, "删除 VLAN 10")
                self.assertEqual(value["status"], "blocked")
                self.assertIn("仍被接口引用", value["summary"])
                self.assertTrue(value["validation"]["rolled_back"])
                self.assertEqual(value["commands"], "")
                self.assertEqual(value["steps"], [])

    def test_delete_unreferenced_vlan(self):
        for vendor in VENDORS:
            with self.subTest(vendor=vendor):
                _, _, cfg = self.replay(backup(vendor), vendor, "删除 VLAN 10")
                self.assertNotIn(10, cfg.vlans)

    def test_trunk_list_is_replaced_not_extended_for_four_vendors(self):
        for vendor in VENDORS:
            ios = vendor in IOS_VENDORS
            prefix = "switchport trunk allowed vlan " if ios else "port trunk allow-pass vlan " if vendor == "huawei" else "port trunk permit vlan "
            lines = (" switchport mode trunk" if ios else " port link-type trunk") + "\n " + prefix + "10"
            with self.subTest(vendor=vendor):
                value, _, cfg = self.replay(backup(vendor, interface_lines=lines), vendor, f"接口 {PORT} trunk 允许列表设为 VLAN 20,30")
                self.assertEqual(set(cfg.interfaces[PORT].allowed_vlans), {20, 30})
                self.assertIn("完整替换", value["summary"])

    def test_interface_description_and_power_state(self):
        for vendor in VENDORS:
            with self.subTest(vendor=vendor):
                _, result, cfg = self.replay(backup(vendor), vendor, f"接口 {PORT} 描述设为 办公室")
                self.assertEqual(cfg.interfaces[PORT].description, "办公室")
                _, result, cfg = self.replay(result["config"], vendor, f"关闭接口 {PORT}")
                self.assertTrue(cfg.interfaces[PORT].shutdown)
                _, _, cfg = self.replay(result["config"], vendor, f"启用端口 {PORT}")
                self.assertFalse(cfg.interfaces[PORT].shutdown)

    def test_description_does_not_swallow_an_extra_requested_operation(self):
        for suffix in ("办公室，关闭 HTTP", "办公室,启用 SSH2", "关闭接口", "办公室；创建 VLAN 20"):
            with self.subTest(suffix=suffix):
                value = plan_goal(backup("cisco"), "cisco", f"接口 {PORT} 描述设为 {suffix}")
                self.assertNotEqual(value["status"], "ready")
                self.assertEqual(value["commands"], "")
        _, _, cfg = self.replay(backup("cisco"), "cisco", f"接口 {PORT} 描述设为 “备用关闭接口”")
        self.assertEqual(cfg.interfaces[PORT].description, "备用关闭接口")

    def test_interface_ipv4_prefix_and_explicit_mask(self):
        for vendor in VENDORS:
            for address in ("192.0.2.1/24", "192.0.2.1 掩码 255.255.255.0"):
                with self.subTest(vendor=vendor, address=address):
                    _, _, cfg = self.replay(backup(vendor), vendor, f"接口 {PORT} IP地址设为 {address}")
                    self.assertIn("192.0.2.1/24", cfg.interfaces[PORT].addresses)

    def test_ipv4_does_not_guess_l2_to_l3_conversion_or_bad_host_address(self):
        for lines, address in ((" switchport mode access", "192.0.2.1/24"), (" description lab", "192.0.2.0/24"),
                               (" description lab", "127.0.0.1/32")):
            with self.subTest(lines=lines, address=address):
                value = plan_goal(backup("cisco", interface_lines=lines), "cisco", f"接口 {PORT} IP地址设为 {address}")
                self.assertEqual(value["status"], "blocked")
                self.assertEqual(value["commands"], "")
                self.assertTrue(value["validation"]["rolled_back"])

    def test_access_is_blocked_on_existing_l3_interface(self):
        value = plan_goal(backup("cisco", interface_lines=" ip address 192.0.2.1 255.255.255.0"), "cisco", f"把接口 {PORT} 加入 VLAN 20")
        self.assertEqual(value["status"], "blocked")
        self.assertTrue(value["validation"]["rolled_back"])
        self.assertEqual(value["commands"], "")

    def test_disable_http_uses_vendor_syntax_and_does_not_disable_https(self):
        expected = {"cisco": "no ip http server", "ruijie": "no ip http server", "huawei": "undo http server enable", "h3c": "undo ip http enable"}
        for vendor in VENDORS:
            with self.subTest(vendor=vendor):
                value, _, _ = self.replay(backup(vendor), vendor, "关闭 HTTP 服务")
                self.assertIn(expected[vendor], value["commands"])
                self.assertNotIn("secure", value["commands"])
                self.assertNotIn("https", value["commands"])

    def test_disable_telnet_preserves_known_ssh(self):
        for vendor in VENDORS:
            with self.subTest(vendor=vendor):
                value, _, cfg = self.replay(backup(vendor), vendor, "关闭 Telnet")
                if vendor in IOS_VENDORS:
                    self.assertEqual(cfg.management_lines[0].transport, ["ssh"])
                else:
                    self.assertIn("undo telnet server enable", value["commands"])

    def test_telnet_only_line_disables_access_without_enabling_ssh(self):
        for vendor in IOS_VENDORS:
            with self.subTest(vendor=vendor):
                config = backup(vendor).replace("transport input telnet ssh", "transport input telnet")
                value, _, cfg = self.replay(config, vendor, "禁用 Telnet 服务")
                self.assertEqual(cfg.management_lines[0].transport, ["none"])
                self.assertNotIn("transport input ssh", value["commands"])

    def test_missing_or_ambiguous_vty_does_not_guess_protocols(self):
        for config in (backup("cisco", with_vty=False), backup("cisco").replace("transport input telnet ssh", "transport input all"),
                       backup("cisco").replace(" transport input telnet ssh\n", "")):
            with self.subTest(config=config[-100:]):
                value = plan_goal(config, "cisco", "关闭 Telnet")
                self.assertEqual(value["status"], "needs-input")
                self.assertEqual(value["commands"], "")

    def test_ssh2_version_is_not_confused_with_enabling_a_service(self):
        for vendor in VENDORS:
            with self.subTest(vendor=vendor):
                value = plan_goal(backup(vendor), vendor, "启用 SSH2")
                if vendor in IOS_VENDORS:
                    self.assertEqual(value["status"], "ready")
                    self.assertIn("ip ssh version 2", value["commands"])
                    self.assertIn("仍取决于", value["summary"])
                    self.assertNotIn("transport input", value["commands"])
                else:
                    self.assertEqual(value["status"], "unsupported")
                    self.assertEqual(value["commands"], "")
                    value, _, _ = self.replay(backup(vendor), vendor, "开启 SSH 服务")
                    self.assertIn("不保证", value["summary"])

    def test_add_remove_static_route_with_exact_destination_and_hop(self):
        for vendor in VENDORS:
            with self.subTest(vendor=vendor):
                _, result, cfg = self.replay(backup(vendor), vendor, "添加静态路由 192.0.2.0/24 下一跳 198.51.100.1")
                self.assertEqual((cfg.routes[0].destination, cfg.routes[0].next_hop), ("192.0.2.0/24", "198.51.100.1"))
                _, _, cfg = self.replay(result["config"], vendor, "删除静态路由 192.0.2.0 掩码 255.255.255.0 下一跳为 198.51.100.1")
                self.assertEqual(cfg.routes, [])

    def test_static_route_rejects_bad_network_and_multicast_next_hop(self):
        for goal in ("添加静态路由 192.0.2.1/24 下一跳 198.51.100.1", "添加静态路由 192.0.2.0/24 下一跳 224.0.0.1"):
            with self.subTest(goal=goal):
                value = plan_goal(backup("cisco"), "cisco", goal)
                self.assertNotEqual(value["status"], "ready")
                self.assertEqual(value["commands"], "")

    def test_missing_parameters_produce_questions_and_no_commands(self):
        for goal in ("", "创建 VLAN", "删除 VLAN", f"把接口 {PORT} 加入 VLAN", "把接口加入 VLAN 20", "添加静态路由",
                     f"接口 {PORT} IP地址设为 192.0.2.1", f"接口 {PORT} trunk 允许列表设为"):
            with self.subTest(goal=goal):
                value = plan_goal(backup("cisco"), "cisco", goal)
                self.assertEqual(value["status"], "needs-input")
                self.assertTrue(value["questions"])
                self.assertEqual(value["commands"], "")
                self.assertEqual(value["steps"], [])

    def test_negation_conditions_multigoals_and_partial_matches_never_execute(self):
        for goal in ("不要创建 VLAN 20", "创建 VLAN 20 并关闭 HTTP", "创建 VLAN 20，但不要启用", "如果端口在线就创建 VLAN 20",
                     "创建 VLAN 20 并配置 OSPF", "创建 VLAN 20，关闭 HTTP", "创建 VLAN 20 后自动测试网络连通性", "创建 VLAN 20 吗", "仅在备用端口创建 VLAN 20",
                     f"关闭接口 {PORT} 然后启用接口 {PORT}", "请把上联口加入办公 VLAN"):
            with self.subTest(goal=goal):
                value = plan_goal(backup("cisco"), "cisco", goal)
                self.assertNotEqual(value["status"], "ready")
                self.assertEqual(value["commands"], "")

    def test_unsupported_runtime_or_protocol_goals_return_no_partial_draft(self):
        for goal in ("模拟 OSPF 邻居建立", "测试网络是否连通", "配置 BGP", "重启设备", "执行 ping 192.0.2.1"):
            with self.subTest(goal=goal):
                value = plan_goal(backup("cisco"), "cisco", goal)
                self.assertEqual(value["status"], "unsupported")
                self.assertEqual(value["commands"], "")

    def test_invalid_vlan_and_excessive_expansion_return_no_commands(self):
        for goal in ("创建 VLAN 0", "创建 VLAN 4095", "创建 VLAN 20-10", "创建 VLAN 1-4094"):
            with self.subTest(goal=goal):
                value = plan_goal(backup("cisco"), "cisco", goal)
                self.assertEqual(value["status"], "needs-input")
                self.assertEqual(value["commands"], "")

    def test_input_limits_plain_text_and_unicode_errors_are_generic(self):
        for goal in (None, 2, "x" * (MAX_GOAL_CHARS + 1), "创建 VLAN 20\n关闭 HTTP", "\x00PRIVATE-CREDENTIAL", "<script>PRIVATE-CREDENTIAL</script>", "\ud800PRIVATE-CREDENTIAL"):
            with self.subTest(goal_type=type(goal).__name__):
                with self.assertRaises(ValueError) as caught:
                    plan_goal(backup("cisco"), "cisco", goal)
                self.assertNotIn("PRIVATE-CREDENTIAL", str(caught.exception))

    def test_sensitive_goal_and_bad_config_do_not_echo_credentials(self):
        value = plan_goal(backup("cisco"), "cisco", "修改密码为 PRIVATE-CREDENTIAL")
        self.assertEqual(value["status"], "unsupported")
        self.assertNotIn("PRIVATE-CREDENTIAL", json.dumps(value))
        for config, vendor, context in (("PRIVATE-CREDENTIAL", "auto", None), (backup("cisco"), "unknown PRIVATE-CREDENTIAL", None),
                                        (backup("cisco"), "cisco", {"mode": "interface", "target": "PRIVATE-CREDENTIAL"})):
            with self.subTest(vendor=vendor):
                value = plan_goal(config, vendor, "创建 VLAN 20", context)
                self.assertEqual(value["status"], "blocked")
                self.assertNotIn("PRIVATE-CREDENTIAL", json.dumps(value))
                self.assertNotIn("PRIVATE-DEVICE", json.dumps(value))

    def test_unicode_line_separators_cannot_inject_commands_through_a_description(self):
        for separator in ("\u0085", "\u2028", "\u2029"):
            goal = f"接口 {PORT} 描述设为 office{separator}end{separator}configure terminal{separator}ip http server"
            with self.subTest(separator=repr(separator)):
                with self.assertRaises(ValueError):
                    plan_goal(backup("cisco"), "cisco", goal)

    def test_every_ready_draft_calls_real_simulator_and_returns_only_allowlisted_metadata(self):
        with patch("netaudit.simulation_goals.simulate_configuration", wraps=simulate_configuration) as simulate, \
                patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Unexpected network use")):
            value = plan_goal(backup("cisco"), "cisco", "创建 VLAN 20")
        self.assertEqual(value["status"], "ready")
        self.assertEqual(simulate.call_count, 2)
        self.assertEqual(simulate.call_args.args[2], value["commands"])
        self.assertNotIn("config", value["validation"])
        self.assertNotIn("diff", value["validation"])
        self.assertNotIn("inventory", value["validation"])
        for result in value["validation"]["results"]:
            self.assertEqual(set(result), {"status", "reason", "suggestion"})


if __name__ == "__main__":
    unittest.main()
