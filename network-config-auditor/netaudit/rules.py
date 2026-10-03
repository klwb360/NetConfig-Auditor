# SPDX-License-Identifier: GPL-3.0-only
# GenericPlugin is adapted from syn-4ck/pynipper-ng, Syn-4ck,
# src/analyze/cisco/ios/core/base_plugin.py @ 58957659205bcf656f1f209b26be51d1d508b9f9.
# Modified 2026-10-02: typed IR, explicit registry, reset state per audit,
# provenance, scoped checks, conservative unknown-state handling.
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
import ipaddress
import re

from .model import ACLRule, Config, Evidence, Finding

SEVERITIES = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


class GenericPlugin(ABC):
    def __init__(self):
        self.issues: list[Finding] = []

    def get_issues(self) -> list[Finding]:
        return self.issues

    def add_issue(self, issue: Finding) -> None:
        self.issues.append(issue)

    @abstractmethod
    def analyze(self, config: Config) -> None:
        pass

    def add(self, rule_id, severity, category, title, problem, risk, advice,
            evidence, confidence="confirmed-config", commands=None):
        self.add_issue(Finding(rule_id, severity, category, title, problem,
                               risk, advice, evidence, confidence, commands or []))


class ManagementChecks(GenericPlugin):
    def analyze(self, c: Config) -> None:
        globals_ = c.global_commands
        http_state: tuple[bool, Evidence] | None = None
        telnet_state: tuple[bool, Evidence] | None = None
        credentials = [e for v in c.management_lines for e in v.evidence
                       if e.text.startswith(("password ", "set authentication password "))]
        for e in globals_ + credentials:
            s = e.text.lower()
            if s in ("ip http server", "http server enable", "http server", "http enable"):
                http_state = (True, e)
            elif s in ("no ip http server", "undo http server enable", "undo http server", "undo http enable"):
                http_state = (False, e)
            if s in ("telnet server enable", "telnet server"):
                telnet_state = (True, e)
            elif s in ("undo telnet server enable", "undo telnet server"):
                telnet_state = (False, e)
            if re.search(r"\b(?:password|secret) (?:0 |7 |plain |simple )?\[redacted\]", s):
                if "cipher [redacted]" in s or "secret 5 " in s or "secret 8 " in s or "secret 9 " in s:
                    continue
                self.add("MGMT-CREDENTIAL", "high", "management", "明文或弱保护凭据",
                         "配置含明文/simple/type 0/type 7 或未标注保护类型的凭据。",
                         "配置泄露可能导致凭据恢复；Cisco type 7 仅为可逆混淆。",
                         "更换凭据，按平台支持改用强哈希 secret 或不可逆密码；service password-encryption 不能替代强哈希。", [e])
            if s.startswith(("snmp-server community ", "snmp-agent community ")):
                write = bool(re.search(r"\b(?:rw|write)\b", s))
                self.add("MGMT-SNMP-COMMUNITY", "high" if write else "medium", "management",
                         "SNMP community 配置", "存在基于 community 的 SNMP 配置" + ("，含写权限。" if write else "。"),
                         "SNMPv1/v2c 不提供传输加密；写权限还可能允许更改设备。",
                         "迁移到 SNMPv3 authPriv，限制管理网段与只读权限；确认监控兼容后删除旧 community。", [e])
            if s.startswith("ip ssh authentication-retries "):
                try:
                    retries = int(s.split()[-1])
                    if retries > 5:
                        self.add("MGMT-SSH-RETRIES", "medium", "management", "SSH 重试次数过多",
                                 f"SSH 单会话允许 {retries} 次认证重试。", "增加在线密码猜测机会。",
                                 "根据运维基线将重试次数设为 3–5，配合 AAA 与登录限速。", [e], commands=["ip ssh authentication-retries 3"])
                except ValueError:
                    self.add("PARSE-NUMBER", "info", "coverage", "SSH 重试参数无法识别",
                             "该命令末尾不是整数。", "无法评估重试策略。", "检查完整原始配置。", [e], "needs-review")
            if s == "ip ssh version 1":
                self.add("MGMT-SSHV1", "high", "management", "SSH 版本 1",
                         "显式指定 SSHv1。", "SSH 版本 1 存在协议层安全缺陷。",
                         "验证客户端兼容后使用 SSHv2。", [e], commands=["ip ssh version 2"])
        if http_state and http_state[0]:
            command = {"cisco": "no ip http server", "huawei": "undo http server enable", "h3c": "undo http server enable"}[c.vendor]
            self.add("MGMT-HTTP", "high", "management", "HTTP 管理服务开启",
                     "配置显式开启明文 HTTP 管理。", "可达网络上的通信可能泄露登录信息。",
                     "确认管理路径后关闭 HTTP，使用 HTTPS/SSH 并限制管理来源；命令需核对设备版本。",
                     [http_state[1]], commands=[command])
        if telnet_state and telnet_state[0]:
            self.add("MGMT-TELNET-SERVER", "high", "management", "Telnet 服务开启",
                     "配置显式开启 Telnet 服务器。", "可达网络上的登录凭据与命令可能被窃听。",
                     "确认 SSH 可用后关闭 Telnet 服务，并逐段检查 VTY 入站协议。", [telnet_state[1]])
        for v in c.management_lines:
            # A secure VTY range must never hide another insecure range.
            if v.transport and any(x in ("telnet", "all") for x in v.transport):
                self.add("MGMT-VTY-TELNET", "high", "management", "VTY 允许 Telnet",
                         f"{v.name} 的入站协议包含 Telnet/all。", "此 VTY 段允许明文远程管理协议。",
                         "先验证 SSH、AAA 与备用管理路径，再将该 VTY 段限制为 SSH。", v.evidence,
                         commands=[v.name, "transport input ssh" if c.vendor == "cisco" else "protocol inbound ssh"])
            elif v.transport is None:
                self.add("MGMT-VTY-UNKNOWN", "info", "management", "VTY 协议未显式给出",
                         f"{v.name} 没有已识别的入站协议。", "设备默认值因平台/版本而异，不能静态确认。",
                         "核对设备版本、完整配置和实际服务状态，明确 SSH 管理基线。", [v.evidence[0]], "needs-review")
            if v.authentication in ("no login", "authentication-mode none"):
                self.add("MGMT-VTY-NOAUTH", "critical", "management", "VTY 未要求认证",
                         f"{v.name} 显式配置不认证。", "在可达且有可用入站协议时，未认证人员可能获得会话。",
                         "检查 AAA/本地账号与控制台回退，恢复身份认证。", v.evidence)
            if v.idle_seconds == 0 or (v.idle_seconds is not None and v.idle_seconds > 900):
                self.add("MGMT-VTY-TIMEOUT", "medium", "management", "VTY 会话超时过宽",
                         f"{v.name} 的空闲超时为 {v.idle_seconds} 秒（0 表示不自动超时）。",
                         "遗留管理会话可能被其他人员接管。", "按运维基线设为 5–15 分钟并确认长任务需求。", v.evidence,
                         commands=[v.name, "exec-timeout 10 0" if c.vendor == "cisco" else "idle-timeout 10 0"])
            if not v.acl_bindings and v.transport != ["none"]:
                self.add("MGMT-VTY-SOURCE", "low", "management", "VTY 未见来源 ACL",
                         f"{v.name} 未配置已识别的来源 ACL。", "缺少设备侧来源限制；外部防火墙或管理 VRF 可能已提供隔离。",
                         "结合管理 VRF/防火墙确认可达性，按管理员网段设置来源 ACL。", [v.evidence[0]], "needs-review")


def _covers(a: str, b: str) -> bool:
    if a == "any":
        return True
    if b == "any":
        return False
    try:
        return ipaddress.IPv4Network(b).subnet_of(ipaddress.IPv4Network(a))
    except ValueError:
        return a == b


def _rule_covers(a: ACLRule, b: ACLRule) -> bool:
    if not a.complete or not b.complete:
        return False
    return (a.protocol in ("ip", b.protocol) and _covers(a.source, b.source)
            and _covers(a.destination, b.destination)
            and (a.source_port is None or a.source_port == b.source_port)
            and (a.destination_port is None or a.destination_port == b.destination_port))


class ACLChecks(GenericPlugin):
    def analyze(self, c: Config) -> None:
        refs: dict[str, list[tuple[str, Evidence]]] = {}
        for it in c.interfaces.values():
            for direction, name in it.acl_bindings.items():
                refs.setdefault(name, []).append(("filter", it.evidence[-1]))
                if name not in c.acls:
                    self.add("ACL-UNDEFINED", "high", "acl", "接口引用未定义 ACL",
                             f"{it.name} {direction} 引用 ACL {name}，输入中未见定义。",
                             "设备行为随平台变化，预期过滤可能没有实现。", "确认输入完整性，再补全正确 ACL 或修正引用。", it.evidence)
        for v in c.management_lines:
            for name in v.acl_bindings.values():
                refs.setdefault(name, []).append(("management", v.evidence[-1]))
                if name not in c.acls:
                    self.add("ACL-VTY-UNDEFINED", "high", "acl", "VTY 引用未定义 ACL",
                             f"{v.name} 引用 ACL {name}，输入中未见定义。", "管理来源限制可能没有实现。",
                             "检查配置完整性与 ACL 引用。", v.evidence)
        for n in c.nat:
            if n.acl:
                refs.setdefault(n.acl, []).append(("nat-selection", n.evidence))
        for name, acl in c.acls.items():
            use = {x[0] for x in refs.get(name, [])}
            if not use:
                self.add("ACL-UNBOUND", "info", "acl", "ACL 未见受支持的引用",
                         f"ACL {name} 未见接口、VTY 或 NAT 引用。", "可能是备用 ACL 或由未建模的 QoS、route-map 等功能引用。",
                         "核对所有用途再清理；不能仅因未识别引用就删除。", [Evidence(acl.line, "acl " + name)], "needs-review")
            prior: list[ACLRule] = []
            for r in acl.rules:
                shadow = next((p for p in prior if _rule_covers(p, r)), None) if acl.ordered else None
                if shadow:
                    self.add("ACL-SHADOW", "medium", "acl", "ACL 规则被前序规则覆盖",
                             f"ACL {name} 的规则 {r.sequence} 被规则 {shadow.sequence} 的匹配范围完全覆盖。",
                             "按已解析的顺序匹配语义，后序规则无法命中；硬件/应用模式仍需核对。",
                             "确认 match-order 与业务目的后调整顺序或范围；修改前验证代表性流量。", [shadow.evidence, r.evidence], "needs-review")
                elif r.complete and r.action == "permit" and r.protocol == "ip" and r.source in ("any", "0.0.0.0/0") and r.destination in ("any", "0.0.0.0/0") and not r.source_port and not r.destination_port:
                    applied = bool(use & {"filter", "management"})
                    nat_only = use == {"nat-selection"}
                    self.add("ACL-PERMIT-ANY", "high" if applied else "low", "acl", "ACL 存在宽泛 permit",
                             f"ACL {name} 规则 {r.sequence} 允许全部地址范围的 IP 流量" + ("，用途仅为 NAT 选流。" if nat_only else "。"),
                             "会匹配未被前序规则排除的流量。" + ("NAT 选流并不等于防火墙放通。" if nat_only else "实际影响取决于绑定方向和应用语义。"),
                             "按已确认业务缩小范围；区分过滤、管理访问与 NAT 选流，结合设备默认动作验证。", [r.evidence], "confirmed-config" if applied else "needs-review")
                prior.append(r)


class NetworkChecks(GenericPlugin):
    def analyze(self, c: Config) -> None:
        address_owners: dict[tuple[str, str], list] = {}
        for it in c.interfaces.values():
            for addr in it.addresses:
                address_owners.setdefault((it.vrf, str(ipaddress.IPv4Interface(addr).ip)), []).append(it)
            for vid in (it.access_vlan, it.native_vlan):
                if vid and vid != 1 and vid not in c.vlans:
                    self.add("VLAN-UNDEFINED", "medium", "vlan", "接口引用未见定义的 VLAN",
                             f"{it.name} 引用 VLAN {vid}，输入中未见 vlan 定义。", "可能导致业务 VLAN 未创建或无法转发。",
                             "确认输入完整、动态 VLAN 与平台隐式创建行为，再补全 VLAN。", it.evidence, "needs-review")
            if it.mode == "trunk" and it.allowed_vlans is not None and len(it.allowed_vlans) == 4094:
                self.add("VLAN-TRUNK-ALL", "low", "vlan", "Trunk 允许所有 VLAN",
                         f"{it.name} 显式允许 VLAN 1–4094。", "可能扩大二层广播域暴露；网络用途可能要求全量透传。",
                         "依据两端业务清单设置最小 VLAN 列表，变更前核对聚合/堆叠链路。", it.evidence, "needs-review")
            if it.mode == "trunk" and it.native_vlan == 1:
                self.add("VLAN-NATIVE-1", "low", "vlan", "Trunk 使用 VLAN 1 作为 native/PVID",
                         f"{it.name} 显式将 VLAN 1 设为 native/PVID。", "业务与默认 VLAN 混用可能增加误接入风险；是否允许未标记报文依平台而定。",
                         "核对两端 PVID、标签行为和业务要求，采用专用且受控的 VLAN。", it.evidence, "needs-review")
            if it.mode == "trunk" and it.native_vlan and it.allowed_vlans is not None and it.native_vlan not in it.allowed_vlans:
                self.add("VLAN-PVID-NOT-ALLOWED", "info", "vlan", "PVID 未包含在允许列表",
                         f"{it.name} 的 PVID/native VLAN {it.native_vlan} 不在显式允许 VLAN 中。", "不同平台对未标记报文行为不同，可能造成连接异常，也可能是预期隔离。",
                         "核对平台行为和链路两端配置。", it.evidence, "needs-review")
        for (vrf, address), owners in address_owners.items():
            if len(owners) > 1:
                self.add("IF-DUPLICATE-IP", "high", "interface", "同一 VRF 内重复接口地址",
                         f"VRF {vrf} 的 {address} 同时配置在 " + ", ".join(x.name for x in owners),
                         "可能产生地址冲突或不可预期的选路；anycast/借用地址设计需单独核对。",
                         "确认冗余/anycast 设计后修正误配地址。", [x.evidence[0] for x in owners], "needs-review")
        for r in c.routes:
            if r.next_hop and (r.vrf, r.next_hop) in address_owners:
                self.add("ROUTE-SELF-NEXTHOP", "high", "routing", "静态路由下一跳指向本机",
                         f"{r.destination} 的下一跳 {r.next_hop} 等于同一 VRF 的本机接口地址。",
                         "路由可能无法生效或造成转发异常。", "根据拓扑核对正确邻居地址、递归解析与出口接口。", [r.evidence])
        # Multiple routes for one prefix can be valid ECMP/floating routes. No blanket alarm.
        for n in c.nat:
            if n.acl and n.acl not in c.acls:
                self.add("NAT-ACL-UNDEFINED", "high", "nat", "NAT 引用未定义 ACL",
                         f"NAT 引用 ACL {n.acl}，输入中未见定义。", "NAT 选流可能不符合预期或无法生效。",
                         "确认输入完整并补全/修正 NAT 选流 ACL。", [n.evidence])
            if n.pool and n.pool not in c.nat_pools:
                self.add("NAT-POOL-UNDEFINED", "medium", "nat", "NAT 引用未定义地址池",
                         f"NAT 引用地址池 {n.pool}，输入中未见定义。", "地址转换可能失败。", "核对地址池名称和地址范围。", [n.evidence])
            if n.complete and n.kind in ("static", "server"):
                self.add("NAT-INBOUND-MAPPING", "medium", "nat", "存在静态 NAT / 内部服务器映射",
                         "配置建立了静态映射：" + str(n.outside) + (":" + n.outside_port if n.outside_port else "") + " → " + str(n.inside),
                         "可能使内部服务可从外侧访问；仅凭配置不能确认公网可达、ACL 与路由结果。",
                         "核对外侧访问控制、映射端口和服务加固；确认业务后限制来源并删除不用的映射。", [n.evidence], "needs-review")
        if c.unsupported_count:
            self.add("PARSE-INCOMPLETE", "info", "coverage", "存在未建模配置",
                     f"{c.unsupported_count} 行存在未支持语法或格式问题；报告列出前 200 行。",
                     "可能漏检相关配置；缺少告警不能视为安全或合规证明。",
                     "查看 warnings，补齐解析支持或人工审查这些行，优先核对 ACL/NAT/管理面。", [], "needs-review")


PLUGINS = (ManagementChecks, ACLChecks, NetworkChecks)


def audit(config: Config) -> dict:
    findings = []
    for plugin_type in PLUGINS:
        plugin = plugin_type()
        plugin.analyze(config)
        findings.extend(plugin.get_issues())
    findings.sort(key=lambda f: (-SEVERITIES[f.severity], f.rule_id, f.evidence[0].line if f.evidence else 0))
    counts = Counter(f.severity for f in findings)
    return {
        "schema_version": "1.0", "tool_version": "0.1.0",
        "device": {"vendor": config.vendor, "hostname": config.hostname, "detection": config.detection},
        "summary": {"total": len(findings), "severity": {s: counts[s] for s in SEVERITIES},
                    "recognized_lines": config.recognized_lines, "relevant_lines": config.relevant_lines,
                    "unsupported_lines": config.unsupported_count},
        "limitations": "离线配置审计；仅支持所列 IPv4 语法。动态路由仅提取进程。未确认实时状态、拓扑、公网可达性、CVE 或完整基准合规。修改命令是需核对平台版本与管理回退的建议。",
        "findings": [f.to_dict() for f in findings], "inventory": config.to_dict(),
    }
