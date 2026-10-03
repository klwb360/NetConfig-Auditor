from __future__ import annotations

import ipaddress
import re

from .model import ACL, ACLRule, Config, Evidence, Interface, ManagementLine, NAT, Route
from .privacy import redact

MAX_BYTES = 2 * 1024 * 1024
MAX_LINES = 30000
MAX_INTERFACES = 512
MAX_ACL_RULES = 256
MAX_TOTAL_RULES = 2048
VENDORS = ("auto", "cisco", "huawei", "h3c")
ALL_VLANS = set(range(1, 4095))


def vlan_ids(value: str) -> set[int]:
    tokens = value.replace(",", " ").replace("-", " to ").split()
    if tokens == ["all"]:
        return set(ALL_VLANS)
    if tokens == ["none"]:
        return set()
    result: set[int] = set()
    i = 0
    while i < len(tokens):
        start = int(tokens[i])
        end = start
        if i + 2 < len(tokens) and tokens[i + 1] == "to":
            end = int(tokens[i + 2])
            i += 2
        if not 1 <= start <= end <= 4094:
            raise ValueError("VLAN 必须在 1–4094 范围内，且区间不得倒置")
        result.update(range(start, end + 1))
        i += 1
    if not tokens:
        raise ValueError("VLAN 列表为空")
    return result


def detect_vendor(text: str) -> tuple[str, str]:
    scores = {"cisco": 0, "huawei": 0, "h3c": 0}
    markers = {
        "cisco": r"(?im)^\s*(?:hostname |switchport |ip nat inside|ip access-list |snmp-server |!Command:)",
        "huawei": r"(?im)^\s*(?:!Software Version|.*Huawei Versatile Routing|port trunk allow-pass|interface Vlanif|stelnet server|traffic-filter )",
        "h3c": r"(?im)^\s*(?:.*H3C|.*Comware|port trunk permit|interface Vlan-interface|packet-filter |local-user .*class manage)",
    }
    for vendor, pattern in markers.items():
        scores[vendor] = len(re.findall(pattern, text))
    best = max(scores, key=scores.get)
    others = [v for v in scores if scores[v] and v != best]
    if not scores[best] or others:
        raise ValueError("无法可靠识别厂商，或包含混合厂商配置；请用 --vendor 指定，并每次输入一台设备的完整配置")
    return best, "auto: syntax markers"


def _address(tokens: list[str], pos: int) -> tuple[str, int]:
    token = tokens[pos]
    if token == "any":
        return "any", pos + 1
    if token == "host":
        return str(ipaddress.IPv4Address(tokens[pos + 1])) + "/32", pos + 2
    if "/" in token:
        return str(ipaddress.IPv4Network(token, strict=False)), pos + 1
    addr = ipaddress.IPv4Address(token)
    if pos + 1 < len(tokens):
        try:
            wildcard = int(ipaddress.IPv4Address(tokens[pos + 1]))
        except ipaddress.AddressValueError:
            return str(addr) + "/32", pos + 1
        mask = (~wildcard) & 0xffffffff
        # Non-contiguous wildcard masks are retained, never treated as CIDR.
        try:
            net = ipaddress.IPv4Network((int(addr), str(ipaddress.IPv4Address(mask))), strict=False)
            if int(net.netmask) != mask:
                raise ValueError("ambiguous mask")
            return str(net), pos + 2
        except ValueError:
            return f"{addr} wildcard {tokens[pos + 1]}", pos + 2
    return str(addr) + "/32", pos + 1


def _port(tokens: list[str], pos: int) -> tuple[str | None, int]:
    if pos >= len(tokens) or tokens[pos] not in ("eq", "neq", "gt", "lt", "range"):
        return None, pos
    count = 3 if tokens[pos] == "range" else 2
    if pos + count > len(tokens):
        raise ValueError("不完整的端口条件")
    return " ".join(tokens[pos:pos + count]), pos + count


def _acl_rule(text: str, vendor: str, kind: str, seq: int, evidence: Evidence) -> ACLRule:
    t = text.lower().split()
    if t[0].isdigit():
        seq = int(t.pop(0))
    if t[0] == "rule":
        t.pop(0)
        if t[0].isdigit():
            seq = int(t.pop(0))
    action = t.pop(0)
    if action not in ("permit", "deny"):
        raise ValueError("未知 ACL 动作")
    protocol = "ip" if kind == "standard" else t.pop(0)
    rule = ACLRule(seq, action, protocol, evidence=evidence)
    if vendor == "cisco":
        rule.source, pos = _address(t, 0)
        rule.source_port, pos = _port(t, pos)
        if kind != "standard":
            rule.destination, pos = _address(t, pos)
            rule.destination_port, pos = _port(t, pos)
        rule.complete = all(x in ("log", "log-input") for x in t[pos:])
    else:
        pos = 0
        while pos < len(t):
            token = t[pos]
            if token in ("source", "destination"):
                value, pos = _address(t, pos + 1)
                setattr(rule, token, value)
            elif token in ("source-port", "destination-port"):
                value, end = _port(t, pos + 1)
                if end == pos + 1:
                    rule.complete = False
                    break
                setattr(rule, token.replace("-", "_"), value)
                pos = end
            elif token in ("logging", "counting"):
                pos += 1
            else:
                rule.complete = False
                break
    rule.protocol = {"6": "tcp", "17": "udp", "1": "icmp"}.get(protocol, protocol)
    if rule.protocol not in ("ip", "tcp", "udp", "icmp", "gre", "esp", "ah", "ospf"):
        rule.complete = False
    return rule


def _route(text: str, vendor: str, e: Evidence) -> Route:
    t = text.split()[2:]
    vrf = "default"
    if t[0] in ("vrf", "vpn-instance"):
        vrf = t[1]
        t = t[2:]
    if "/" in t[0]:
        destination = str(ipaddress.IPv4Network(t.pop(0), strict=False))
    else:
        destination = str(ipaddress.IPv4Network(t[0] + "/" + t[1], strict=False))
        t = t[2:]
    interface = hop = None
    if not t:
        raise ValueError("静态路由缺少下一跳")
    try:
        hop = str(ipaddress.IPv4Address(t[0]))
        t = t[1:]
    except ipaddress.AddressValueError:
        interface = t.pop(0)
        if t:
            try:
                hop = str(ipaddress.IPv4Address(t[0]))
                t = t[1:]
            except ipaddress.AddressValueError:
                pass
    distance = None
    if t and t[0].isdigit():
        distance = int(t.pop(0))
    if "preference" in t:
        distance = int(t[t.index("preference") + 1])
    return Route(destination, hop, interface, vrf, distance, e)


def _nat(text: str, interface: str | None, e: Evidence) -> NAT:
    t = text.split()
    n = NAT("other", interface, None, None, None, None, None, None, e)
    if text.startswith("ip nat inside source static "):
        n.kind = "static"
        if t[5] in ("tcp", "udp"):
            n.protocol, n.inside = t[5], t[6] + ":" + t[7]
            n.outside, n.outside_port = t[8], t[9]
        elif t[5] == "network":
            n.complete = False
        else:
            n.inside, n.outside = t[5], t[6]
    elif text.startswith("ip nat inside source list "):
        n.kind, n.acl = "outbound", t[5]
        if "pool" in t:
            n.pool = t[t.index("pool") + 1]
    elif text.startswith("nat outbound"):
        n.kind = "outbound"
        if len(t) > 2 and t[2].isdigit():
            n.acl = t[2]
        if "address-group" in t:
            n.pool = t[t.index("address-group") + 1]
    elif text.startswith("nat server "):
        n.kind = "server"
        if "protocol" in t:
            n.protocol = t[t.index("protocol") + 1]
        j, k = t.index("global") + 1, t.index("inside") + 1
        n.outside, n.inside = t[j], t[k]
        if j + 1 < len(t) and t[j + 1] != "inside":
            n.outside_port = t[j + 1]
        if k + 1 < len(t) and t[k + 1].isdigit():
            n.inside += ":" + t[k + 1]
    else:
        n.complete = False
    return n


def _architecture_redact(text: str) -> str:
    # VRP/Comware authentication-mode accepts credentials without a password
    # keyword; retain the algorithm, never its key identifier or value.
    text = redact(text)
    return re.sub(r"(?i)(\bauthentication-mode\s+\S+)\s+.+$",
                  r"\1 [REDACTED]", text)


def _stp_command(s: str, cfg: Config, interface: Interface | None) -> bool:
    """Parse only explicit, supported STP settings, including reset semantics."""
    inverse = s.startswith(("no ", "undo "))
    command = s.split(" ", 1)[1] if inverse else s
    target = cfg.stp
    value = None if inverse else True
    if interface is not None:
        field_name = None
        if command in ("stp enable", "stp disable"):
            interface.stp_enabled = (False if inverse and command == "stp enable"
                                     else None if inverse else command == "stp enable")
            return True
        if command in ("spanning-tree portfast", "spanning-tree portfast trunk",
                       "spanning-tree portfast edge", "spanning-tree portfast edge trunk"):
            field_name = "stp_edge"
        elif command in ("spanning-tree portfast disable", "spanning-tree portfast edge disable"):
            field_name, value = "stp_edge", None if inverse else False
        elif re.fullmatch(r"stp edged-port(?: (enable|disable))?", command):
            field_name = "stp_edge"
            value = None if inverse else not command.endswith(" disable")
        elif re.fullmatch(r"spanning-tree bpdu(guard|filter) (enable|disable)", command):
            field_name = "bpdu_guard" if "bpduguard" in command else "bpdu_filter"
            value = None if inverse else command.endswith(" enable")
        elif re.fullmatch(r"stp bpdu-filter(?: (enable|disable))?", command):
            field_name = "bpdu_filter"
            value = None if inverse else not command.endswith(" disable")
        if field_name:
            setattr(interface, field_name, value)
            return True
        return False
    if command in ("stp enable", "stp disable"):
        target["enabled"] = (False if inverse and command == "stp enable"
                             else None if inverse else command == "stp enable")
        return True
    mode = re.fullmatch(r"(?:spanning-tree mode (pvst|rapid-pvst|mst)|stp mode (stp|rstp|mstp))", command)
    if mode:
        target["mode"] = None if inverse else next(x for x in mode.groups() if x)
        return True
    defaults = {
        "spanning-tree portfast default": "edge_default",
        "spanning-tree portfast edge default": "edge_default",
        "spanning-tree portfast bpduguard default": "bpdu_guard_default",
        "spanning-tree portfast edge bpduguard default": "bpdu_guard_default",
        "spanning-tree portfast bpdufilter default": "bpdu_filter_default",
        "spanning-tree portfast edge bpdufilter default": "bpdu_filter_default",
        "stp bpdu-protection": "bpdu_guard_default",
    }
    if command in defaults:
        target[defaults[command]] = value
        return True
    if command.startswith("spanning-tree vlan "):
        values = vlan_ids(command[len("spanning-tree vlan "):])
        for vid in values:
            target["vlan_enabled"][vid] = not inverse
        return True
    return False


def _area_id(value: str) -> str:
    if "." in value:
        return str(int(ipaddress.IPv4Address(value)))
    number = int(value)
    if not 0 <= number <= 0xffffffff:
        raise ValueError("OSPF area 超出范围")
    return str(number)


def _ospf_process(s: str, e: Evidence, cfg: Config) -> dict:
    t = s.split()
    if t[0] == "router":
        if len(t) < 3 or not t[2].isdigit():
            raise ValueError("Cisco OSPF 进程必须指定整数 ID")
        t = t[1:]
    t = t[1:]
    process_id = t.pop(0) if t and t[0].isdigit() else "1"
    if not 1 <= int(process_id) <= 65535:
        raise ValueError("OSPF process ID 超出范围")
    router_id, vrf = None, "default"
    while t:
        keyword = t.pop(0)
        if keyword == "router-id":
            router_id = t.pop(0)
        elif keyword in ("vrf", "vpn-instance"):
            vrf = t.pop(0)
        else:
            raise ValueError("未支持的 OSPF 进程参数")
    proc = next((p for p in cfg.routing_processes if p["protocol"] == "ospf"
                 and p.get("process_id") == process_id and p.get("vrf") == vrf), None)
    if proc is None:
        proc = {"protocol": "ospf", "process_id": process_id, "vrf": vrf,
                "header": e, "commands": [], "router_id": None,
                "router_id_evidence": None, "networks": [], "areas": {},
                "passive_default": None, "passive_interfaces": {}}
        cfg.routing_processes.append(proc)
    if router_id is not None:
        proc["router_id"], proc["router_id_evidence"] = router_id, e
    return proc


def _ospf_command(s: str, proc: dict, area: str | None, e: Evidence) -> bool:
    inverse = s.startswith(("no ", "undo "))
    command = s.split(" ", 1)[1] if inverse else s
    t = command.split()
    if t[0] == "router-id" and len(t) in (1, 2):
        if not inverse and len(t) != 2:
            return False
        proc["router_id"] = None if inverse else t[1]
        proc["router_id_evidence"] = e
        return True
    if t[0] in ("passive-interface", "silent-interface") and len(t) >= 2:
        name = "".join(t[1:])
        if name in ("default", "all"):
            proc["passive_default"] = not inverse
        else:
            proc["passive_interfaces"][name] = not inverse
        return True
    if t[0] == "network":
        if area is None:
            if len(t) != 5 or t[3] != "area":
                return False
            network_area = _area_id(t[4])
        else:
            if len(t) != 3:
                return False
            network_area = area
        address = str(ipaddress.IPv4Address(t[1]))
        wildcard = str(ipaddress.IPv4Address(t[2]))
        mask = (~int(ipaddress.IPv4Address(wildcard))) & 0xffffffff
        try:
            prefix = str(ipaddress.IPv4Network((int(ipaddress.IPv4Address(address)),
                         str(ipaddress.IPv4Address(mask))), strict=False))
            if int(ipaddress.IPv4Network(prefix).netmask) != mask:
                prefix = None
        except ValueError:
            prefix = None
        identity = (address, wildcard, network_area)
        proc["networks"] = [n for n in proc["networks"]
                            if (n["address"], n["wildcard"], n["area"]) != identity]
        if not inverse:
            proc["networks"].append({"address": address, "wildcard": wildcard,
                                     "prefix": prefix, "area": network_area, "evidence": e})
            proc["areas"].setdefault(network_area, {"authentication": None, "evidence": []})
        return True
    authentication = None
    auth_area = area
    if t[0] == "area" and len(t) >= 3 and t[2] == "authentication":
        auth_area = _area_id(t[1])
        if len(t) == 3:
            authentication = "simple"
        elif len(t) == 4 and t[3] == "message-digest":
            authentication = "message-digest"
        else:
            return False
    elif t[0] == "authentication-mode" and area is not None:
        if inverse and len(t) == 1:
            authentication = None
        elif len(t) >= 2 and t[1] in ("simple", "md5", "hmac-md5", "hmac-sha256", "hmac-sha-256", "none", "null"):
            authentication = "none" if t[1] in ("none", "null") else t[1]
        else:
            return False
    else:
        return False
    if auth_area is None:
        return False
    settings = proc["areas"].setdefault(auth_area, {"authentication": None, "evidence": []})
    settings["authentication"] = None if inverse else authentication
    settings["evidence"].append(e)
    return True


def _ospf_interface(s: str, interface: Interface, e: Evidence) -> bool:
    inverse = s.startswith(("no ", "undo "))
    command = s.split(" ", 1)[1] if inverse else s
    binding = re.fullmatch(r"(?:ip ospf|ospf enable) (\d+) area (\S+)", command)
    if binding:
        process_id, area = binding.groups()
        if not 1 <= int(process_id) <= 65535:
            raise ValueError("OSPF process ID 超出范围")
        interface.ospf_binding = None if inverse else {"process_id": process_id,
                                                       "area": _area_id(area), "evidence": e}
        return True
    if inverse and command in ("ip ospf", "ospf enable"):
        interface.ospf_binding = None
        return True
    if re.fullmatch(r"ip ospf authentication(?: (message-digest|null))?", command):
        interface.ospf_authentication = (None if inverse else "message-digest"
            if command.endswith("message-digest") else "none" if command.endswith("null") else "simple")
        return True
    auth = re.match(r"^ospf authentication-mode (\S+)(?:\s+.*)?$", command)
    if auth:
        if auth[1] not in ("simple", "md5", "hmac-md5", "hmac-sha256", "hmac-sha-256", "none", "null"):
            return False
        interface.ospf_authentication = None if inverse else "none" if auth[1] in ("none", "null") else auth[1]
        return True
    if inverse and command == "ospf authentication-mode":
        interface.ospf_authentication = None
        return True
    if re.match(r"^ip ospf (?:authentication-key|message-digest-key)\s+", command):
        # Keys alone do not enable an authentication algorithm.
        return True
    return False


def _parse_config(text: str, vendor: str = "auto") -> Config:
    if vendor not in VENDORS:
        raise ValueError("厂商必须为 auto / cisco / huawei / h3c")
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("配置超过 2 MiB 限制")
    if any(ord(c) < 32 and c not in "\n\r\t" for c in text):
        raise ValueError("配置含控制字符，请先移除终端转义序列")
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        raise ValueError("配置超过 30000 行限制")
    if not text.strip():
        raise ValueError("配置为空")
    detection = "explicit vendor"
    if vendor == "auto":
        vendor, detection = detect_vendor(text)
    cfg = Config(vendor, detection, "unknown", line_count=len(lines))
    context: tuple[str, object] | None = None
    banner = None
    total_rules = 0

    def warn(e: Evidence, reason: str) -> None:
        cfg.unsupported_count += 1
        if len(cfg.warnings) < 200:
            cfg.warnings.append({"line": e.line, "text": e.text, "reason": reason})

    for num, raw in enumerate(lines, 1):
        s = raw.strip()
        if banner is not None:
            if banner in s:
                banner = None
            continue
        if not s or s in ("!", "#", "return", "end", "exit", "quit"):
            if s:
                if s in ("exit", "quit") and context and context[0] == "ospf-area":
                    context = ("routing", context[1][0])
                else:
                    context = None
            continue
        if s.startswith(("!", "#")):
            continue
        if s.startswith("banner "):
            parts = s.split(None, 2)
            if len(parts) == 3:
                value = parts[2]
                delim = value[:2] if value.startswith("^") else value[0]
                if delim not in value[len(delim):]:
                    banner = delim
            context = None
            continue
        cfg.relevant_lines += 1
        e = Evidence(num, _architecture_redact(s))
        if vendor == "cisco" and not raw[:1].isspace():
            context = None
        try:
            inverse = s[3:] if s.startswith("no ") else s[5:] if s.startswith("undo ") else None
            stp_command = inverse or s
            if stp_command.startswith(("stp ", "spanning-tree ")):
                interface = context[1] if context and context[0] == "interface" else None
                evidence = interface.stp_evidence if interface is not None else cfg.stp["evidence"]
                evidence.append(e)
                if interface is not None:
                    interface.evidence.append(e)
                else:
                    cfg.global_commands.append(e)
                    context = None
                if _stp_command(s, cfg, interface):
                    cfg.recognized_lines += 1
                else:
                    warn(e, "STP 变体未建模；未据此推断启停状态或拓扑")
                continue
            if (inverse and re.match(r"^(?:router ospf(?:\s+\d+|$)|ospf(?:\s+\d+|\s+(?:router-id|vpn-instance)\b|$))", inverse)
                    and not (context and context[0] == "interface")):
                removed = _ospf_process(inverse, e, cfg)
                cfg.routing_processes.remove(removed)
                context = None
                cfg.recognized_lines += 1
                continue
            if inverse and inverse.startswith(("ip nat pool ", "nat address-group ")):
                t = inverse.split()
                cfg.nat_pools.pop(t[3] if t[0] == "ip" else t[2], None)
                cfg.recognized_lines += 1
                continue
            if inverse and inverse not in ("ip nat inside", "ip nat outside") and inverse.startswith(("ip nat ", "nat outbound", "nat server")):
                owner = context[1].name if context and context[0] == "interface" else None
                cfg.nat = [n for n in cfg.nat if not (n.interface == owner and n.evidence.text.startswith(inverse))]
                cfg.recognized_lines += 1
                continue
            if inverse and inverse.startswith(("ip route ", "ip route-static ")):
                removed = _route(inverse, vendor, e)
                cfg.routes = [r for r in cfg.routes if (r.destination, r.next_hop, r.interface, r.vrf) != (removed.destination, removed.next_hop, removed.interface, removed.vrf)]
                cfg.recognized_lines += 1
                continue
            if s.startswith(("hostname ", "sysname ")):
                cfg.hostname = redact(s.split(None, 1)[1])
            elif re.match(r"^interface\s+\S+", s) and (context is None or not raw[:1].isspace()):
                name = s.split(None, 1)[1].replace(" ", "")
                if name.lower().startswith("range"):
                    context = ("unsupported", name)
                    warn(e, "interface range 必须展开后输入")
                    continue
                iface = cfg.interfaces.setdefault(name, Interface(name, num))
                if len(cfg.interfaces) > MAX_INTERFACES:
                    raise OverflowError("接口数量超过 512 个限制")
                iface.evidence.append(e)
                context = ("interface", iface)
            elif re.match(r"^ip access-list (standard|extended) \S+$", s):
                _, _, kind, name = s.split()
                acl = cfg.acls.setdefault(name, ACL(name, kind, num))
                context = ("acl", acl)
            elif re.match(r"^acl (?:number |basic |advanced |name )?\S+", s) and (context is None or not raw[:1].isspace()):
                t = s.split()
                name = t[2] if t[1] in ("number", "basic", "advanced", "name") else t[1]
                kind = "standard" if t[1] == "basic" or (name.isdigit() and 2000 <= int(name) < 3000) else "extended"
                if "name" in t and t[1] != "name":
                    name = t[t.index("name") + 1]
                acl = cfg.acls.setdefault(name, ACL(name, kind, num))
                if "auto" in t:
                    acl.ordered = False
                    warn(e, "match-order auto 的硬件排序未建模，禁用遮蔽推断")
                context = ("acl", acl)
            elif re.match(r"^access-list \S+ (?:permit|deny) ", s):
                _, name, rule_text = s.split(None, 2)
                kind = "standard" if name.isdigit() and (1 <= int(name) <= 99 or 1300 <= int(name) <= 1999) else "extended"
                acl = cfg.acls.setdefault(name, ACL(name, kind, num))
                rule = _acl_rule(rule_text, vendor, kind, len(acl.rules) * 10 + 10, e)
                total_rules += 1
                if len(acl.rules) >= MAX_ACL_RULES or total_rules > MAX_TOTAL_RULES:
                    raise OverflowError("ACL 规则超过限制：每 ACL 256 条、总计 2048 条")
                acl.rules.append(rule)
                if not rule.complete:
                    warn(e, "ACL 条件未完整解析，禁用此规则的安全/遮蔽推断")
            elif re.match(r"^(?:line vty|user-interface vty) \d", s):
                vty = ManagementLine(s, num, evidence=[e])
                cfg.management_lines.append(vty)
                context = ("vty", vty)
            elif s.startswith(("vlan ", "vlan batch ")):
                value = s[11:] if s.startswith("vlan batch ") else s[5:]
                ids = vlan_ids(value)
                for vid in ids:
                    cfg.vlans[vid] = {"name": "", "evidence": e}
                context = ("vlan", sorted(ids))
            elif re.match(r"^(?:router ospf(?:\s+\d+(?:\s|$)|$)|ospf(?:\s+\d+(?:\s|$)|\s+(?:router-id|vpn-instance)\b|$))", s) and not (context and context[0] == "interface"):
                proc = _ospf_process(s, e, cfg)
                context = ("routing", proc)
            elif s.startswith(("router bgp ", "bgp ", "router rip")):
                proc = {"protocol": s.split()[1] if s.startswith("router ") else s.split()[0], "header": e, "commands": []}
                cfg.routing_processes.append(proc)
                context = ("routing", proc)
            elif s.startswith(("ip route ", "ip route-static ")):
                cfg.routes.append(_route(s, vendor, e))
            elif s.startswith("ip nat pool ") or s.startswith("nat address-group "):
                t = s.split()
                name = t[3] if t[0] == "ip" else t[2]
                cfg.nat_pools[name] = {"evidence": e}
            elif s.startswith("ip nat ") and context is None:
                n = _nat(s, None, e)
                cfg.nat.append(n)
                if not n.complete:
                    warn(e, "NAT 变体未完整建模，只保存原文")
            elif context and context[0] == "interface":
                it = context[1]
                it.evidence.append(e)
                if (inverse or s).startswith(("ip ospf", "ospf ")):
                    it.ospf_evidence.append(e)
                    if not _ospf_interface(s, it, e):
                        warn(e, "OSPF 接口变体未建模；认证和邻居状态仍需核对")
                elif s in ("shutdown", "undo shutdown", "no shutdown"):
                    it.shutdown = s == "shutdown"
                elif s.startswith("description "):
                    it.description = e.text[12:]
                elif s.startswith("ip address "):
                    t = s.split()
                    if t[2] in ("dhcp", "negotiated", "unnumbered"):
                        warn(e, "动态/借用地址无法静态确认")
                    else:
                        value = t[2] if "/" in t[2] else t[2] + "/" + t[3]
                        address = str(ipaddress.IPv4Interface(value))
                        if "secondary" not in t and "sub" not in t:
                            it.addresses = [address] + [x for x in it.addresses[1:] if x != address]
                        elif address not in it.addresses:
                            it.addresses.append(address)
                elif s.startswith(("ip vrf forwarding ", "vrf forwarding ", "ip binding vpn-instance ")):
                    it.vrf = s.split()[-1]
                elif s.startswith(("switchport mode ", "port link-type ")):
                    it.mode = s.split()[-1]
                elif s == "no switchport":
                    it.mode = "routed"
                elif s.startswith(("switchport access vlan ", "port default vlan ", "port access vlan ")):
                    it.access_vlan = next(iter(vlan_ids(s.split()[-1])))
                elif s.startswith(("switchport trunk native vlan ", "port trunk pvid vlan ")):
                    it.native_vlan = next(iter(vlan_ids(s.split()[-1])))
                elif s.startswith(("switchport trunk allowed vlan ", "port trunk allow-pass vlan ", "port trunk permit vlan ", "undo port trunk allow-pass vlan ", "undo port trunk permit vlan ")):
                    value = s.split("vlan ", 1)[1]
                    mode = "replace" if vendor == "cisco" else "add"
                    if s.startswith("undo "):
                        mode = "remove"
                    if value.split()[0] in ("add", "remove", "except"):
                        mode, value = value.split(None, 1)
                    values = vlan_ids(value)
                    if mode == "except":
                        values = ALL_VLANS - values
                    elif mode in ("add", "remove"):
                        default = ALL_VLANS if vendor == "cisco" else {1}
                        current = set(it.allowed_vlans) if it.allowed_vlans is not None else default
                        values = current | values if mode == "add" else current - values
                    it.allowed_vlans = sorted(values)
                elif re.match(r"^ip access-group \S+ (in|out)$", s):
                    t = s.split()
                    it.acl_bindings[t[3]] = t[2]
                elif re.match(r"^traffic-filter (inbound|outbound) acl (?:name )?\S+$", s):
                    t = s.split()
                    it.acl_bindings[t[1]] = t[-1]
                elif re.match(r"^packet-filter \S+ (inbound|outbound)$", s):
                    t = s.split()
                    it.acl_bindings[t[2]] = t[1]
                elif s in ("ip nat inside", "ip nat outside"):
                    it.nat_role = s.split()[-1]
                elif s.startswith(("nat outbound", "nat server ")):
                    n = _nat(s, it.name, e)
                    cfg.nat.append(n)
                    if not n.complete:
                        warn(e, "NAT 变体未完整建模")
                elif s.startswith(("no ", "undo ")):
                    if s in ("no ip address", "undo ip address"):
                        it.addresses.clear()
                    elif inverse and inverse.startswith("ip address "):
                        t = inverse.split()
                        value = t[2] if "/" in t[2] else t[2] + "/" + t[3]
                        removed = str(ipaddress.IPv4Interface(value))
                        it.addresses = [x for x in it.addresses if x != removed]
                    elif inverse in ("switchport trunk allowed vlan",):
                        it.allowed_vlans = None
                    elif inverse in ("switchport access vlan", "port access vlan", "port default vlan"):
                        it.access_vlan = None
                    elif inverse in ("ip nat inside", "ip nat outside"):
                        it.nat_role = None
                    elif s.startswith(("no ip access-group ", "undo traffic-filter ", "undo packet-filter ")):
                        t = s.split()
                        direction = next((x for x in t if x in ("in", "out", "inbound", "outbound")), None)
                        if direction:
                            it.acl_bindings.pop(direction, None)
                        else:
                            warn(e, "未识别 ACL 解绑方向")
                    else:
                        warn(e, "未支持此接口撤销命令")
                else:
                    warn(e, "接口命令未建模")
            elif context and context[0] == "acl":
                acl = context[1]
                if s.startswith("remark ") or re.match(r"^\d+ remark ", s) or s.startswith("description "):
                    pass
                elif s.startswith("undo rule ") or re.match(r"^no \d+$", s):
                    seq = int(s.split()[-1])
                    acl.rules = [x for x in acl.rules if x.sequence != seq]
                else:
                    rule = _acl_rule(s, vendor, acl.kind, len(acl.rules) * 10 + 10, e)
                    total_rules += 1
                    if len(acl.rules) >= MAX_ACL_RULES or total_rules > MAX_TOTAL_RULES:
                        raise OverflowError("ACL 规则超过限制：每 ACL 256 条、总计 2048 条")
                    acl.rules = [x for x in acl.rules if x.sequence != rule.sequence]
                    acl.rules.append(rule)
                    if not rule.complete:
                        warn(e, "ACL 条件未完整解析，禁用此规则的安全/遮蔽推断")
            elif context and context[0] == "vty":
                vty = context[1]
                vty.evidence.append(e)
                if s.startswith(("transport input ", "protocol inbound ")):
                    vty.transport = s.split()[2:]
                elif s in ("login", "login local", "no login") or s.startswith(("login authentication ", "authentication-mode ")):
                    vty.authentication = e.text
                elif s.startswith(("exec-timeout ", "idle-timeout ")):
                    t = s.split()
                    minutes = int(t[1])
                    seconds = int(t[2]) if len(t) > 2 else 0
                    if minutes < 0 or not 0 <= seconds <= 59:
                        raise ValueError("不合法的会话超时")
                    vty.idle_seconds = minutes * 60 + seconds
                elif s.startswith("access-class ") and len(s.split()) == 3:
                    t = s.split()
                    vty.acl_bindings[t[2]] = t[1]
                elif s.startswith("acl ") and len(s.split()) == 3:
                    t = s.split()
                    vty.acl_bindings[t[2]] = t[1]
                elif s.startswith(("password ", "set authentication password ")):
                    pass
                else:
                    warn(e, "VTY 命令未建模")
            elif context and context[0] == "vlan" and s.startswith(("name ", "description ")):
                for vid in context[1]:
                    cfg.vlans[vid]["name"] = e.text.split(None, 1)[1]
            elif context and context[0] in ("routing", "ospf-area"):
                proc, area = context[1] if context[0] == "ospf-area" else (context[1], None)
                proc["commands"].append(e)
                if proc["protocol"] != "ospf":
                    warn(e, "此动态路由仅提取进程与原文，未验证协议策略")
                elif re.fullmatch(r"area \S+", s):
                    area = _area_id(s.split()[1])
                    proc["areas"].setdefault(area, {"authentication": None, "evidence": []})
                    context = ("ospf-area", (proc, area))
                elif inverse and re.fullmatch(r"area \S+", inverse):
                    removed = _area_id(inverse.split()[1])
                    proc["areas"].pop(removed, None)
                    proc["networks"] = [n for n in proc["networks"] if n["area"] != removed]
                    context = ("routing", proc)
                elif not _ospf_command(s, proc, area, e):
                    warn(e, "OSPF 变体未建模；未确认邻居、拓扑或协议运行状态")
                elif (inverse or s).startswith("network ") and any(
                        n["evidence"] is e and n["prefix"] is None for n in proc["networks"]):
                    warn(e, "OSPF 非连续 wildcard 已保留，但不转为 CIDR 或据此检查 Network 范围")
            elif context and context[0] == "unsupported":
                warn(e, "未支持的配置块")
            elif s.startswith(("aaa", "local-user ", "username ", "enable ", "ip ssh ", "ssh server ", "stelnet ", "telnet ", "undo telnet ", "http ", "undo http ", "ip http ", "no ip http ", "snmp", "undo snmp", "no snmp", "no ip ssh", "service ", "no service ", "logging ", "info-center ", "version ", "irf ", "stp ", "ip source routing", "no ip source routing")):
                cfg.global_commands.append(e)
                context = None
            else:
                warn(e, "命令未建模；不能据此判定合规")
                continue
            cfg.recognized_lines += 1
        except (ValueError, IndexError) as exc:
            warn(e, "格式错误或未支持的语法（" + type(exc).__name__ + "）")
    if banner is not None:
        warn(Evidence(len(lines), "banner [CONTENT OMITTED]"), "banner 未闭合，后续内容未审计")
    for acl in cfg.acls.values():
        if acl.ordered:
            acl.rules.sort(key=lambda r: r.sequence)
    return cfg


# Do not return a partial IR when a resource ceiling is exceeded.
def parse_config(text: str, vendor: str = "auto") -> Config:
    try:
        return _parse_config(text, vendor)
    except OverflowError as exc:
        raise ValueError(str(exc)) from None
