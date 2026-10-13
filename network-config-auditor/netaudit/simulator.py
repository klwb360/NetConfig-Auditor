"""Conservative offline configuration-state simulator, never a device emulator.

The parser is used for validation and inventory, never for serializing backups.
Edits retain untouched source lines verbatim. A rejected command rolls back the
whole batch including CLI context; only an explicit caller action commits it.
"""
from __future__ import annotations

from dataclasses import dataclass
import difflib
import ipaddress
import json
import re

from .model import Evidence
from .branding import APPLICATION_NAME
from .parser import (IOS_VENDORS, MAX_BYTES, MAX_LINES, VENDORS, _acl_rule,
                     parse_config, vlan_ids)
from .privacy import redact

MAX_COMMAND_BYTES = 64 * 1024
MAX_COMMAND_LINES = 200
MAX_OUTPUT_BYTES = 256 * 1024
_MODES = {"exec", "config", "interface", "vlan", "vty", "acl"}
_FAILURE = {"blocked", "unsupported", "invalid"}
_LIMITATIONS = [
    "这是离线配置状态练习，不连接设备，也不执行操作系统或网络命令。",
    "可运行仅表示本工具支持该语法且配置前置条件满足，不保证实机型号、固件或许可证支持。",
    "不模拟数据包转发、链路通断、STP 收敛、OSPF 邻居、性能、重启或真实业务影响。",
    "未识别的原配置按原文保留；未知命令和无法确定的作用域拒绝修改。",
    "候选配置和导出备份保留原有凭据；请按敏感文件保存。显示与差异会脱敏。",
]


def _safe(text: str) -> str:
    """Redact linewise, including VRP/Comware authentication without 'password'."""
    return "\n".join(re.sub(r"(?i)(\bauthentication-mode\s+\S+)\s+.+$",
                            r"\1 [REDACTED]", redact(line)) for line in text.splitlines())


def _unsafe_control(value: str) -> bool:
    # Python splitlines() also treats C1 NEL and Unicode separators as line
    # breaks. Reject them before parsing so a pasted description cannot turn
    # into an extra device command that was not visibly on its own CLI line.
    return any((ord(c) < 32 and c not in "\n\r\t") or 127 <= ord(c) <= 159
               or c in ("\u2028", "\u2029") for c in value)


def _netmask(value: str, ios: bool) -> str:
    """Device CLI netmasks are not the hostmasks accepted by ipaddress."""
    if value.isdigit():
        if ios or not 0 <= int(value) <= 32:
            raise ValueError("unsupported prefix length")
        return value
    mask = ipaddress.IPv4Address(value)
    network = ipaddress.IPv4Network("0.0.0.0/" + value)
    if mask != network.netmask:
        raise ValueError("wildcard is not a netmask")
    return value


def _vlan_text(ids: set[int], ios: bool) -> str:
    ranges: list[list[int]] = []
    for vid in sorted(ids):
        if ranges and vid == ranges[-1][1] + 1:
            ranges[-1][1] = vid
        else:
            ranges.append([vid, vid])
    return ("," if ios else " ").join(str(a) if a == b else str(a) + ("-" if ios else " to ") + str(b) for a, b in ranges)


class _Rejected(Exception):
    def __init__(self, status: str, reason: str, suggestion: str = ""):
        self.status, self.reason, self.suggestion = status, reason, suggestion


def _reject(reason: str, suggestion: str = "", status: str = "blocked") -> None:
    raise _Rejected(status, reason, suggestion)


@dataclass
class _Block:
    start: int
    end: int
    header: str
    kind: str
    target: str = ""
    ids: frozenset[int] = frozenset()


class _Document:
    """A minimal lossless physical-line editor with conservative block boundaries."""
    def __init__(self, text: str, vendor: str):
        self.lines = text.splitlines(keepends=True)
        self.vendor = vendor
        self.newline = "\r\n" if "\r\n" in text else "\n"
        self.sep = "!" if vendor in IOS_VENDORS else "#"

    @property
    def text(self) -> str:
        return "".join(self.lines)

    def blocks(self) -> list[_Block]:
        found: list[_Block] = []
        current = None
        banner = None
        for i, raw in enumerate(self.lines):
            s = raw.strip()
            if banner is not None:
                if banner in s:
                    banner = None
                continue
            if s.startswith("banner "):
                if current is not None:
                    current.end = i
                parts = s.split(None, 2)
                if len(parts) == 3 and parts[2]:
                    value = parts[2]
                    delim = value[:2] if value.startswith("^") else value[:1]
                    if delim not in value[len(delim):]:
                        banner = delim
                current = None
                continue
            if s in ("!", "#", "end", "return", "exit", "quit"):
                if current is not None:
                    current.end = i
                current = None
                continue
            if not s or s.startswith(("!", "#")):
                continue
            if raw[:1].isspace():
                continue
            if current is not None:
                current.end = i
            kind, target, ids = "global", "", frozenset()
            if s.startswith("interface "):
                kind, target = "interface", s[10:].replace(" ", "")
            elif re.fullmatch(r"vlan (?:batch |range )?[\d,\s-]+(?:to[\d,\s-]+)*", s):
                try:
                    ids = frozenset(vlan_ids(re.sub(r"^vlan (?:batch |range )?", "", s)))
                    kind = "vlan"
                except ValueError:
                    pass
            elif re.fullmatch(r"(?:line|user-interface) vty \d+(?: \d+)?", s):
                kind, target = "vty", s
            elif re.fullmatch(r"ip access-list (?:standard|extended) [\w.-]+", s):
                kind, target = "acl", s.split()[-1]
            elif re.fullmatch(r"acl (?:number |basic |advanced )?\d+", s):
                kind, target = "acl", s.split()[-1]
            current = _Block(i, len(self.lines), s, kind, target, ids)
            found.append(current)
        if banner is not None:
            _reject("备份中有未闭合的 banner，无法确定后续配置边界。", "补全 banner 分隔符后再练习。")
        return found

    def find(self, mode: str, target: str) -> _Block:
        if mode == "vlan":
            matches = [b for b in self.blocks() if b.kind == mode and int(target) in b.ids]
        else:
            matches = [b for b in self.blocks() if b.kind == mode and b.target == target]
        if len(matches) != 1:
            _reject("该对象没有唯一、可安全编辑的配置块。", "请先整理重复块，或使用有明确缩进和分隔符的完整备份。")
        b = matches[0]
        if (self.vendor not in IOS_VENDORS and b.end < len(self.lines)
                and self.lines[b.end].strip() not in ("#", "!", "end", "return", "exit", "quit")
                and any(other.start == b.end and other.kind == "global" for other in self.blocks())):
            _reject("此配置块后有未分隔的顶层命令，无法确定其作用域。", "为配置块补全 # 分隔符或正确缩进后再练习。")
        if mode == "vlan" and len(b.ids) != 1:
            _reject("该 VLAN 与其他 VLAN 共用配置块，单独修改名称会影响范围判断。",
                    "先在备份中拆成独立 VLAN 块，再模拟修改名称。")
        return b

    def _insert(self, index: int, texts: list[str]) -> None:
        if index and not self.lines[index - 1].endswith(("\n", "\r")):
            self.lines[index - 1] += self.newline
        self.lines[index:index] = [s + self.newline for s in texts]

    def append(self, header: str) -> None:
        # Explicit separator avoids inheriting an unknown stanza at EOF.
        terminal = next((i for i in range(len(self.lines) - 1, -1, -1)
                         if self.lines[i].strip()), None)
        index = terminal if terminal is not None and self.lines[terminal].strip() in ("end", "return") else len(self.lines)
        self._insert(index, [self.sep, header, self.sep])

    def edit(self, block: _Block | None, match, replacement: str | list[str] | None) -> bool:
        replacements = [replacement] if isinstance(replacement, str) else replacement
        if block is None:
            selected = [b for b in self.blocks() if b.kind == "global" and match(b.header)]
            if selected and self.vendor not in IOS_VENDORS:
                parsed = parse_config(self.text, self.vendor)
                flat_lines = {e.line - 1 for e in parsed.global_commands}
                flat_lines.update(route.evidence.line - 1 for route in parsed.routes)
                blocks = self.blocks()
                for selected_block in selected:
                    boundary = next((i for i in range(selected_block.start - 1, -1, -1)
                                     if self.lines[i].strip() in ("!", "#", "end", "return", "exit", "quit")), -1)
                    for prior in blocks:
                        if not boundary < prior.start < selected_block.start:
                            continue
                        has_children = any(line.strip() and not line.lstrip().startswith(("!", "#"))
                                           for line in self.lines[prior.start + 1:prior.end])
                        if (prior.kind != "global" or has_children or prior.header == "aaa"
                                or prior.header.startswith("local-user ") or (prior.start not in flat_lines
                                and not prior.header.startswith(("sysname ", "hostname ", "version ")))):
                            _reject("待修改的全局命令前有未分隔的局部或未知配置块，作用域无法确认。",
                                    "先补全 # 分隔符或正确缩进，再修改全局配置。")
            for b in selected:
                if any(s.strip() and not s.lstrip().startswith(("!", "#")) for s in self.lines[b.start + 1:b.end]):
                    _reject("目标全局命令含未知子配置，无法安全替换。", "先核对并拆分该配置块。")
            indices = [b.start for b in selected]
            indent = ""
        else:
            indices = [i for i in range(block.start + 1, block.end) if match(self.lines[i].strip())]
            indent = next((re.match(r"\s*", self.lines[i]).group(0) for i in range(block.start + 1, block.end)
                           if self.lines[i].strip() and self.lines[i][:1].isspace()), " ")
            # A deeper child means this would change a nested, unmodelled scope.
            nonempty = [s for s in self.lines[block.start + 1:block.end]
                        if s.strip() and not s.lstrip().startswith(("!", "#"))]
            if any(len(re.match(r"[ \t]*", s).group()) != len(indent) for s in nonempty):
                _reject("该块含嵌套或不一致缩进，无法确定命令作用域。", "请先展开或整理该块后再模拟。")
        if replacements is not None and [self.lines[i].strip() for i in indices] == replacements:
            return False
        if replacement is None and not indices:
            return False
        if indices:
            first = indices[0]
            for i in reversed(indices):
                del self.lines[i]
            if replacements is not None:
                self._insert(first, [indent + value for value in replacements])
        elif block is None:
            for value in replacements or []:
                self.append(value)
        else:
            self._insert(block.end, [indent + value for value in replacements or []])
        return True


def _prompt(context: dict, vendor: str) -> str:
    mode, target = context["mode"], context["target"]
    if vendor in IOS_VENDORS:
        suffix = {"exec": "#", "config": "(config)#", "interface": "(config-if)#",
                  "vlan": "(config-vlan)#", "vty": "(config-line)#", "acl": "(config-acl)#"}[mode]
        return APPLICATION_NAME + suffix
    return "<" + APPLICATION_NAME + ">" if mode == "exec" else "[" + APPLICATION_NAME + ("-" + target if target else "") + "]"


def _capabilities(vendor: str, context: dict) -> list[dict]:
    ios = vendor in IOS_VENDORS
    mode = context["mode"]
    entries = [("show running-config" if ios else "display current-configuration", "查看脱敏的候选配置，不查询真实设备。")]
    if mode == "exec":
        entries.append(("configure terminal" if ios else "system-view", "进入配置模式，随后选择接口或 VLAN。"))
    elif mode == "config":
        entries += [("vlan 10", "创建 VLAN；随后进入 VLAN 视图。"),
                    ("interface <备份中已有接口名>", "选择已导入接口；本工具不凭空创建物理端口。"),
                    ("ip route <网段> <掩码> <下一跳>" if ios else "ip route-static <网段> <掩码> <下一跳>", "增加静态路由配置；不验证下一跳在线。")]
    elif mode == "interface":
        entries += [("description <用途>", "记录接口用途。"), ("shutdown", "设置管理关闭；不推断物理链路状态。"),
                    ("no shutdown" if ios else "undo shutdown", "取消管理关闭。"),
                    ("switchport mode access" if ios else "port link-type access", "把已导入端口设为 access 模式。"),
                    ("switchport access vlan <已建VLAN>" if ios else ("port default vlan <已建VLAN>" if vendor == "huawei" else "port access vlan <已建VLAN>"), "VLAN 必须先创建；端口需处于 access 模式。"),
                    ("ip address <IPv4> <掩码>", "设置主地址；检查格式和同一 VRF 地址重复。")]
    elif mode == "vlan":
        entries.append(("name <名称>" if ios else "description <名称>", "给当前独立 VLAN 配置块设置说明。"))
    elif mode == "vty":
        entries.append(("transport input ssh" if ios else "protocol inbound ssh", "只保留 SSH 接入配置；不会替你创建用户或密钥。"))
    elif mode == "acl":
        entries.append(("10 permit ip any any" if ios else "rule 10 permit ip", "练习完整基础规则；是否过宽可在练习后另做审计。"))
    if mode != "exec":
        entries.append(("end" if ios else "return", "返回执行视图。"))
    return [{"command": c, "reason": r} for c, r in entries]


def _context(value: dict | None, cfg, doc: _Document) -> dict:
    if value is None:
        return {"mode": "exec", "target": ""}
    if (not isinstance(value, dict) or set(value) != {"mode", "target"}
            or not isinstance(value.get("mode"), str) or value.get("mode") not in _MODES
            or not isinstance(value.get("target"), str)):
        raise ValueError("模拟上下文必须包含合法的 mode 和字符串 target")
    mode, target = value["mode"], value["target"]
    if mode in ("exec", "config"):
        valid = target == ""
    elif mode == "interface":
        valid = target in cfg.interfaces
    elif mode == "vlan":
        valid = bool(re.fullmatch(r"[1-9]\d{0,3}", target)) and int(target) in cfg.vlans
    elif mode == "acl":
        valid = target in cfg.acls
    else:
        valid = target in [v.name for v in cfg.management_lines]
    if not valid:
        raise ValueError("模拟上下文与当前配置不匹配，请返回执行视图后重新选择对象")
    return dict(value)


class _Session:
    def __init__(self, doc: _Document, context: dict):
        self.doc, self.context = doc, dict(context)
        self.vendor = doc.vendor
        self.ios = self.vendor in IOS_VENDORS
        self.inverse = "no " if self.ios else "undo "
        self._cached_text = None
        self._cached_config = None

    def cfg(self):
        text = self.doc.text
        if text != self._cached_text:
            self._cached_config = parse_config(text, self.vendor)
            self._cached_text = text
        return self._cached_config

    def need(self, mode: str) -> None:
        if self.context["mode"] != mode:
            _reject("当前不在所需的命令视图。", "先进入" + {"config": "全局配置视图", "interface": "接口视图", "vty": "VTY 视图", "vlan": "VLAN 视图", "acl": "ACL 视图"}.get(mode, mode) + "。")

    def edit(self, match, command: str | list[str] | None, mode: str | None = None) -> tuple[str, str, str, str]:
        mode = mode or self.context["mode"]
        block = None if mode == "config" else self.doc.find(mode, self.context["target"])
        changed = self.doc.edit(block, match, command)
        return ("applied" if changed else "noop", "候选配置已更新。" if changed else "配置已经是该值，无需重复修改。", "确认差异后应用；需要时再运行审计。", "")

    def show(self, command: str):
        prefix = "show " if self.ios else "display "
        if not command.startswith(prefix):
            _reject("这是其他厂商的查看语法。", "使用 " + ("show" if self.ios else "display") + " 查看已建模配置。", "unsupported")
        name = command[len(prefix):]
        cfg = self.cfg()
        if name == ("running-config" if self.ios else "current-configuration"):
            output = _safe(self.doc.text)
        elif name in (("vlan", "vlan brief") if self.ios else ("vlan",)):
            output = "\n".join(f"VLAN {vid}: {item['name'] or '未命名'}" for vid, item in sorted(cfg.vlans.items())) or "输入配置未见 VLAN 定义。"
        elif name in (("ip interface brief", "interfaces") if self.ios else ("ip interface brief", "interface brief")):
            output = "\n".join(f"{i.name}: 管理配置={'shutdown' if i.shutdown is True else 'no shutdown' if i.shutdown is False else '未显式配置'}; IPv4={','.join(i.addresses) or '未配置'}; 链路状态=未模拟" for i in cfg.interfaces.values()) or "输入配置未见接口定义。"
        elif name == ("ip route" if self.ios else "ip routing-table"):
            output = "仅显示备份中的静态路由配置，不代表活动路由表：\n" + "\n".join(
                f"{r.destination} -> {r.next_hop or r.interface} (VRF {r.vrf})"
                + (" [参数未完整建模，需人工复核]" if not r.complete else "")
                for r in cfg.routes)
        elif name == ("access-lists" if self.ios else "acl all"):
            output = json.dumps(cfg.to_dict()["acls"], ensure_ascii=False, indent=2)
        else:
            _reject("此查看命令涉及未建模内容或运行状态。", "可查看配置、VLAN、接口地址、静态路由配置和 ACL。", "unsupported")
        return "show", "只读展示已导入或模拟后的配置状态。", "", _safe(output)

    def run(self, command: str):
        s = command.strip()
        if s in ("!", "#") or s.startswith(("!", "#")):
            return "noop", "注释不改变配置。", "", ""
        if s.startswith(("show ", "display ")):
            return self.show(s)
        if s == "enable":
            if not self.ios:
                _reject("该厂商不使用 enable 进入配置视图。", "使用 system-view。", "unsupported")
            if self.context["mode"] != "exec":
                _reject("enable 仅用于执行视图。", "先使用 end 返回执行视图。")
            return "noop", "练习已处于授权执行视图，无需输入密码。", "", ""
        if s in ("configure terminal", "conf t", "system-view"):
            if (s == "system-view") == self.ios:
                _reject("进入视图的命令与所选厂商不符。", "使用 " + ("configure terminal" if self.ios else "system-view") + "。", "unsupported")
            self.need("exec")
            self.context = {"mode": "config", "target": ""}
            return "mode", "已进入全局配置视图。", "", ""
        if s in ("end", "return", "exit", "quit"):
            if s not in (("end", "exit") if self.ios else ("return", "quit")):
                _reject("退出命令与所选厂商不符。", "使用 " + ("end / exit" if self.ios else "return / quit") + "。", "unsupported")
            target = "exec" if s in ("end", "return") or self.context["mode"] in ("exec", "config") else "config"
            self.context = {"mode": target, "target": ""}
            return "mode", "已返回" + ("执行" if target == "exec" else "全局配置") + "视图。", "", ""
        if s.startswith("interface "):
            self.need("config")
            target = s[10:].replace(" ", "")
            if target not in self.cfg().interfaces:
                _reject("备份中没有这个接口，无法确认设备具有该端口。", "从接口清单中选择完整名称；暂不支持创建新接口。")
            self.doc.find("interface", target)
            self.context = {"mode": "interface", "target": target}
            return "mode", "已进入该接口视图。", "", ""
        if re.match(r"^(?:line|user-interface) vty\b", s):
            self.need("config")
            expected = "line" if self.ios else "user-interface"
            match = re.fullmatch(expected + r" vty (\d+)(?: (\d+))?", s)
            if not match:
                _reject("VTY 语法与厂商不符或范围格式不支持。", "仅选择备份中已有的完整 VTY 范围。", "unsupported")
            if s not in [v.name for v in self.cfg().management_lines]:
                _reject("备份中未见该 VTY 范围。", "使用备份里的 VTY 范围；本工具不推断设备最大线路数。")
            self.doc.find("vty", s)
            self.context = {"mode": "vty", "target": s}
            return "mode", "已进入 VTY 视图。", "", ""
        if re.match(r"^(?:(?:no|undo) )?vlan\b", s):
            return self.vlan(s)
        if s.startswith(("ip access-list ", "acl ")) and self.context["mode"] == "config":
            return self.acl_select(s)
        mode = self.context["mode"]
        if mode == "interface":
            return self.interface(s)
        if mode == "vlan":
            prefix = "name " if self.ios else "description "
            if s.startswith(prefix) and len(s[len(prefix):]) <= 128 and s[len(prefix):].strip():
                return self.edit(lambda x: x.startswith(("name ", "description ")), s)
        elif mode == "vty":
            return self.vty(s)
        elif mode == "acl":
            return self.acl_rule(s)
        elif mode == "config":
            if s.startswith(("ip route ", "ip route-static ", "no ip route ", "undo ip route-static ")):
                return self.route(s)
            return self.global_command(s)
        _reject("本视图暂不支持该命令。", "查看当前可练习命令；配置命令需先进入相应视图。", "unsupported")

    def vlan(self, s: str):
        self.need("config")
        removing = s.startswith(("no ", "undo "))
        if removing and not s.startswith(self.inverse):
            _reject("撤销前缀与所选厂商不符。", "使用 " + self.inverse.strip() + "。", "unsupported")
        command = s[len(self.inverse):] if removing else s
        if re.fullmatch(r"vlan \d+", command):
            ids = vlan_ids(command[5:])
        elif self.vendor == "huawei" and command.startswith("vlan batch "):
            if re.search(r"\b(?:all|none)\b", command):
                _reject("VLAN 创建/删除需要明确的数字或范围。", "例如 vlan batch 10 to 12。", "unsupported")
            ids = vlan_ids(command[11:])
        elif self.vendor == "ruijie" and command.startswith("vlan range "):
            if re.search(r"\b(?:all|none)\b", command):
                _reject("VLAN 创建/删除需要明确的数字或范围。", "例如 vlan range 10-12。", "unsupported")
            ids = vlan_ids(command[11:])
        else:
            _reject("该 VLAN 批量语法未在当前厂商建模。", "使用 vlan <1–4094>，一次创建一个 VLAN。", "unsupported")
        cfg = self.cfg()
        if removing:
            if 1 in ids:
                _reject("VLAN 1 是平台默认 VLAN，本版不模拟删除。", "保留默认 VLAN，在其他 VLAN 上练习。")
            refs = []
            for iface in cfg.interfaces.values():
                used = {iface.access_vlan, iface.native_vlan}
                if iface.allowed_vlans is not None:
                    used.update(iface.allowed_vlans)
                svi = re.fullmatch(r"(?:Vlanif|Vlan-interface|Vlan)(\d+)", iface.name, re.I)
                if svi:
                    used.add(int(svi[1]))
                if used & ids:
                    refs.append(iface.name)
            if refs:
                _reject("这些 VLAN 仍被接口引用，删除会留下不完整的配置。", "先迁移或移除相关接口的 VLAN/PVID/允许列表引用，再删除 VLAN。")
            # Unknown commands mentioning this VLAN may establish dependencies.
            if cfg.unsupported_count > len(cfg.warnings):
                _reject("未知配置超过可展示的范围，无法完整核对 VLAN 删除依赖。", "先整理不支持的配置，再练习删除。")
            for warning in cfg.warnings:
                if re.search(r"\bvlan\b", warning["text"], re.I):
                    _reject("存在未建模的 VLAN 相关语法，无法完整确认删除依赖。", "先核对相关未知配置行及其中的范围，再练习删除。")
            changed = False
            for b in reversed(self.doc.blocks()):
                if b.kind != "vlan" or not b.ids & ids:
                    continue
                for raw in self.doc.lines[b.start + 1:b.end]:
                    if raw.strip() and not raw.lstrip().startswith(("!", "#", "name ", "description ")):
                        _reject("VLAN 块中含未建模的子配置，删除会丢失这些内容。", "先核对 VLAN 块内的未知配置。")
                remaining = b.ids - ids
                if remaining:
                    if len(remaining) == 1:
                        header = "vlan " + str(next(iter(remaining)))
                    elif self.vendor == "huawei":
                        header = "vlan batch " + " ".join(map(str, sorted(remaining)))
                    elif self.vendor == "ruijie":
                        header = "vlan range " + ",".join(map(str, sorted(remaining)))
                    else:
                        _reject("此备份使用未建模的 VLAN 范围块，无法局部删除。", "先拆成单 VLAN 块。")
                    self.doc.lines[b.start] = header + self.doc.newline
                else:
                    del self.doc.lines[b.start:b.end]
                changed = True
            return "applied" if changed else "noop", "已移除 VLAN 配置。" if changed else "该 VLAN 未定义，无需删除。", "", ""
        missing = ids - set(cfg.vlans)
        for vid in sorted(missing):
            self.doc.append("vlan " + str(vid))
        if len(ids) == 1 and not command.startswith(("vlan batch ", "vlan range ")):
            self.context = {"mode": "vlan", "target": str(next(iter(ids)))}
        return "applied" if missing else "mode", "已创建 VLAN。" if missing else "VLAN 已存在，已选择该对象。", "VLAN 成员端口仍需单独配置。", ""

    def interface(self, s: str):
        cfg = self.cfg()
        iface = cfg.interfaces[self.context["target"]]
        if s.startswith("description ") and 0 < len(s[12:]) <= 240:
            return self.edit(lambda x: x.startswith("description ") or x == self.inverse + "description", s)
        if s == self.inverse + "description":
            return self.edit(lambda x: x.startswith("description ") or x == self.inverse + "description", None)
        if s in ("shutdown", self.inverse + "shutdown"):
            result = self.edit(lambda x: x in ("shutdown", "no shutdown", "undo shutdown"), s)
            return result[0], "已更新接口的管理启停配置；未模拟物理链路。", "关闭接口可能中断业务，真实设备需先核对用途。", ""
        mode_match = re.fullmatch(r"switchport mode (access|trunk)", s) if self.ios else re.fullmatch(r"port link-type (access|trunk)", s)
        if mode_match:
            if iface.addresses:
                _reject("接口已配置 IPv4 地址，直接切换二层模式可能冲突。", "先核对三层用途，必要时移除 IP 地址后再切换。")
            return self.edit(lambda x: x.startswith(("switchport mode ", "port link-type ")) or x == "no switchport", s)
        if s == "no switchport" and self.ios:
            if iface.access_vlan is not None or iface.native_vlan is not None or iface.allowed_vlans is not None:
                _reject("接口仍有二层 VLAN 配置，不能直接转换为路由接口。", "先清理 access/native/allowed VLAN 配置。")
            return self.edit(lambda x: x.startswith("switchport mode ") or x == "no switchport", s)
        access = "switchport access vlan " if self.ios else "port default vlan " if self.vendor == "huawei" else "port access vlan "
        native = "switchport trunk native vlan " if self.ios else "port trunk pvid vlan "
        allowed = "switchport trunk allowed vlan " if self.ios else "port trunk allow-pass vlan " if self.vendor == "huawei" else "port trunk permit vlan "
        for prefix, mode in ((access, "access"), (native, "trunk")):
            if s.startswith(prefix):
                value = s[len(prefix):]
                if not re.fullmatch(r"\d+", value):
                    _reject("该命令需要单个 VLAN ID。", "输入 1–4094 之间的整数。", "invalid")
                vid = next(iter(vlan_ids(value)))
                if vid not in cfg.vlans:
                    _reject("目标 VLAN 尚未定义，当前不能引用。", f"先返回全局视图创建 vlan {vid}，再进入接口执行此命令。")
                if iface.mode != mode:
                    _reject("接口没有显式配置为所需的 " + mode + " 模式。", "先设置 " + ("switchport mode " if self.ios else "port link-type ") + mode + "。")
                return self.edit(lambda x, p=prefix: x.startswith(p) or x == self.inverse + p.strip(), s)
            if s == self.inverse + prefix.strip():
                return self.edit(lambda x, p=prefix: x.startswith(p) or x == self.inverse + p.strip(), None)
        if s.startswith(allowed) or (not self.ios and s.startswith("undo " + allowed)):
            if iface.mode != "trunk":
                _reject("允许 VLAN 列表只在明确的 trunk 模式下模拟。", "先设置 trunk 模式。")
            remove = s.startswith("undo ")
            value = s[len("undo " + allowed) if remove else len(allowed):]
            operation = "remove" if remove else "replace" if self.ios else "add"
            if self.ios and value.startswith(("add ", "remove ")):
                operation, value = value.split(None, 1)
            if value in ("all", "none") or value.startswith("except "):
                _reject("all / none / except 的平台默认行为未在模拟器建模。", "明确列出已创建的 VLAN ID。", "unsupported")
            values = vlan_ids(value)
            if operation != "remove" and values - set(cfg.vlans):
                _reject("允许列表中包含未定义 VLAN。", "先创建列表中的 VLAN，再添加到 trunk。")
            existing = set(iface.allowed_vlans) if iface.allowed_vlans is not None else (set(range(1, 4095)) if self.ios else {1})
            target = values if operation == "replace" else existing - values if operation == "remove" else existing | values
            if target == existing:
                return "noop", "允许列表已经包含这些修改，无需重复。", "", ""
            # Replace the whole modeled family so an earlier inverse command
            # cannot silently override a command replayed at its old position.
            canonical = ([allowed + (_vlan_text(target, True) or "none")] if self.ios else
                         ["undo " + allowed + "1 to 4094"] + ([allowed + _vlan_text(target, False)] if target else []))
            return self.edit(lambda x: x.startswith(allowed) or x.startswith("undo " + allowed) or x == self.inverse + allowed.strip(), canonical)
        if s == self.inverse + allowed.strip():
            return self.edit(lambda x: x.startswith(allowed) or x.startswith("undo " + allowed), None)
        if s.startswith("ip address "):
            m = re.fullmatch(r"ip address (\S+) (\S+)(?: (secondary|sub))?", s)
            if not m:
                _reject("仅支持静态 IPv4 地址和掩码。", "使用 ip address <IPv4> <掩码>，暂不模拟 DHCP 或借用地址。", "unsupported")
            if m[3] and m[3] != ("secondary" if self.ios else "sub"):
                _reject("辅助地址关键字与厂商不符。", "使用 " + ("secondary" if self.ios else "sub") + "。", "unsupported")
            address = ipaddress.IPv4Interface(m[1] + "/" + _netmask(m[2], self.ios))
            if address.ip.is_multicast or address.ip.is_unspecified or address.ip.is_loopback or address.ip == ipaddress.IPv4Address("255.255.255.255"):
                _reject("该地址不能作为普通接口单播地址。", "选择合法的接口单播 IPv4 地址。", "invalid")
            if address.network.prefixlen < 31 and address.ip in (address.network.network_address, address.network.broadcast_address):
                _reject("该地址是网段地址或广播地址。", "请选择网段内的主机地址。", "invalid")
            if iface.mode in ("access", "trunk", "hybrid"):
                _reject("该接口已配置为二层交换模式，不能直接设置三层 IPv4。", "在已有三层接口上练习，或先按设备能力转换为路由模式。")
            for other in cfg.interfaces.values():
                if other.name != iface.name and other.vrf == iface.vrf and any(ipaddress.IPv4Interface(x).ip == address.ip for x in other.addresses):
                    _reject("同一 VRF 的另一个接口已使用这个 IPv4 地址。", "选择未使用的地址，或先移除原接口上的重复地址。")
            block = self.doc.find("interface", self.context["target"])
            primary = None
            for raw in self.doc.lines[block.start + 1:block.end]:
                value = raw.strip()
                if value == self.inverse + "ip address":
                    primary = None
                elif re.fullmatch(r"ip address \S+ \S+", value):
                    primary = value
                elif value.startswith(self.inverse + "ip address ") and primary and value[len(self.inverse):] == primary:
                    primary = None
            primary_address = None
            if primary is not None:
                try:
                    parts = primary.split()
                    primary_address = ipaddress.IPv4Interface(parts[2] + "/" + parts[3])
                except (ValueError, IndexError):
                    _reject("已有主地址语法不能可靠识别，无法确认地址角色。", "先核对接口原有主地址与辅助地址。")
                # Equivalent mask spellings may have removed the primary
                # address without matching its original physical line.
                if str(primary_address) not in iface.addresses:
                    primary, primary_address = None, None
            if m[3] and (not iface.addresses or primary is None):
                _reject("没有主 IPv4 地址，不能先添加辅助地址。", "先配置主地址，再添加 secondary / sub 地址。")
            if str(address) in iface.addresses:
                currently_primary = primary_address == address
                if currently_primary == bool(m[3]):
                    _reject("这个地址已存在，但主地址/辅助地址角色与本条命令不同。", "先移除并核对现有地址，再按所需顺序配置主地址和辅助地址。")
                return "noop", "接口已配置该地址。", "", ""
            if any(ipaddress.IPv4Interface(x).ip == address.ip for x in iface.addresses):
                _reject("本接口已使用这个 IPv4 地址，不能用另一个掩码或地址角色重复添加。", "先移除已有地址，再设置新的主地址或辅助地址。")
            if m[3]:
                return self.edit(lambda x: x.removeprefix(self.inverse).startswith("ip address ")
                                 and x.removeprefix(self.inverse).split()[2] == m[1]
                                 and (x.endswith((" secondary", " sub")) or x.startswith(self.inverse)), s)
            # Rebuild this supported family from its effective state. Retain
            # secondary addresses, remove stale inverse lines, preserve all
            # other interface commands byte-for-byte.
            family = [line.strip() for line in self.doc.lines[block.start + 1:block.end]
                      if line.strip().startswith(("ip address ", self.inverse + "ip address"))]
            for line in family:
                if line == self.inverse + "ip address":
                    continue
                raw = line.removeprefix(self.inverse)
                if not re.fullmatch(r"ip address \S+ \S+(?: (?:secondary|sub))?", raw):
                    _reject("已有地址使用未建模的动态或借用语法，不能安全替换。", "先核对该接口原有地址方式。")
            secondary = []
            for old in iface.addresses[1:] if primary is not None else iface.addresses:
                parsed = ipaddress.IPv4Interface(old)
                secondary.append(f"ip address {parsed.ip} {parsed.netmask} " + ("secondary" if self.ios else "sub"))
            return self.edit(lambda x: x.startswith(("ip address ", self.inverse + "ip address")), [s] + secondary)
        if s == self.inverse + "ip address":
            return self.edit(lambda x: x.startswith(("ip address ", self.inverse + "ip address")), None)
        binding_command = s.removeprefix(self.inverse)
        binding = re.fullmatch(r"ip access-group ([\w.-]+) (in|out)", binding_command) if self.ios else re.fullmatch(r"traffic-filter (inbound|outbound) acl (\d+)", binding_command) if self.vendor == "huawei" else re.fullmatch(r"packet-filter (\d+) (inbound|outbound)", binding_command)
        if binding:
            name, direction = (binding[2], binding[1]) if self.vendor == "huawei" else (binding[1], binding[2])
            prefix = "ip access-group " if self.ios else "traffic-filter " if self.vendor == "huawei" else "packet-filter "
            matcher = lambda x: x.removeprefix(self.inverse).startswith(prefix) and direction in x.split()
            if s.startswith(self.inverse):
                if iface.acl_bindings.get(direction) != name:
                    return "noop", "该方向没有绑定这个 ACL，无需解除。", "", ""
                return self.edit(matcher, None)
            if name not in cfg.acls:
                _reject("引用的 ACL 尚未创建。", "先在全局视图创建并核对 ACL，再绑定接口。")
            if not cfg.acls[name].rules:
                _reject("ACL 还没有规则，绑定后的默认行为无法可靠练习。", "先增加明确的 permit / deny 规则。")
            return self.edit(matcher, s)
        stp = {"spanning-tree portfast", "no spanning-tree portfast", "spanning-tree bpduguard enable", "no spanning-tree bpduguard enable", "spanning-tree bpdufilter enable", "no spanning-tree bpdufilter enable"} if self.ios else {"stp enable", "stp disable", "stp edged-port enable", "stp edged-port disable"}
        if self.vendor == "ruijie":
            stp |= {"spanning-tree bpdufilter enabled", "spanning-tree bpdufilter disabled"}
        if s in stp:
            base = s.removeprefix(self.inverse)
            family = "spanning-tree portfast" if "portfast" in base else "spanning-tree bpduguard" if "bpduguard" in base else "spanning-tree bpdufilter" if "bpdufilter" in base else "stp edged-port" if "edged-port" in base else "stp bpdu-protection" if "bpdu-protection" in base else "stp "
            return self.edit(lambda x: x.removeprefix(self.inverse).startswith(family) if family != "stp " else x in ("stp enable", "stp disable"), s)
        _reject("该接口命令或厂商方言暂未建模。", "查看接口可练习命令；未知命令不会写入候选配置。", "unsupported")

    def vty(self, s: str):
        prefix = "transport input " if self.ios else "protocol inbound "
        if s.startswith(prefix):
            values = s[len(prefix):].split()
            permitted = {"ssh", "telnet", "all", "none"} if self.ios else {"ssh", "telnet", "all"}
            if not values or set(values) - permitted or len(values) != len(set(values)) or (len(values) > 1 and set(values) & {"all", "none"}):
                _reject("管理协议组合无效。", "使用 ssh，或显式列出 ssh telnet。", "invalid")
            result = self.edit(lambda x: x.startswith(prefix), s)
            return result[0], "已更新 VTY 允许的管理协议。", "Telnet 为明文；SSH 仍需已有用户、认证和设备密钥。", ""
        timeout = "exec-timeout" if self.ios else "idle-timeout"
        m = re.fullmatch(timeout + r" (\d+)(?: (\d+))?", s)
        if m:
            if not 0 <= int(m[1]) <= 35791 or not 0 <= int(m[2] or 0) <= 59:
                _reject("超时值不在支持范围内。", "分钟使用 0–35791，秒使用 0–59。", "invalid")
            return self.edit(lambda x: x.startswith(timeout + " "), s)
        if s in (("login local",) if self.ios else ("authentication-mode aaa", "authentication-mode scheme")):
            if (self.vendor == "huawei" and s.endswith("scheme")) or (self.vendor == "h3c" and s.endswith("aaa")):
                _reject("认证模式关键字与厂商不符。", "Huawei 使用 aaa；H3C 使用 scheme。", "unsupported")
            if not any(re.match(r"(?:username|local-user) \S+", e.text) for e in self.cfg().global_commands):
                _reject("备份中未识别到本地管理用户，切换认证可能失去登录入口。", "先核对用户与 AAA 配置；本版不创建或修改凭据。")
            return self.edit(lambda x: x in ("login", "login local", "no login") or x.startswith(("login authentication ", "authentication-mode ")), s)
        _reject("此 VTY 命令暂未建模。", "可修改接入协议和会话超时；凭据修改需在实机文档中核对。", "unsupported")

    def global_command(self, s: str):
        pairs = [("ip ssh version 1", "ip ssh version 2"), ("ip http server", "no ip http server"), ("ip http secure-server", "no ip http secure-server")] if self.ios else [("stelnet server enable", "undo stelnet server enable"), ("telnet server enable", "undo telnet server enable"), ("http server enable", "undo http server enable"), ("http secure-server enable", "undo http secure-server enable")]
        if self.vendor == "h3c":
            pairs = [("ssh server enable", "undo ssh server enable"), ("telnet server enable", "undo telnet server enable"), ("ip http enable", "undo ip http enable"), ("ip https enable", "undo ip https enable")]
        for pair in pairs:
            if s in pair:
                result = self.edit(lambda x, p=pair: x in p, s)
                return result[0], "已更新管理服务的显式配置。", "开启服务不等于具备完整登录条件；用户、密钥、ACL 和设备支持仍需核对。", ""
        stp = {"spanning-tree mode pvst", "spanning-tree mode rapid-pvst", "spanning-tree mode mst"} if self.vendor == "cisco" else {"spanning-tree", "no spanning-tree"} if self.vendor == "ruijie" else {"stp enable", "stp disable", "stp mode stp", "stp mode rstp", "stp mode mstp"}
        if s in stp:
            if " mode " in s:
                prefix = "spanning-tree mode " if self.ios else "stp mode "
                return self.edit(lambda x: x.startswith(prefix), s)
            return self.edit(lambda x: x in ("spanning-tree", "no spanning-tree") if self.ios else x in ("stp enable", "stp disable"), s)
        _reject("该全局命令未在本版配置模型中实现。", "本版支持基础 VLAN、接口、静态路由、ACL 和部分管理/STP 配置；ping、重启、保存及动态协议运行状态不模拟。", "unsupported")

    def route(self, s: str):
        remove = s.startswith(("no ", "undo "))
        prefix = "ip route" if self.ios else "ip route-static"
        pattern = (re.escape(self.inverse) if remove else "") + re.escape(prefix) + r" (\S+) (\S+) (\S+)(?: " + (r"(\d+)" if self.ios else r"preference (\d+)") + r")?"
        m = re.fullmatch(pattern, s)
        if not m:
            _reject("只支持默认 VRF 的 IPv4 网段、掩码、下一跳和可选优先级。", "使用 " + prefix + " <网段> <掩码> <下一跳IPv4>。", "unsupported")
        destination = ipaddress.IPv4Network(m[1] + "/" + _netmask(m[2], self.ios), strict=True)
        hop = ipaddress.IPv4Address(m[3])
        if hop.is_unspecified or hop.is_multicast or hop.is_loopback or hop == ipaddress.IPv4Address("255.255.255.255"):
            _reject("下一跳不是有效单播地址。", "使用可路由的下一跳 IPv4 地址。", "invalid")
        if not remove and any(iface.vrf == "default" and any(ipaddress.IPv4Interface(value).ip == hop for value in iface.addresses)
                              for iface in self.cfg().interfaces.values()):
            _reject("下一跳是本设备已有接口地址，不能把自身设置为下一跳。", "使用相邻设备地址；实际可达性仍需在实机确认。")
        if m[4] and not 1 <= int(m[4]) <= 255:
            _reject("优先级必须在 1–255 范围内。", "请按设备支持范围选择优先级。", "invalid")
        canonical = s[len(self.inverse):] if remove else s
        def matches(text):
            text = text.removeprefix(self.inverse)
            match = re.fullmatch(re.escape(prefix) + r" (\S+) (\S+) (\S+)(?: (?:preference )?\d+)?", text)
            if not match:
                return False
            try:
                return ipaddress.IPv4Network(match[1] + "/" + match[2], strict=False) == destination and ipaddress.IPv4Address(match[3]) == hop
            except ValueError:
                return False
        result = self.edit(matches, None if remove else canonical)
        return result[0], "已更新静态路由配置。", "下一跳可达性、递归查找及实际选路未模拟。", ""

    def acl_select(self, s: str):
        if self.ios:
            m = re.fullmatch(r"ip access-list (standard|extended) ([A-Za-z0-9_.-]{1,64})", s)
            if not m:
                _reject("只支持命名 standard / extended ACL。", "使用 ip access-list extended <名称>。", "unsupported")
            kind, name = m[1], m[2]
        else:
            pattern = r"acl number (\d+)" if self.vendor == "huawei" else r"acl (?:number |basic |advanced )?(\d+)"
            m = re.fullmatch(pattern, s)
            if not m or not 2000 <= int(m[1]) <= 3999:
                _reject("只支持 2000–2999 基本 ACL 和 3000–3999 高级 ACL。", "使用 acl number 3000。", "unsupported")
            name = m[1]
            kind = "standard" if int(name) < 3000 else "extended"
            if ("basic " in s and kind != "standard") or ("advanced " in s and kind != "extended"):
                _reject("ACL 编号与种类不匹配。", "基本 ACL 使用 2000–2999；高级 ACL 使用 3000–3999。", "invalid")
        acl = self.cfg().acls.get(name)
        if acl and acl.kind != kind:
            _reject("同名 ACL 已存在且种类不同。", "选择其他名称或现有 ACL 的种类。")
        if acl:
            self.doc.find("acl", name)
        else:
            self.doc.append(s)
        self.context = {"mode": "acl", "target": name}
        return "mode" if acl else "applied", "已进入 ACL 视图。", "添加完整规则后再绑定接口；规则过宽可通过审计发现。", ""

    def acl_rule(self, s: str):
        acl = self.cfg().acls[self.context["target"]]
        delete = re.fullmatch(r"no (\d+)" if self.ios else r"undo rule (\d+)", s)
        if delete:
            seq = int(delete[1])
            return self.edit(lambda x: bool(re.match((rf"^{seq} " if self.ios else rf"^rule {seq} "), x)) or x == (f"no {seq}" if self.ios else f"undo rule {seq}"), None)
        m = re.match(r"^(\d+) (permit|deny) " if self.ios else r"^rule (\d+) (permit|deny)(?: |$)", s)
        if not m or not 1 <= int(m[1]) <= 65535:
            _reject("只支持带显式序号的基础 ACL 规则。", "指定 1–65535 的规则序号和完整匹配条件。", "unsupported")
        try:
            rule = _acl_rule(s, self.vendor, acl.kind, int(m[1]), Evidence(0, _safe(s)))
        except (ValueError, IndexError):
            _reject("ACL 规则不完整或地址/掩码格式错误。", "检查动作、协议、源地址和目的地址。", "invalid")
        if not rule.complete:
            _reject("该 ACL 扩展条件未完整建模。", "仅使用支持的地址、连续 wildcard、协议和基础端口条件。", "unsupported")
        if not self.ios:
            tokens = s.split()
            fields = ("source", "destination", "source-port", "destination-port", "logging", "counting")
            if any(tokens.count(field) > 1 for field in fields):
                _reject("ACL 同一匹配字段不能重复指定。", "每条规则只写一次源、目的和各自端口条件。", "invalid")
            if acl.kind == "standard" and any(field in tokens for field in ("destination", "source-port", "destination-port")):
                _reject("基本 ACL 仅支持源地址匹配。", "需要目的地址或端口条件时使用 3000–3999 的高级 ACL。", "invalid")
        if " wildcard " in rule.source or " wildcard " in rule.destination:
            _reject("非连续 wildcard 的匹配语义暂不模拟。", "使用连续 wildcard 或单个主机地址。", "unsupported")
        ports = [value for value in (rule.source_port, rule.destination_port) if value]
        if ports and (acl.kind == "standard" or rule.protocol not in ("tcp", "udp")):
            _reject("端口条件只能用于高级 ACL 的 TCP 或 UDP 规则。", "核对协议后再添加端口条件。", "invalid")
        for value in ports:
            parts = value.split()
            if any(not v.isdigit() or not 0 <= int(v) <= 65535 for v in parts[1:]):
                _reject("本版端口条件仅支持 0–65535 的数值。", "使用有效的数字端口；服务名暂不模拟。", "invalid")
            if parts[0] == "range" and int(parts[1]) > int(parts[2]):
                _reject("端口范围不能倒置。", "将起始端口放在结束端口之前。", "invalid")
        seq = int(m[1])
        return self.edit(lambda x: bool(re.match((rf"^{seq} " if self.ios else rf"^rule {seq} "), x)) or x == (f"no {seq}" if self.ios else f"undo rule {seq}"), s)


def simulate_configuration(config: str, vendor: str = "auto", commands: str = "", context: dict | None = None) -> dict:
    """Return a candidate; caller explicitly applies it. Input errors raise ValueError."""
    if not isinstance(config, str) or not isinstance(commands, str):
        raise ValueError("配置和命令必须为文本")
    if vendor not in VENDORS:
        raise ValueError("厂商必须为 auto / cisco / huawei / h3c / ruijie")
    try:
        command_size = len(commands.encode("utf-8"))
    except UnicodeError:
        raise ValueError("命令包含无效的 Unicode 字符") from None
    if command_size > MAX_COMMAND_BYTES or len(commands.splitlines()) > MAX_COMMAND_LINES:
        raise ValueError("每批命令不能超过 200 行或 64 KiB")
    if _unsafe_control(commands):
        raise ValueError("命令含控制字符，请使用纯文本命令")
    if _unsafe_control(config):
        raise ValueError("配置含控制字符，请使用纯文本备份")
    try:
        initial = parse_config(config, vendor)
    except UnicodeError:
        raise ValueError("配置包含无效的 Unicode 字符") from None
    vendor = initial.vendor
    doc = _Document(config, vendor)
    original_context = _context(context, initial, doc)
    session = _Session(doc, original_context)
    results = []
    output_budget = MAX_OUTPUT_BYTES
    for command in commands.splitlines():
        if not command.strip():
            continue
        result = {"command": _safe(command.strip()), "status": "invalid", "reason": "", "suggestion": "", "output": "", "rolled_back": False}
        try:
            # Validate boundaries before any edit, including malformed banners.
            doc.blocks()
            if output_budget <= 0 and command.strip().startswith(("show ", "display ")):
                # Still validate the requested show command, but never expand
                # another full 2 MiB backup into the response.
                allowed_shows = {"show running-config", "show vlan", "show vlan brief", "show ip interface brief", "show interfaces", "show ip route", "show access-lists"} if session.ios else {"display current-configuration", "display vlan", "display ip interface brief", "display interface brief", "display ip routing-table", "display acl all"}
                if command.strip() not in allowed_shows:
                    _reject("此查看命令未建模。", "查看当前支持的只读命令。", "unsupported")
                status, reason, suggestion, output = "show", "本批只读输出已达到 256 KiB 上限。", "请分批查看。", ""
            else:
                status, reason, suggestion, output = session.run(command)
            # Resource failures reject the batch rather than returning partial IR.
            session.cfg()
            encoded = output.encode("utf-8")
            if len(encoded) > output_budget:
                output = encoded[:output_budget].decode("utf-8", errors="ignore") + "\n[输出已截断：本批最多显示 256 KiB；完整配置请显式导出。]"
                output_budget = 0
            else:
                output_budget -= len(encoded)
            result.update(status=status, reason=_safe(reason), suggestion=_safe(suggestion), output=_safe(output))
        except _Rejected as exc:
            result.update(status=exc.status, reason=_safe(exc.reason), suggestion=_safe(exc.suggestion))
        except (ValueError, IndexError):
            result.update(status="invalid", reason="参数格式、地址/VLAN 范围或候选配置大小不合法。", suggestion="检查命令格式、ID、掩码和输入上限后重新模拟。")
        results.append(result)
    rolled_back = any(r["status"] in _FAILURE for r in results)
    if rolled_back:
        for result in results:
            if result["status"] not in _FAILURE:
                result["rolled_back"] = True
                result["reason"] += " 本批存在失败命令，配置与视图变化均已回滚。"
                if result["status"] == "show":
                    result["output"] = "本批已回滚；不保留基于临时状态生成的查看输出。"
        final_config, final_context, inventory = config, original_context, initial.to_dict()
    else:
        final_config, final_context = doc.text, dict(session.context)
        inventory = session.cfg().to_dict()
    # Redact before diffing so even context lines cannot disclose credentials.
    diff_lines = list(difflib.unified_diff(_safe(config).splitlines(), _safe(final_config).splitlines(), fromfile="当前配置", tofile="候选配置", lineterm=""))
    diff = "\n".join(diff_lines) + ("\n" if diff_lines else "")
    return {"vendor": vendor, "config": final_config, "context": final_context,
            "prompt": _prompt(final_context, vendor), "results": results,
            "summary": {"applied": 0 if rolled_back else sum(r["status"] == "applied" for r in results),
                        "blocked": sum(r["status"] == "blocked" for r in results),
                        "unsupported": sum(r["status"] == "unsupported" for r in results),
                        "invalid": sum(r["status"] == "invalid" for r in results),
                        "changed": final_config != config, "rolled_back": rolled_back},
            "diff": diff, "inventory": inventory, "capabilities": _capabilities(vendor, final_context),
            "limitations": list(_LIMITATIONS)}
