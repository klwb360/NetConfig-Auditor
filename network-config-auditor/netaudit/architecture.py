"""Conservative architecture checks on one device's offline configuration.

These checks establish configured intent, never live topology, convergence,
neighbor state, reachability, or the absence of controls on other devices.
"""
from __future__ import annotations

import ipaddress
import re

from .model import Config, Evidence, Finding


def _finding(rule_id, severity, category, title, problem, risk, recommendation,
             evidence, confidence="needs-review") -> Finding:
    return Finding(rule_id, severity, category, title, problem, risk,
                   recommendation, [e for e in evidence if e is not None], confidence)


def _ospf_interfaces(config, process, area):
    """Match configured interface selection, without asserting adjacency."""
    result = []
    for interface in config.interfaces.values():
        if interface.vrf != process["vrf"] or interface.shutdown is True:
            continue
        binding = interface.ospf_binding
        if binding is not None:
            selected = (binding["process_id"] == process["process_id"]
                        and binding["area"] == area)
        else:
            selected = False
            for network in process["networks"]:
                if network["area"] != area:
                    continue
                mask = (~int(ipaddress.IPv4Address(network["wildcard"]))) & 0xffffffff
                address = int(ipaddress.IPv4Address(network["address"]))
                if any((int(ipaddress.IPv4Interface(a).ip) & mask) == (address & mask)
                       for a in interface.addresses):
                    selected = True
                    break
        passive = process["passive_interfaces"].get(interface.name, process["passive_default"])
        if selected and passive is not True:
            result.append(interface)
    return result


def check_architecture(config: Config) -> list[Finding]:
    findings = []
    stp = config.stp
    if stp["enabled"] is False:
        findings.append(_finding(
            "STP-DISABLED", "high", "stp", "STP 显式关闭",
            "全局配置显式关闭生成树协议。",
            "存在冗余二层路径时，缺少生成树控制可能形成环路；配置文件不能证明实际有环路。",
            "核对二层拓扑、冗余设计和设备版本，在维护窗口验证后恢复适当的 STP 模式。",
            stp["evidence"], "confirmed-config"))
    disabled = [vid for vid, enabled in stp["vlan_enabled"].items() if enabled is False]
    if disabled:
        findings.append(_finding(
            "STP-DISABLED", "high", "stp", "STP 显式关闭",
            "下列 VLAN 的 STP 被显式关闭：" + ", ".join(map(str, sorted(disabled))),
            "存在冗余二层路径时，缺少生成树控制可能形成环路；配置文件不能证明实际有环路。",
            "核对二层拓扑、冗余设计和设备版本，在维护窗口验证后恢复适当的 STP 模式。",
            stp["evidence"], "confirmed-config"))
    if stp["bpdu_filter_default"] is True:
        findings.append(_finding(
            "STP-BPDU-FILTER-DEFAULT", "low", "stp", "配置默认 BPDU 过滤",
            "全局配置对边缘端口启用默认 BPDU 过滤。",
            "默认过滤和接口强制过滤的行为不同；误用在交换设备连接上可能影响环路防护。",
            "核对平台的默认过滤回退行为和端口用途，确认边缘识别与 BPDU 防护策略。",
            stp["evidence"]))
    for interface in config.interfaces.values():
        if interface.shutdown is True or interface.mode == "routed":
            continue
        if interface.stp_enabled is False:
            findings.append(_finding(
                "STP-DISABLED", "high", "stp", "STP 显式关闭",
                f"接口 {interface.name} 显式关闭 STP。",
                "存在冗余二层路径时，缺少生成树控制可能形成环路；配置文件不能证明实际有环路。",
                "核对二层拓扑、冗余设计和设备版本，在维护窗口验证后恢复适当的 STP 模式。",
                interface.stp_evidence, "confirmed-config"))
        # Cisco's portfast default applies to access ports, not every trunk.
        if interface.mode == "trunk" and interface.stp_edge is True:
            findings.append(_finding(
                "STP-EDGE-TRUNK", "medium", "stp", "Trunk 显式配置边缘/PortFast",
                f"接口 {interface.name} 同时配置 Trunk 和边缘/PortFast。",
                "若连接交换设备，快速转发可能扩大环路窗口；服务器或虚拟化 Trunk 也可能有合法需求。",
                "核对端口实际连接对象、冗余路径和 BPDU 防护；仅在确认的边缘链路使用此设置。",
                interface.stp_evidence + interface.evidence[:1]))
        if interface.bpdu_filter is True:
            findings.append(_finding(
                "STP-BPDU-FILTER", "high", "stp", "接口显式开启 BPDU 过滤",
                f"接口 {interface.name} 显式开启 BPDU 过滤。",
                "接口过滤可能隐藏对端生成树报文，削弱二层环路检测；实际影响取决于平台和连接对象。",
                "核对端口用途与平台过滤语义，确认业务后移除不必要的过滤并验证环路防护。",
                interface.stp_evidence))

    processes = [p for p in config.routing_processes if p["protocol"] == "ospf"]
    router_ids = {}
    for process in processes:
        identity = process["router_id"]
        if identity is not None:
            try:
                address = ipaddress.IPv4Address(identity)
                valid = not address.is_unspecified
            except ValueError:
                valid = False
            if not valid:
                findings.append(_finding(
                    "OSPF-ROUTER-ID", "high", "ospf", "OSPF Router ID 无效",
                    f"OSPF 进程 {process['process_id']} 的显式 Router ID 为 {identity}，不是有效的非零 IPv4 标识。",
                    "无效标识可能使配置被拒绝或导致协议无法按预期运行。",
                    "结合路由规划选择稳定、非零且在相应 OSPF 域内唯一的 Router ID，核对变更影响后修改。",
                    [process["router_id_evidence"]], "confirmed-config"))
            else:
                router_ids.setdefault((process["vrf"], str(address)), []).append(process)
        for network in process["networks"]:
            if network["prefix"] is not None and ipaddress.IPv4Network(network["prefix"]).prefixlen <= 8:
                findings.append(_finding(
                    "OSPF-BROAD-NETWORK", "medium", "ospf", "OSPF Network 选择范围过宽",
                    f"OSPF 进程 {process['process_id']}、区域 {network['area']} 的接口选择范围为 {network['prefix']}。",
                    "宽泛 Network 语句可能将非预期接口纳入协议；它选择接口，不等同于发布整个匹配地址段。",
                    "按实际三层链路缩小接口匹配范围或采用平台支持的接口绑定，并核对被动接口和认证。",
                    [network["evidence"]]))
        areas = set(process["areas"]) | {n["area"] for n in process["networks"]}
        areas.update(i.ospf_binding["area"] for i in config.interfaces.values()
                     if i.ospf_binding and i.ospf_binding["process_id"] == process["process_id"]
                     and i.vrf == process["vrf"])
        if not areas:
            areas = {None}
        for area in sorted(areas, key=lambda a: "" if a is None else a):
            settings = process["areas"].get(area, {"authentication": None, "evidence": []})
            interfaces = _ospf_interfaces(config, process, area) if area is not None else []
            unknown = [i for i in interfaces if (i.ospf_authentication
                       if i.ospf_authentication is not None else settings["authentication"]) in (None, "none")]
            # A configured passive-only process cannot form neighbors on its
            # modeled interfaces. Missing interfaces remain an input limitation.
            all_passive = process["passive_default"] is True and not any(
                state is False for state in process["passive_interfaces"].values())
            if unknown or (not interfaces and not all_passive and settings["authentication"] in (None, "none")):
                detail = ("接口：" + ", ".join(i.name for i in unknown)) if unknown else "未匹配到可完整核对的非被动接口"
                findings.append(_finding(
                    "OSPF-AUTH-REVIEW", "low", "ospf", "OSPF 认证需要人工复核",
                    f"OSPF 进程 {process['process_id']}、区域 {area if area is not None else '未明确'}未能确认有效认证模式；{detail}。",
                    "缺失配置、继承关系或平台默认值使认证状态不确定；不能据此断言邻居未认证或存在可利用攻击路径。",
                    "核对完整进程、区域与接口认证模式、密钥和双方配置，结合设备实际邻居状态验证；密钥应通过受控方式管理。",
                    [process["header"]] + settings["evidence"] + [e for i in unknown for e in i.ospf_evidence]))
    for (vrf, router_id), owners in router_ids.items():
        if len(owners) > 1:
            findings.append(_finding(
                "OSPF-DUPLICATE-ROUTER-ID", "low", "ospf", "多个 OSPF 进程共用 Router ID",
                f"VRF {vrf} 的多个 OSPF 进程共用 Router ID {router_id}。",
                "独立 OSPF 域可能允许共用标识；若域间连接或迁移设计不当，需要核对唯一性约束。",
                "根据 OSPF 域边界和迁移计划核对 Router ID 唯一性；不要仅因不同进程共用标识就直接修改。",
                [p["router_id_evidence"] for p in owners]))
    known = {(p["vrf"], p["process_id"]) for p in processes}
    for interface in config.interfaces.values():
        binding = interface.ospf_binding
        if binding and (interface.vrf, binding["process_id"]) not in known:
            findings.append(_finding(
                "OSPF-AUTH-REVIEW", "low", "ospf", "OSPF 认证需要人工复核",
                f"接口 {interface.name} 绑定 OSPF 进程 {binding['process_id']}，输入未见对应进程配置。",
                "缺失配置、继承关系或平台默认值使认证状态不确定；不能据此断言邻居未认证或存在可利用攻击路径。",
                "核对完整进程、区域与接口认证模式、密钥和双方配置，结合设备实际邻居状态验证；密钥应通过受控方式管理。",
                interface.ospf_evidence or [binding["evidence"]]))
    return findings


def architecture_summary(config: Config, findings) -> dict:
    """Return six stable domains; checked describes coverage, not safety."""
    def finding_value(finding, field):
        return finding.get(field) if isinstance(finding, dict) else getattr(finding, field)

    coverage = {
        "vlan": "检查显式 VLAN、Access/Trunk、PVID 和允许列表；未确认链路两端、动态 VLAN 或二层拓扑。",
        "stp": "检查显式全局/接口/VLAN 启停、模式、边缘端口和 BPDU 过滤；未给出的默认状态保持未知，未确认根桥或环路。",
        "ospf": "检查 IPv4 进程、Router ID、区域、Network、接口绑定、被动接口及认证模式；未确认邻居、密钥有效性或收敛。",
        "acl": "检查已支持 IPv4 ACL 的定义、绑定、宽泛许可和顺序覆盖；未知条件禁用匹配推断，不等同于实际流量验证。",
        "nat": "检查已支持静态/服务器映射、选流 ACL 和地址池引用；未确认公网可达性或转换运行状态。",
        "management_plane": "检查显式 HTTP、Telnet、VTY、SSH、凭据与 SNMP 配置；未确认实际服务、AAA 后端或管理路径可达性。",
    }
    observed = {
        "vlan": len(config.vlans) + sum(i.mode in ("access", "trunk") or i.access_vlan is not None or i.native_vlan is not None
                                             for i in config.interfaces.values()),
        "stp": int(bool(config.stp["evidence"])) + sum(bool(i.stp_evidence) for i in config.interfaces.values()),
        "ospf": sum(p["protocol"] == "ospf" for p in config.routing_processes)
                + sum(bool(i.ospf_evidence) for i in config.interfaces.values()),
        "acl": len(config.acls),
        "nat": len(config.nat) + len(config.nat_pools) + sum(i.nat_role is not None for i in config.interfaces.values()),
        "management_plane": len(config.management_lines) + sum(bool(re.search(
            r"\b(?:aaa|username|local-user|password|secret|ssh|stelnet|telnet|http|snmp)\b", e.text, re.I))
            for e in config.global_commands),
    }
    warning_patterns = {
        "vlan": r"vlan|switchport|port (?:link-type|trunk|access|default)",
        "stp": r"stp|spanning-tree", "ospf": r"ospf|router-id|network|passive-interface|silent-interface|authentication-mode",
        "acl": r"acl|access-list|access-group|traffic-filter|packet-filter|permit|deny",
        "nat": r"\bnat\b", "management_plane": r"vty|ssh|telnet|http|snmp|password|secret|authentication-mode",
    }
    domains = []
    for domain in coverage:
        category = "management" if domain == "management_plane" else domain
        ids = sorted({finding_value(f, "rule_id") for f in findings if finding_value(f, "category") == category})
        incomplete = any(re.search(warning_patterns[domain], w["text"], re.I) for w in config.warnings)
        status = "needs-review" if ids or incomplete else "checked" if observed[domain] else "not-observed"
        domains.append({"domain": domain, "status": status, "observed": observed[domain],
                        "coverage": coverage[domain], "finding_ids": ids})
    return {"scope": "单设备离线配置检查；状态表示已观察配置的检查覆盖，不能证明实时拓扑、邻居或整体网络安全。",
            "domains": domains}
