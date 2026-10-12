"""Independent fixture authoring record; no netaudit/parser/rules imports.

These manually specified vendor commands and IR values predate measurement.
Run explicitly to recreate the authored dataset. The acceptance runner never
invokes this file, updates expectations, or repairs checksums.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
INTERFACE_FIELDS = ("name", "shutdown", "description", "mode", "access_vlan", "native_vlan",
                    "allowed_vlan_ranges", "addresses", "vrf", "acl_bindings", "nat_role",
                    "stp_enabled", "stp_edge", "bpdu_guard", "bpdu_filter", "protected")
ACL_RULE_FIELDS = ("sequence", "action", "protocol", "source", "destination", "source_port", "destination_port", "complete")
ROUTE_FIELDS = ("destination", "next_hop", "interface", "vrf", "distance")
NAT_FIELDS = ("kind", "interface", "acl", "pool", "protocol", "inside", "outside", "outside_port", "complete")
MANAGEMENT_FIELDS = ("name", "transport", "authentication", "idle_seconds", "acl_bindings")
STP_FIELDS = ("enabled", "mode", "edge_default", "bpdu_guard_default", "bpdu_filter_default", "vlan_enabled")
SUPPORTED_PATHS = (["hostname"] + ["interfaces.*." + f for f in INTERFACE_FIELDS] +
                   ["vlans.*.name"] + ["routes[]." + f for f in ROUTE_FIELDS] +
                   ["acls.*." + f for f in ("name", "kind", "ordered")] +
                   ["acls.*.rules[]." + f for f in ACL_RULE_FIELDS] +
                   ["nat[]." + f for f in NAT_FIELDS] + ["nat_pools.*"] +
                   ["management_lines[]." + f for f in MANAGEMENT_FIELDS] +
                   ["stp." + f for f in STP_FIELDS])
UNKNOWN_IDS = ["PARSE-INCOMPLETE", "PARSE-NUMBER", "MGMT-VTY-UNKNOWN",
               "MGMT-VTY-SOURCE", "ACL-UNBOUND", "OSPF-AUTH-REVIEW"]


def interface(name, **values):
    result = {"name": name, "shutdown": None, "description": "", "mode": None,
              "access_vlan": None, "native_vlan": None, "allowed_vlan_ranges": None,
              "addresses": [], "vrf": "default", "acl_bindings": {}, "nat_role": None,
              "stp_enabled": None, "stp_edge": None, "bpdu_guard": None,
              "bpdu_filter": None, "protected": None}
    result.update(values)
    return result


def acl_rule(sequence=5, action="deny", protocol="ip", **values):
    result = {"sequence": sequence, "action": action, "protocol": protocol, "source": "any",
              "destination": "any", "source_port": None, "destination_port": None, "complete": True}
    result.update(values)
    return result


class Case:
    def __init__(self, number, vendor, scenario, positive, rule):
        self.vendor, self.number, self.scenario, self.positive = vendor, number, scenario, positive
        self.id = f"{vendor}-{number:02d}-{scenario}-{'risk' if positive else 'control'}"
        self.port = {"cisco": "GigabitEthernet0/1", "huawei": "GigabitEthernet0/0/1", "h3c": "GigabitEthernet1/0/1"}[vendor]
        self.peer = {"cisco": "GigabitEthernet0/2", "huawei": "GigabitEthernet0/0/2", "h3c": "GigabitEthernet1/0/2"}[vendor]
        self.ip = f"10.{number}.0.1"
        self.lines = [("hostname " if vendor == "cisco" else "sysname ") + self.id]
        self.gold = {"inventory": {"hostname": self.id, "interfaces": {}, "vlans": {}, "routes": [],
                                   "acls": {}, "nat": [], "nat_pools": {}, "management_lines": [],
                                   "stp": {"enabled": None, "mode": None, "edge_default": None,
                                           "bpdu_guard_default": None, "bpdu_filter_default": None, "vlan_enabled": {}}},
                     "risk_findings": [], "unknown_findings": [], "unknown_commands": [],
                     "must_not_report": [] if positive else [rule],
                     "annotation": "手工根据显式命令、匹配顺序和对象作用域标注；不代表实设备运行状态。"}
        self.block("interface " + self.port, ["description Campus-uplink", "no shutdown" if vendor == "cisco" else "undo shutdown"] +
                   (["no switchport"] if vendor == "cisco" else []) + [f"ip address {self.ip} 255.255.255.0"])
        self.inv["interfaces"][self.port] = interface(self.port, shutdown=False, description="Campus-uplink",
                                                      mode="routed" if vendor == "cisco" else None,
                                                      addresses=[self.ip + "/24"])

    @property
    def inv(self):
        return self.gold["inventory"]

    def add(self, text):
        self.lines.append(text)
        return len(self.lines)

    def block(self, header, commands):
        line = self.add(header)
        for command in commands:
            self.add(" " + command)
        self.add("!" if self.vendor == "cisco" else "#")
        return line

    def risk(self, rule, objects):
        self.gold["risk_findings"].append({"rule_id": rule, "affected_objects": objects})

    def line_risk(self, rule, line):
        self.risk(rule, [f"配置行 {line}"])

    def unknown(self, rule, objects=None, command=None):
        item = {"rule_id": rule, "affected_objects": objects or []}
        if item not in self.gold["unknown_findings"]:
            self.gold["unknown_findings"].append(item)
        if command:
            self.gold["unknown_commands"].append(command)

    def vlans(self):
        if self.vendor == "cisco":
            for vid, name in ((10, "Students"), (20, "Staff")):
                self.block(f"vlan {vid}", ["name " + name])
                self.inv["vlans"][str(vid)] = {"name": name}
        else:
            self.add("vlan batch 10 20" if self.vendor == "huawei" else "vlan 10 20")
            self.add("#")
            self.inv["vlans"] = {"10": {"name": ""}, "20": {"name": ""}}

    def filtered_acl(self, name="2001"):
        self.block("acl number " + name, ["rule 5 permit source 10.0.0.0 0.255.255.255"])
        self.inv["acls"][name] = {"name": name, "kind": "standard", "ordered": True,
                                   "rules": [acl_rule(action="permit", source="10.0.0.0/8")]}


def author_case(case, scenario, rule):
    c, p, v = case, case.positive, case.vendor
    if scenario == "http":
        line = c.add("ip http server" if p else "no ip http server")
        if p: c.line_risk(rule, line)
    elif scenario == "ssh-retries":
        line = c.add("ip ssh authentication-retries " + ("8" if p else "3"))
        if p: c.line_risk(rule, line)
    elif scenario in ("vty-telnet", "vty-noauth", "vty-timeout"):
        transport = ["telnet", "ssh"] if p and scenario == "vty-telnet" else ["ssh"]
        auth = "no login" if p and scenario == "vty-noauth" else "login local"
        timeout = 0 if p and scenario == "vty-timeout" else 600
        c.block("line vty 0 4", ["transport input " + " ".join(transport), auth, "exec-timeout " + str(timeout // 60) + " 0"])
        c.inv["management_lines"] = [{"name": "line vty 0 4", "transport": transport, "authentication": auth,
                                      "idle_seconds": timeout, "acl_bindings": {}}]
        if p: c.risk(rule, ["line vty 0 4"])
        c.unknown("MGMT-VTY-SOURCE", ["line vty 0 4"])
    elif scenario == "credential":
        c.add("username trainee " + ("password 7 SYNTHETIC" if p else "secret 9 SYNTHETIC_HASH"))
        if p: c.risk(rule, ["账号 trainee"])
        if not p:
            c.block("interface " + c.peer, ["ip address dhcp"])
            c.inv["interfaces"][c.peer] = interface(c.peer)
            c.unknown("PARSE-INCOMPLETE", command="ip address dhcp")
    elif scenario == "snmp":
        line = c.add("snmp-server community SYNTHETIC RO" if p else "no snmp-server community SYNTHETIC")
        if p: c.line_risk(rule, line)
    elif scenario == "ssh-version":
        line = c.add("ip ssh version " + ("1" if p else "2"))
        if p: c.line_risk(rule, line)
    elif scenario == "acl-shadow":
        commands = (["10 deny tcp any any eq 23", "20 permit tcp any any eq 23"] if p else
                    ["10 permit tcp any any established", "20 deny tcp any any eq 23"])
        c.block("ip access-list extended CAMPUS", commands)
        c.block("interface " + c.port, ["ip access-group CAMPUS in"])
        c.inv["interfaces"][c.port]["acl_bindings"] = {"in": "CAMPUS"}
        c.inv["acls"]["CAMPUS"] = {"name": "CAMPUS", "kind": "extended", "ordered": True,
                                     "rules": [acl_rule(10, "deny" if p else "permit", "tcp", destination_port="eq 23" if p else None, complete=p),
                                               acl_rule(20, "permit" if p else "deny", "tcp", destination_port="eq 23")]}
        if p: c.risk(rule, ["ACL CAMPUS"])
        else: c.unknown("PARSE-INCOMPLETE", command="10 permit tcp any any established")
    elif scenario == "telnet-server":
        line = c.add("telnet server enable" if p else "undo telnet server enable")
        if p: c.line_risk(rule, line)
    elif scenario == "acl-undefined":
        if not p:
            c.block("acl number 3000", ["rule 5 deny ip"])
            c.inv["acls"]["3000"] = {"name": "3000", "kind": "extended", "ordered": True, "rules": [acl_rule()]}
        c.block("interface " + c.port, ["traffic-filter inbound acl 3000"])
        c.inv["interfaces"][c.port]["acl_bindings"] = {"inbound": "3000"}
        if p: c.risk(rule, [c.port])
    elif scenario == "vty-acl-undefined":
        if not p: c.filtered_acl("2001")
        c.block("user-interface vty 0 4", ["protocol inbound ssh", "authentication-mode aaa", "idle-timeout 10 0", "acl 2001 inbound"])
        c.inv["management_lines"] = [{"name": "user-interface vty 0 4", "transport": ["ssh"], "authentication": "authentication-mode aaa",
                                      "idle_seconds": 600, "acl_bindings": {"inbound": "2001"}}]
        if p: c.risk(rule, ["user-interface vty 0 4"])
    elif scenario == "vlan-undefined":
        if not p:
            c.block("vlan 30", ["description Students"])
            c.inv["vlans"]["30"] = {"name": "Students"}
        c.block("interface " + c.peer, ["port link-type access", "port default vlan 30", "description Student-desktop", "undo shutdown"])
        c.inv["interfaces"][c.peer] = interface(c.peer, mode="access", access_vlan=30, description="Student-desktop", shutdown=False)
        if p: c.risk(rule, [c.peer])
    elif scenario in ("native-vlan", "pvid-list", "trunk-all", "edge-trunk"):
        c.vlans()
        native = (1 if p else 10) if scenario == "native-vlan" else ((20 if p else 10) if scenario == "pvid-list" else 10)
        allow = "10" if scenario == "pvid-list" else ("all" if p and scenario == "trunk-all" else "10 20")
        command = "port trunk allow-pass vlan " if v == "huawei" else "port trunk permit vlan "
        commands = ["port link-type trunk", "port trunk pvid vlan " + str(native), command + allow]
        if scenario == "edge-trunk": commands.append("stp edged-port " + ("enable" if p else "disable"))
        c.block("interface " + c.peer, commands)
        ranges = [[1, 4094]] if allow == "all" else ([[1, 1], [10, 10]] if allow == "10" else [[1, 1], [10, 10], [20, 20]])
        c.inv["interfaces"][c.peer] = interface(c.peer, mode="trunk", native_vlan=native, allowed_vlan_ranges=ranges,
                                                stp_edge=p if scenario == "edge-trunk" else None)
        if p: c.risk(rule, [c.peer])
    elif scenario == "duplicate-ip":
        commands = [f"ip address {c.ip} 255.255.255.0"]
        if not p: commands.insert(0, "ip binding vpn-instance BLUE")
        c.block("interface " + c.peer, commands)
        c.inv["interfaces"][c.peer] = interface(c.peer, addresses=[c.ip + "/24"], vrf="default" if p else "BLUE")
        if p: c.risk(rule, [c.port, c.peer])
    elif scenario == "self-nexthop":
        hop = c.ip if p else f"10.{c.number}.0.254"
        line = c.add("ip route-static 0.0.0.0 0.0.0.0 " + hop + " preference 70")
        c.inv["routes"] = [{"destination": "0.0.0.0/0", "next_hop": hop, "interface": None, "vrf": "default", "distance": 70}]
        if p: c.line_risk(rule, line)
    elif scenario in ("nat-acl", "nat-pool"):
        if scenario == "nat-pool" or not p: c.filtered_acl()
        if scenario == "nat-pool" and not p:
            c.add("nat address-group 5 198.51.100.10 198.51.100.11")
            c.inv["nat_pools"] = {"5": {}}
        c.block("interface " + c.port, ["nat outbound 2001" + (" address-group 5" if scenario == "nat-pool" else "")])
        c.inv["nat"] = [{"kind": "outbound", "interface": c.port, "acl": "2001", "pool": "5" if scenario == "nat-pool" else None,
                          "protocol": None, "inside": None, "outside": None, "outside_port": None, "complete": True}]
        if p: c.risk(rule, [c.port])
    elif scenario == "nat-inbound":
        command = f"nat server protocol tcp global 203.0.113.10 443 inside 10.{c.number}.0.50 443"
        # Official H3C ordinary-server deletion selects the external endpoint;
        # Huawei interface NAT-server deletion retains the inside endpoint.
        undo = "undo nat server protocol tcp global 203.0.113.10 443" if v == "h3c" else "undo " + command
        c.block("interface " + c.port, [command] + ([] if p else [undo]))
        if not p and v == "h3c":
            c.gold["annotation"] = "根据H3C官方普通内部服务器语法，undo仅按协议/外侧地址/端口删除对应映射；最终nat为空。修正此前把正向inside参数机械复制到undo的无效测试输入，预期语义不变，不按当前解析输出改写。"
            c.gold["sources"] = ["https://www.h3c.com/en/d_202511/2698500_294551_0.htm",
                                   "https://www.h3c.com/en/d_202402/2050558_294551_0.htm"]
        if p:
            c.inv["nat"] = [{"kind": "server", "interface": c.port, "acl": None, "pool": None, "protocol": "tcp",
                              "inside": f"10.{c.number}.0.50:443", "outside": "203.0.113.10", "outside_port": "443", "complete": True}]
            c.risk(rule, [c.port])
    elif scenario == "stp-disabled":
        line = c.add("stp disable" if p else "stp enable")
        c.inv["stp"]["enabled"] = not p
        if p: c.line_risk(rule, line)
    elif scenario == "bpdu-filter":
        c.vlans()
        c.block("interface " + c.peer, ["port link-type access", "port access vlan 10", "stp bpdu-filter " + ("enable" if p else "disable")])
        c.inv["interfaces"][c.peer] = interface(c.peer, mode="access", access_vlan=10, bpdu_filter=p)
        if p: c.risk(rule, [c.peer])
    elif scenario == "ospf-broad":
        c.add("ospf 1 router-id 1.1.1.1")
        c.add(" silent-interface all")
        c.add(" area 0")
        line = c.add("  network " + ("10.0.0.0 0.255.255.255" if p else f"10.{c.number}.0.0 0.0.0.255"))
        c.add("#")
        if p: c.line_risk(rule, line)
        else:
            c.add("ip route-static 192.0.2.0 255.255.255.0 10.16.0.254 description Lab-route")
            c.inv["routes"] = [{"destination": "192.0.2.0/24", "next_hop": "10.16.0.254", "interface": None, "vrf": "default", "distance": None}]
    else:
        raise ValueError(scenario)


SCENARIOS = {
    "cisco": [("http", "MGMT-HTTP"), ("ssh-retries", "MGMT-SSH-RETRIES"), ("vty-telnet", "MGMT-VTY-TELNET"),
              ("vty-noauth", "MGMT-VTY-NOAUTH"), ("vty-timeout", "MGMT-VTY-TIMEOUT"), ("credential", "MGMT-CREDENTIAL"),
              ("snmp", "MGMT-SNMP-COMMUNITY"), ("ssh-version", "MGMT-SSHV1"), ("acl-shadow", "ACL-SHADOW")],
    "huawei": [("telnet-server", "MGMT-TELNET-SERVER"), ("acl-undefined", "ACL-UNDEFINED"), ("vty-acl-undefined", "ACL-VTY-UNDEFINED"),
               ("vlan-undefined", "VLAN-UNDEFINED"), ("native-vlan", "VLAN-NATIVE-1"), ("pvid-list", "VLAN-PVID-NOT-ALLOWED"),
               ("duplicate-ip", "IF-DUPLICATE-IP"), ("self-nexthop", "ROUTE-SELF-NEXTHOP")],
    "h3c": [("trunk-all", "VLAN-TRUNK-ALL"), ("nat-acl", "NAT-ACL-UNDEFINED"), ("nat-pool", "NAT-POOL-UNDEFINED"),
            ("nat-inbound", "NAT-INBOUND-MAPPING"), ("stp-disabled", "STP-DISABLED"), ("edge-trunk", "STP-EDGE-TRUNK"),
            ("bpdu-filter", "STP-BPDU-FILTER"), ("ospf-broad", "OSPF-BROAD-NETWORK")],
}


def main():
    manifest = {"dataset_id": "campus-synthetic-gold-v1.1", "schema_version": "1.0",
                "scope": "50份按厂商真实CLI语法人工合成的校园网络配置片段；未采集、未连接或验证实设备。仅衡量冻结支持字段与列出的规则，不能外推为所有平台、版本或生产网络的普适性能。",
                "gold_provenance": "author_fixtures.py逐场景人工指定配置和语义值；不导入、调用或复制当前parser/rules输出。expected JSON在首次测量前写入并由SHA256冻结。",
                "frozen_supported_paths": SUPPORTED_PATHS, "unknown_rule_ids": UNKNOWN_IDS,
                "change_history": [{"version": "1.1", "date": "2026-10-12", "case": "h3c-08-nat-inbound-control",
                                    "reason": "官方语法复核发现普通H3C undo nat server不得机械复制inside参数；修正合法输入，保留独立nat=[]预期及不应报NAT-INBOUND-MAPPING断言。",
                                    "old_config_sha256": "712cdc53ff02bf7e4748918fdd25a4015f1e9f60683536690206f403eba27e3b",
                                    "old_expected_sha256": "3b31a898aafb5ba1068832eaff19904a6603b7843f052061c304e3936ead61b9",
                                    "source": "https://www.h3c.com/en/d_202511/2698500_294551_0.htm"}],
                "cases": []}
    for vendor, scenarios in SCENARIOS.items():
        for index, (scenario, rule) in enumerate(scenarios):
            for positive in (True, False):
                case = Case(index * 2 + (1 if positive else 2), vendor, scenario, positive, rule)
                author_case(case, scenario, rule)
                config_name, expected_name = f"configs/{case.id}.cfg", f"expected/{case.id}.json"
                for name, contents in ((config_name, "\n".join(case.lines) + "\n"),
                                       (expected_name, json.dumps(case.gold, ensure_ascii=False, indent=2) + "\n")):
                    path = HERE / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(contents, encoding="utf-8")
                manifest["cases"].append({"id": case.id, "vendor": vendor, "scenario": scenario,
                                           "polarity": "risk" if positive else "control", "focus_rule": rule,
                                           "config": config_name, "expected": expected_name,
                                           "sha256": {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                                                      for name in (config_name, expected_name)}})
    (HERE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Authored 50 independent fixtures: Cisco18 Huawei16 H3C16; no parser or auditor called.")


if __name__ == "__main__":
    main()
