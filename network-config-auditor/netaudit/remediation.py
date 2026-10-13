"""Deterministic, offline command suggestions derived from redacted configuration.

``commands`` contains complete scripts whose required values are known. Changes
that need a business decision, a new secret, or version-specific syntax belong
to ``command_templates``. Neither collection is executed by NetConfig Auditor. Source
scopes are validated before interpolation; source commands are never replayed.
"""
from __future__ import annotations

import re

from .model import Config, Finding
from .branding import APPLICATION_NAME


SUPPORTED = {"cisco", "ruijie", "huawei", "h3c"}
IOS_STYLE = {"cisco", "ruijie"}
BASE_NOTE = (
    "先在特权/用户视图执行只读核查，核对设备型号和软件版本。整改脚本需由管理员确认后执行；"
    f"先备份配置并保留 Console/带外或备用管理会话，验证业务后再自行保存。{APPLICATION_NAME} 不连接设备、"
    "不执行命令，也不自动保存配置。模板中的 <参数名> 必须替换，不能原样粘贴执行。"
)


def _name(value: str) -> str | None:
    """A single CLI name must not introduce whitespace, control chars or tokens."""
    return value if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,63}", value) else None


def _interface(value: str) -> str | None:
    # Permit the one conventional type/number space, not arbitrary CLI tokens.
    return value if re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{0,31} ?\d+(?:/\d+){0,3}(?:\.\d+)?", value) else None


def _line(value: str, vendor: str) -> str | None:
    prefix = r"line (?:vty|console|con)" if vendor in IOS_STYLE else r"user-interface (?:vty|console|aux)"
    match = re.fullmatch(prefix + r" (\d{1,3})(?: (\d{1,3}))?", value)
    if not match or int(match[1]) > 255 or (match[2] is not None and not int(match[1]) <= int(match[2]) <= 255):
        return None
    return value


def _script(vendor: str, *lines: str) -> str:
    return "\n".join((["configure terminal"] + list(lines) + ["end"]) if vendor in IOS_STYLE
                     else (["system-view"] + list(lines) + ["return"]))


def _scoped_script(vendor: str, scope: str, command: str) -> str:
    return _script(vendor, scope, command, "exit" if vendor in IOS_STYLE else "quit")


def _interfaces(finding: Finding, config: Config) -> list[str]:
    lines = {e.line for e in finding.evidence}
    return [name for name, interface in config.interfaces.items()
            if _interface(name) and (name in finding.affected_objects or
               any(e.line in lines for e in interface.evidence + interface.stp_evidence + interface.ospf_evidence))]


def _management(finding: Finding, config: Config) -> list[str]:
    lines = {e.line for e in finding.evidence}
    return [line.name for line in config.management_lines
            if _line(line.name, config.vendor) and (line.name in finding.affected_objects or
                any(e.line in lines for e in line.evidence))]


def _checks(vendor: str, category: str) -> list[str]:
    if vendor in IOS_STYLE:
        commands = {
            "management": ["show ip ssh", "show running-config"],
            "vlan": ["show vlan", "show interfaces switchport" if vendor == "cisco" else "show interface switchport"],
            "stp": ["show spanning-tree", "show running-config"],
            "ospf": ["show ip ospf neighbor", "show ip ospf interface", "show running-config"],
            "acl": ["show access-lists", "show running-config"],
            "interface": ["show ip interface brief", "show running-config"],
            "routing": ["show ip route", "show running-config"],
            "nat": ["show ip nat translations", "show running-config"],
        }
        return ["show version"] + commands.get(category, ["show running-config"])
    commands = {
        "management": ["display ssh server status", "display current-configuration"],
        "vlan": ["display vlan", "display current-configuration"],
        "stp": ["display stp brief", "display current-configuration"],
        "ospf": ["display ospf peer", "display ospf interface", "display current-configuration"],
        "acl": ["display acl all", "display current-configuration"],
        "interface": ["display ip interface brief", "display current-configuration"],
        "routing": ["display ip routing-table", "display current-configuration"],
        "nat": ["display nat session", "display current-configuration"],
    }
    return ["display version"] + commands.get(category, ["display current-configuration"])


def _credential(finding: Finding, config: Config) -> str:
    vendor = config.vendor
    templates = []
    for evidence in finding.evidence:
        words = evidence.text.split()
        if len(words) >= 2 and words[0] == "enable" and vendor in IOS_STYLE:
            level = re.search(r"\blevel (\d+)\b", evidence.text)
            role = re.search(r"\brole (\S+)\b", evidence.text)
            if level:
                parameter = " level " + level[1] if 0 <= int(level[1]) <= 15 else " level <VERIFIED_ENABLE_LEVEL>"
            elif role:
                parameter = " role " + role[1] if vendor == "ruijie" and _name(role[1]) else " <VERIFIED_ENABLE_SCOPE>"
            else:
                parameter = ""
            # RGOS and older IOS support secret with cleartext input; the device
            # stores a protected value. Stronger algorithm support varies.
            command = "enable secret" + parameter + (" 0" if vendor == "ruijie" else "") + " <NEW_STRONG_PASSWORD>"
            templates.append(_script(vendor, command))
        elif len(words) >= 2 and words[0] == "username" and vendor in IOS_STYLE and _name(words[1]):
            command = f"username {words[1]} secret" + (" 0" if vendor == "ruijie" else "") + " <NEW_STRONG_PASSWORD>"
            templates.append(_script(vendor, command))
        elif len(words) >= 2 and words[0] == "local-user" and vendor not in IOS_STYLE and _name(words[1]):
            if vendor == "huawei":
                templates.append(_script(vendor, "aaa", f"local-user {words[1]} password irreversible-cipher <NEW_STRONG_PASSWORD>", "quit"))
            else:
                templates.append(_scoped_script(vendor, f"local-user {words[1]}", "password irreversible-cipher <NEW_STRONG_PASSWORD>"))
    for scope in _management(finding, config):
        if vendor in IOS_STYLE:
            # Require a verified existing local account and AAA design first;
            # changing authentication blindly can lock out every administrator.
            templates.append(_scoped_script(vendor, scope, "login local"))
        else:
            templates.append(_scoped_script(vendor, scope, "authentication-mode aaa" if vendor == "huawei" else "authentication-mode scheme"))
    finding.command_templates = list(dict.fromkeys(templates))
    return ("新密码由管理员在设备侧受控输入；报告不会恢复原密码。secret 的可用算法及存储强度因版本而异，"
            "应优先采用平台支持的强哈希/不可逆保护；旧 RGOS 的 MD5 secret 只适合作为过渡，不等同于现代强哈希。"
            "执行 username/enable secret 前用设备 ? 核对语法并保留原权限；新会话验证成功后再人工清理旧 password。"
            "线路切换本地/AAA 认证前必须先验证账号、AAA 列表及回退；login local 不是创建账号。")


def enrich_findings(findings: list[Finding], config: Config) -> None:
    """Add complete independent scripts, templates and read-only checks in place."""
    vendor = config.vendor
    for finding in findings:
        # Old suggestions contain bare global or line-mode commands. Rebuild
        # those supported suggestions with explicit entry/exit modes below.
        finding.commands = []
        finding.command_templates = []
        finding.verification_commands = _checks(vendor, finding.category) if vendor in SUPPORTED else []
        finding.command_notes = BASE_NOTE
        if vendor not in SUPPORTED:
            finding.command_notes += " 厂商未识别，无法选择可靠的 CLI 语法；请依据实际平台手册整改。"
            continue
        rule = finding.rule_id
        scopes = _management(finding, config)
        interfaces = _interfaces(finding, config)
        note = ""
        if rule == "MGMT-SSHV1":
            if vendor in IOS_STYLE:
                finding.commands = [_script(vendor, "ip ssh version 2")]
                note = "先确认 SSHv2 客户端、新会话和备用管理路径；show ip ssh 应确认只支持版本 2。此脚本不重新生成设备密钥。"
            else:
                note = "此输入含 IOS 风格 SSHv1 命令，与所选厂商不符；核对厂商和原始导出，不套用跨厂商修改。"
        elif rule == "MGMT-SSH-RETRIES":
            if vendor in IOS_STYLE:
                finding.commands = [_script(vendor, "ip ssh authentication-retries 3")]
                note = "示例基线为 3 次；核对本单位认证策略及该版本支持的参数范围。"
        elif rule == "MGMT-HTTP":
            command = "no ip http server" if vendor in IOS_STYLE else "undo http server enable"
            # Preserve the exact already-observed enable-command family.
            if vendor not in IOS_STYLE:
                source = next((e.text.lower() for e in finding.evidence if e.text.lower() in ("http server", "http enable")), None)
                if source:
                    command = "undo " + source
            finding.commands = [_script(vendor, command)]
            note = "先验证 SSH/HTTPS 或带外可用，再关闭明文 HTTP；此脚本不启用新的 HTTPS 服务。"
        elif rule == "MGMT-TELNET-SERVER":
            if vendor not in IOS_STYLE:
                command = "undo telnet server enable"
                if any(e.text.lower() == "telnet server" for e in finding.evidence):
                    command = "undo telnet server"
                finding.commands = [_script(vendor, command)]
            note = "先验证 SSH 新会话与备用路径，再关闭 Telnet；IOS/RGOS 的 Telnet 服务需逐段核对 VTY 协议，不直接套用 undo 命令。"
        elif rule in {"MGMT-VTY-TELNET", "MGMT-VTY-UNKNOWN"}:
            command = "transport input ssh" if vendor in IOS_STYLE else "protocol inbound ssh"
            scripts = [_scoped_script(vendor, scope, command) for scope in scopes]
            if rule == "MGMT-VTY-TELNET":
                finding.commands = scripts
            else:
                finding.command_templates = scripts
            note = "先确认 SSH 服务、设备密钥、认证和客户端可用，再在列出的每一段 VTY 限制入站协议。未显式给出的协议可能由默认值决定，需核查后才执行候选脚本。"
        elif rule == "MGMT-VTY-TIMEOUT":
            command = "exec-timeout 10 0" if vendor in IOS_STYLE else "idle-timeout 10 0"
            finding.commands = [_scoped_script(vendor, scope, command) for scope in scopes]
            note = "示例基线为空闲 10 分钟；该值不是长任务允许时长，需按本单位需求调整。"
        elif rule == "MGMT-VTY-NOAUTH":
            command = "login local" if vendor in IOS_STYLE else "authentication-mode aaa" if vendor == "huawei" else "authentication-mode scheme"
            finding.command_templates = [_scoped_script(vendor, scope, command) for scope in scopes]
            note = "模板依赖已验证的本地账号或 AAA 方法与回退，不创建账号。先在新会话验证认证成功，避免将 no login 直接改成无法登录的状态。"
        elif rule == "MGMT-VTY-SOURCE":
            if vendor in IOS_STYLE:
                # Numeric ACL placeholder avoids inventing a business subnet
                # or colliding with an existing fixed ACL name/number.
                for scope in scopes:
                    finding.command_templates.append(_script(vendor,
                        "ip access-list standard <UNUSED_STANDARD_ACL_ID>",
                        "permit <ADMIN_NETWORK> <ADMIN_WILDCARD_MASK>", "exit", scope,
                        "access-class <UNUSED_STANDARD_ACL_ID> in", "exit"))
            else:
                for scope in scopes:
                    finding.command_templates.append(_script(vendor,
                        "acl number <UNUSED_BASIC_ACL_ID>",
                        "rule permit source <ADMIN_NETWORK> <ADMIN_WILDCARD_MASK>", "quit", scope,
                        "acl <UNUSED_BASIC_ACL_ID> inbound", "quit"))
            note = ("填写未占用的基础/标准 IPv4 ACL 编号和全部管理员、跳板机及运维系统的真实来源网段/反掩码。"
                    "所选平台的 ACL 编号范围需用 ? 核对；不要把设备管理地址当作管理员来源网段。"
                    "先创建并审查允许规则，再绑定 VTY；隐式拒绝可能锁定远程管理，必须保留回退并验证许可/拒绝来源。")
        elif rule == "MGMT-CREDENTIAL":
            note = _credential(finding, config)
        elif rule == "MGMT-SNMP-COMMUNITY":
            if vendor in IOS_STYLE:
                command = "no snmp-server community <OLD_COMMUNITY>"
            else:
                permission = "write" if any(re.search(r"\bwrite\b", e.text) for e in finding.evidence) else "read"
                command = f"undo snmp-agent community {permission} <OLD_COMMUNITY>"
            finding.command_templates = [_script(vendor, command)]
            finding.verification_commands = (["show version", "show snmp group", "show snmp user", "show running-config"]
                                              if vendor in IOS_STYLE else ["display version", "display snmp-agent group", "display snmp-agent usm-user", "display current-configuration"])
            note = ("先按本型号/版本文档部署并验证 SNMPv3 authPriv、只读视图、来源限制以及监控轮询/告警，确认迁移成功后再删除旧 community。"
                    "<OLD_COMMUNITY> 在设备侧受控填写，报告内的 [REDACTED] 不是可执行参数；不提供随机账号、密钥或未经核验的 AES 语法。")
        elif rule == "VLAN-UNDEFINED":
            match = re.search(r"\bVLAN (\d{1,4})\b", finding.problem)
            vid = int(match[1]) if match else None
            if vid is not None and 2 <= vid <= 4094 and vid not in config.vlans:
                finding.commands = [_script(vendor, f"vlan {vid}", "exit" if vendor in IOS_STYLE else "quit")]
                finding.verification_commands += [f"show vlan id {vid}" if vendor in IOS_STYLE else f"display vlan {vid}"]
            note = ("先用 show/display vlan 核查设备的 VLAN 数据库、完整导出、批量定义和动态/隐式创建行为。"
                    "仅当设备确认该 VLAN 缺失且业务需要创建时执行创建脚本；如果端口引用写错，应按业务规划修正引用。"
                    "创建 VLAN 不会替你配置网关、上联允许列表或重分配端口。")
        elif rule in {"VLAN-TRUNK-ALL", "VLAN-NATIVE-1", "VLAN-PVID-NOT-ALLOWED"}:
            if vendor in IOS_STYLE:
                command = "switchport trunk allowed vlan <APPROVED_VLAN_LIST>" if rule != "VLAN-NATIVE-1" else "switchport trunk native vlan <APPROVED_NATIVE_VLAN_ID>"
            else:
                allow_command = "port trunk allow-pass vlan" if vendor == "huawei" else "port trunk permit vlan"
                command = allow_command + " <APPROVED_VLAN_LIST>" if rule != "VLAN-NATIVE-1" else "port trunk pvid vlan <APPROVED_PVID>"
            finding.command_templates = [_scoped_script(vendor, "interface " + name, command) for name in interfaces]
            note = ("先核对链路两端、聚合/堆叠、现有允许列表和实际业务。IOS/RGOS allowed vlan 会替换列表；"
                    "Huawei allow-pass vlan / H3C permit vlan 通常为增量，缩小范围需另外核对并撤销不再需要的现有 VLAN，不能将此候选命令当成已完成限制。"
                    "不得猜测新 PVID 或直接删除 VLAN 1；PVID 未允许可能是预期隔离，候选模板仅用于确认需调整后。")
        elif rule == "STP-DISABLED":
            interface_scope = finding.problem.startswith("接口 ")
            vlan_scope = finding.problem.startswith("下列 VLAN")
            global_scope = finding.problem.startswith("全局配置")
            if vendor == "ruijie":
                # Global no spanning-tree reverses with spanning-tree. Selecting
                # MSTP/RSTP or root priority requires topology and is never guessed.
                if global_scope and any(e.text.lower() == "no spanning-tree" for e in finding.evidence):
                    finding.command_templates = [_script(vendor, "spanning-tree")]
            elif vendor not in IOS_STYLE:
                if interface_scope:
                    finding.command_templates = [_scoped_script(vendor, "interface " + name, "stp enable") for name in interfaces]
                elif global_scope:
                    finding.command_templates = [_script(vendor, "stp enable")]
            else:
                vids = sorted(vid for vid, enabled in config.stp["vlan_enabled"].items()
                              if enabled is False and isinstance(vid, int) and 1 <= vid <= 4094)
                if vlan_scope and vids:
                    finding.command_templates = [_script(vendor, "spanning-tree vlan " + ",".join(map(str, vids)))]
            note = ("恢复 STP 会改变根桥选择、端口阻塞和收敛，需先核对冗余拓扑、现有模式、根桥/MST 域及 VLAN 映射，并在维护窗口执行。"
                    "候选脚本只恢复所示开关，不选择未知的 STP 模式/根桥优先级，也不证明网络不会中断。")
        elif rule in {"STP-BPDU-FILTER", "STP-BPDU-FILTER-DEFAULT"}:
            if vendor in IOS_STYLE:
                if rule.endswith("DEFAULT"):
                    finding.commands = [_script(vendor, "no spanning-tree portfast bpdufilter default")]
                else:
                    command = "spanning-tree bpdufilter disabled" if vendor == "ruijie" else "no spanning-tree bpdufilter enable"
                    finding.commands = [_scoped_script(vendor, "interface " + name, command) for name in interfaces]
            note = "先确认端口用途、BPDU 过滤与防护的具体语义及邻居状态；取消过滤可能触发 STP 收敛，按维护窗口验证。"
        elif rule == "STP-EDGE-TRUNK":
            command = "no spanning-tree portfast" if vendor in IOS_STYLE else "undo stp edged-port"
            finding.command_templates = [_scoped_script(vendor, "interface " + name, command) for name in interfaces]
            note = "先确认对端是交换设备还是需要边缘 Trunk 的服务器/虚拟化设备；仅在确认不应作为边缘时执行候选脚本。"
        elif rule.startswith("ACL-") or rule == "NAT-ACL-UNDEFINED":
            note = ("先核对 ACL 的接口/VTY/NAT/QoS 等用途、顺序、默认动作及真实许可流量；不推测业务网段，"
                    "也不因未建模引用而自动删除 ACL。缺失 ACL 必须先按真实策略补全并测试；不能用 permit any 作为通用修复。")
            if rule in {"ACL-UNDEFINED", "ACL-VTY-UNDEFINED", "NAT-ACL-UNDEFINED"}:
                # Match one referenced name from typed IR, never arbitrary text.
                lines = {e.line for e in finding.evidence}
                references = []
                for interface in config.interfaces.values():
                    if any(e.line in lines for e in interface.evidence):
                        references += list(interface.acl_bindings.values())
                for line in config.management_lines:
                    if any(e.line in lines for e in line.evidence):
                        references += list(line.acl_bindings.values())
                references += [n.acl for n in config.nat if n.evidence.line in lines and n.acl]
                for name in dict.fromkeys(references):
                    if not _name(name) or name in config.acls:
                        continue
                    if vendor in IOS_STYLE:
                        finding.command_templates.append(_script(vendor,
                            f"ip access-list <ACL_KIND_STANDARD_OR_EXTENDED> {name}",
                            "<APPROVED_PERMIT_AND_DENY_RULES>", "exit"))
                    elif name.isdigit():
                        finding.command_templates.append(_script(vendor, f"acl number {name}",
                            "<APPROVED_PERMIT_AND_DENY_RULES>", "quit"))
        elif rule == "ROUTE-SELF-NEXTHOP":
            note = "先核对真实邻居、出口接口、VRF 和递归解析。模板需保留原路由的 VRF/出口/距离等选项，填入可达的真实邻居，先验证回退与业务流量；不猜测下一跳。"
            if vendor in IOS_STYLE:
                finding.command_templates = [_script(vendor,
                    "no ip route <ORIGINAL_ROUTE_ARGUMENTS>",
                    "ip route <DESTINATION_NETWORK> <NETMASK> <VERIFIED_NEXT_HOP_AND_OPTIONS>")]
            else:
                finding.command_templates = [_script(vendor,
                    "undo ip route-static <ORIGINAL_ROUTE_ARGUMENTS>",
                    "ip route-static <DESTINATION_NETWORK> <NETMASK> <VERIFIED_NEXT_HOP_AND_OPTIONS>")]
        elif rule == "IF-DUPLICATE-IP":
            note = "先核对 anycast/冗余设计、接口用途及同一 VRF 的地址规划；不能从单设备重复地址推测应删除哪一处或分配哪个新地址。"
        elif rule.startswith("OSPF-"):
            note = "先核对实际邻居、进程/区域、被动接口和两端认证，以及 OSPF 域内 Router ID 规划。修改 Router ID/认证/Network 可能重建邻接，需维护窗口；不猜测新 ID、密钥或链路地址。"
        elif rule.startswith("NAT-"):
            note = "先核对路由、真实内部/外部地址、选流 ACL、地址池和现有转换；映射存在不等于公网可达。没有业务规划不能直接删除映射或猜测 NAT 池地址。"
        elif rule.startswith("PARSE-"):
            note = "提供完整、脱敏的原始导出并逐项核对未支持语法；配置覆盖不足不能用配置变更命令修复。"
        if note:
            finding.command_notes += " " + note
        finding.verification_commands = list(dict.fromkeys(finding.verification_commands))
