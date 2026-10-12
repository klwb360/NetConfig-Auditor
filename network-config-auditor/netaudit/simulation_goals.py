"""Small, explicit Chinese goal templates for the offline configuration lab.

Whole-sentence matching is intentional: recognizing one clause is not enough to
claim a user's goal has been met. Every draft is checked by the same simulator
that handles typed commands. No network, model service or device is contacted.
"""
from __future__ import annotations

import ipaddress
import re

from .parser import IOS_VENDORS, parse_config, vlan_ids
from .privacy import redact
from .simulator import simulate_configuration

MAX_GOAL_CHARS = 2000
MAX_GOAL_VLANS = 32
_TOKEN = r"[A-Za-z][A-Za-z0-9./:_-]*"
_VLAN_LIST = r"\d+(?:\s*(?:-|to|至)\s*\d+)?(?:\s*(?:[,，、]|和)\s*\d+(?:\s*(?:-|to|至)\s*\d+)?)*"
_ADDRESS = r"\d{1,3}(?:\.\d{1,3}){3}"
_IP_WITH_MASK = rf"{_ADDRESS}(?:\s*/\s*(?:\d{{1,2}}|{_ADDRESS})|\s+(?:掩码\s*)?{_ADDRESS})"
_SENSITIVE = re.compile(r"密码|口令|凭据|密钥|(?:password|secret|community|token|authentication)\b", re.I)


def _safe_goal(goal: str) -> str:
    if _SENSITIVE.search(goal):
        return "包含凭据信息的目标已隐藏。"
    return redact(goal)


def _answer(goal: str, status: str, summary: str, *, questions=()) -> dict:
    return {"status": status, "goal": _safe_goal(goal), "summary": summary,
            "commands": "", "steps": [], "questions": list(questions)}


def _match(patterns, text: str):
    for pattern in patterns:
        match = re.fullmatch(pattern, text, re.I)
        if match:
            return match
    return None


def _ids(value: str) -> list[int]:
    normalized = re.sub(r"[,，、和]", " ", value)
    normalized = normalized.replace("至", " to ")
    result = sorted(vlan_ids(normalized))
    if len(result) > MAX_GOAL_VLANS:
        raise ValueError("一次目标最多配置 32 个 VLAN；请拆成几次练习。")
    return result


def _ip_and_mask(value: str, *, network: bool = False) -> tuple[str, str]:
    value = re.sub(r"\s*/\s*", "/", value)
    value = re.sub(r"\s+(?:掩码\s*)?", "/", value.strip())
    address = ipaddress.IPv4Network(value, strict=True) if network else ipaddress.IPv4Interface(value)
    return str(address.network_address if network else address.ip), str(address.netmask)


class _Draft:
    def __init__(self, cfg):
        self.cfg = cfg
        self.ios = cfg.vendor in IOS_VENDORS
        self.exit = "exit" if self.ios else "quit"
        self.end = "end" if self.ios else "return"
        self.inverse = "no " if self.ios else "undo "
        self.steps = []
        self.add(self.end, "先返回执行视图，避免从上次练习的接口或 VLAN 视图误执行。")
        self.add("configure terminal" if self.ios else "system-view", "进入全局配置视图。")

    def add(self, command: str, reason: str) -> None:
        self.steps.append({"command": command, "reason": reason})

    def create_missing(self, values: list[int]) -> None:
        for vid in values:
            if vid not in self.cfg.vlans:
                self.add(f"vlan {vid}", f"备份中尚未定义 VLAN {vid}；先创建，接口才能引用它。")
                self.add(self.exit, "返回全局配置视图。")

    def interface(self, value: str) -> str | None:
        # Resolve case only; never expand abbreviations or invent an interface.
        matches = [name for name in self.cfg.interfaces if name.casefold() == value.casefold()]
        if len(matches) != 1:
            return None
        name = matches[0]
        self.add("interface " + name, "选择备份中已经存在的接口。")
        return name

    def finish(self) -> None:
        self.add(self.end, "结束本次草案，返回执行视图。")


def plan_goal(config: str, vendor: str = "auto", goal: str = "", context: dict | None = None) -> dict:
    """Return a checked command draft, or ask for information without guessing.

    ``ready`` means the offline simulator accepts the whole draft. It does not
    assert device compatibility, forwarding behaviour, or a working login.
    Candidate configuration, inventory and diffs are deliberately not returned.
    """
    if not isinstance(goal, str):
        raise ValueError("目标必须为纯文本")
    if len(goal) > MAX_GOAL_CHARS:
        raise ValueError("目标不能超过 2000 个字符")
    try:
        goal.encode("utf-8")
    except UnicodeError:
        raise ValueError("目标包含无效的 Unicode 字符") from None
    if any(ord(c) < 32 or 127 <= ord(c) <= 159 or c in "\u2028\u2029" for c in goal) or re.search(r"<[^>]*>", goal):
        raise ValueError("目标请使用单行纯文本，不要包含控制字符或标签")
    text = goal.strip().rstrip("。！？!?").strip()
    text = re.sub(r"^(?:请帮我|请|帮我|我想要|我想|我要)\s*", "", text)
    if not text:
        return _answer(goal, "needs-input", "请先描述一个具体配置目标。",
                       questions=["例如：创建 VLAN 20；或把接口 GigabitEthernet0/1 加入 VLAN 20。"])
    if _SENSITIVE.search(text):
        return _answer(goal, "unsupported", "本版不生成用户、密码或密钥修改命令；请不要在目标中填写凭据。")
    # Reject ambiguous requirements as a whole, including a supported clause
    # followed by a condition, negation or another requested operation.
    if re.search(r"不要|不用|不能|不想|不需要|别|勿|除了|除外|保持|如果|但是|但要|然后|同时|并且|以及|并|[;；\n\r]", text):
        return _answer(goal, "needs-input", "目标包含条件、否定或多个动作，目前无法保证完整理解。",
                       questions=["请一次写一个明确动作，并给出接口、VLAN 或地址等具体参数。"])
    if not isinstance(config, str):
        raise ValueError("配置必须为文本")
    try:
        cfg = parse_config(config, vendor)
        # Validate context even for an unanswered goal, without exposing the
        # simulator's inventory (which can contain backup credentials).
        simulate_configuration(config, cfg.vendor, "", context)
    except (ValueError, UnicodeError):
        return _answer(goal, "blocked", "备份、厂商或当前视图无法确认；请先导入有效备份并选择正确厂商。")

    draft = _Draft(cfg)
    ios = draft.ios
    summary = ""

    def missing_interface():
        return _answer(goal, "blocked", "备份中没有唯一匹配的接口；不能猜测或创建物理端口。",
                       questions=["请使用已导入备份中的接口完整名称。"])

    match = re.fullmatch(rf"(创建|新建|添加|增加|删除|移除)\s*(?:一个\s*)?VLAN(?:\s*({_VLAN_LIST}))?", text, re.I)
    if match:
        if not match[2]:
            return _answer(goal, "needs-input", "还缺少 VLAN 编号。", questions=["要操作哪个 VLAN？请输入 1–4094，例如创建 VLAN 20。"])
        try:
            values = _ids(match[2])
        except ValueError:
            return _answer(goal, "needs-input", "VLAN 编号或范围无效，或一次超过 32 个 VLAN。", questions=["请给出 1–4094 范围内、最多 32 个 VLAN。"])
        removing = match[1] in ("删除", "移除")
        for vid in values:
            draft.add((draft.inverse if removing else "") + f"vlan {vid}",
                      "只有没有接口等依赖引用时，模拟器才允许删除。" if removing else "创建 VLAN；已有同编号 VLAN 会保留。")
            if not removing:
                draft.add(draft.exit, "返回全局配置视图。")
        summary = "删除指定 VLAN；若仍被引用，整份草案会被阻止。" if removing else "创建指定 VLAN，暂不改变端口归属。"
    else:
        match = _match([
            rf"(?:把|将)?\s*(?:接口|端口)?\s*({_TOKEN})\s*(?:加入|划入|接入|分配到)\s*VLAN\s*(\d+)?",
            rf"(?:把|将)?\s*(?:接口|端口)\s*({_TOKEN})\s*(?:的\s*)?(?:access|接入)\s*VLAN\s*(?:设置|设|改)?为\s*(\d+)?",
        ], text)
        if match:
            if not match[2]:
                return _answer(goal, "needs-input", "还缺少目标 VLAN 编号。", questions=["该接口要加入哪个 VLAN？"])
            try:
                values = _ids(match[2])
            except ValueError:
                return _answer(goal, "needs-input", "VLAN 编号必须在 1–4094 之间。", questions=["请提供有效 VLAN 编号。"])
            draft.create_missing(values)
            if not draft.interface(match[1]):
                return missing_interface()
            draft.add("switchport mode access" if ios else "port link-type access", "把该端口设为 access 模式，用于单个 VLAN 的接入。")
            prefix = "switchport access vlan " if ios else "port default vlan " if cfg.vendor == "huawei" else "port access vlan "
            draft.add(prefix + str(values[0]), "将接口的接入 VLAN 指向已定义的 VLAN。")
            summary = "把指定接口作为 access 端口加入目标 VLAN；缺少的 VLAN 会先创建。"

    if not summary:
        match = _match([
            rf"(?:把|将)?\s*(?:接口|端口)\s*({_TOKEN})\s*(?:的\s*)?trunk\s*(?:允许\s*(?:VLAN\s*)?(?:列表)?|允许列表)\s*(?:设置|设|改)?为\s*(?:VLAN\s*)?({_VLAN_LIST})",
            rf"(?:把|将)?\s*(?:接口|端口)\s*({_TOKEN})\s*(?:设置|设|改)为\s*trunk\s*[,，]?\s*允许\s*VLAN\s*({_VLAN_LIST})",
        ], text)
        if match:
            try:
                values = _ids(match[2])
            except ValueError:
                return _answer(goal, "needs-input", "允许列表编号无效，或一次超过 32 个 VLAN。", questions=["请明确列出 1–4094 范围内、最多 32 个 VLAN。"])
            draft.create_missing(values)
            if not draft.interface(match[1]):
                return missing_interface()
            draft.add("switchport mode trunk" if ios else "port link-type trunk", "将该端口设置为承载多个 VLAN 的 trunk 模式。")
            prefix = "switchport trunk allowed vlan " if ios else "port trunk allow-pass vlan " if cfg.vendor == "huawei" else "port trunk permit vlan "
            if not ios:
                draft.add("undo " + prefix + "1 to 4094", "该厂商的允许命令会累加；先清空显式范围，才能把列表准确替换为目标值。")
            draft.add(prefix + ("," if ios else " ").join(map(str, values)), "允许列表将仅包含这些 VLAN；未列出的 VLAN 将不再通过该 trunk。")
            summary = "将 trunk 允许列表完整替换为指定 VLAN；缺少的 VLAN 会先创建。"

    if not summary:
        match = _match([
            rf"(?:把|将)?\s*(?:接口|端口)\s*({_TOKEN})\s*(?:的)?描述\s*(?:设置|设|改)?为\s*(.+)",
            rf"(?:给|为)\s*(?:接口|端口)\s*({_TOKEN})\s*(?:设置|添加)描述\s*[:：]?\s*(.+)",
        ], text)
        if match:
            description = match[2].strip()
            quoted = (description[:1], description[-1:]) in (('"', '"'), ("“", "”"))
            if quoted:
                description = description[1:-1].strip()
            elif re.search(r"[,，:：]|创建|删除|关闭|开启|启用|禁用|配置|设置|添加|修改|运行|执行", description):
                return _answer(goal, "needs-input", "描述内容可能混有另一个操作，不能把整句话当成接口描述。",
                               questions=["请只描述一个动作；若这些词确实是接口说明，请将完整说明放在中文引号中。"])
            if not description or len(description) > 240 or any(c in description for c in ';；<>"“”'):
                return _answer(goal, "needs-input", "接口描述必须是 1–240 个字符的单行文本。", questions=["请提供简短用途，例如：接口 GigabitEthernet0/1 描述设为 办公室。"])
            if not draft.interface(match[1]):
                return missing_interface()
            draft.add("description " + description, "只修改接口用途说明，不改变接口转发配置。")
            summary = "更新指定接口的用途描述。"

    if not summary:
        match = _match([
            rf"(关闭|禁用|启用|开启|打开)\s*(?:接口|端口)\s*({_TOKEN})",
            rf"(?:把|将)?\s*(?:接口|端口)\s*({_TOKEN})\s*(关闭|禁用|启用|开启|打开)",
        ], text)
        if match:
            action, name = (match[1], match[2]) if match[1] in ("关闭", "禁用", "启用", "开启", "打开") else (match[2], match[1])
            if not draft.interface(name):
                return missing_interface()
            shutting = action in ("关闭", "禁用")
            draft.add("shutdown" if shutting else draft.inverse + "shutdown", "设置管理关闭，真实设备上的业务可能中断。" if shutting else "取消管理关闭；不代表网线、对端和链路已经正常。")
            summary = "关闭指定接口的管理状态。" if shutting else "启用指定接口的管理状态；不推断真实链路是否连通。"

    if not summary:
        match = _match([
            rf"(?:为|给)?\s*(?:接口|端口)\s*({_TOKEN})\s*(?:配置|设置)\s*(?:IPv4|IP)\s*(?:地址)?\s*(?:为)?\s*({_IP_WITH_MASK})",
            rf"(?:把|将)?\s*(?:接口|端口)\s*({_TOKEN})\s*(?:的)?\s*(?:IPv4|IP)\s*(?:地址)?\s*(?:设置|设|改)?为\s*({_IP_WITH_MASK})",
        ], text)
        if match:
            try:
                address, mask = _ip_and_mask(match[2])
            except ValueError:
                return _answer(goal, "needs-input", "IPv4 地址或掩码无效。", questions=["请给出完整地址和连续掩码，例如 192.0.2.1/24。"])
            if not draft.interface(match[1]):
                return missing_interface()
            draft.add(f"ip address {address} {mask}", "设置主 IPv4 地址；二层模式冲突或同一 VRF 地址重复时会阻止。")
            summary = "设置指定接口的主 IPv4 地址；不自动转换接口类型，也不证明网络可达。"

    if not summary and re.fullmatch(r"(?:关闭|禁用)\s*HTTP\s*(?:服务)?", text, re.I):
        draft.add("no ip http server" if ios else "undo http server enable" if cfg.vendor == "huawei" else "undo ip http enable", "关闭明文 HTTP 管理服务，HTTPS 配置保持原样。")
        summary = "关闭 HTTP 管理服务。"

    if not summary and re.fullmatch(r"(?:关闭|禁用)\s*Telnet\s*(?:服务)?", text, re.I):
        if not ios:
            draft.add("undo telnet server enable", "关闭明文 Telnet 服务；不改动 SSH 服务配置。")
        else:
            lines = cfg.management_lines
            if not lines or any(line.transport is None or "all" in line.transport for line in lines):
                return _answer(goal, "needs-input", "备份未完整说明 VTY 允许协议，无法只关闭 Telnet 而保留其他接入方式。",
                               questions=["请补充完整 VTY 配置，明确其现有 transport input 协议。"])
            for line in lines:
                if "telnet" not in line.transport:
                    continue
                remaining = [protocol for protocol in line.transport if protocol != "telnet"]
                if any(protocol != "ssh" for protocol in remaining):
                    return _answer(goal, "unsupported", "现有 VTY 协议组合超出本版模型，不能保证保留其余接入方式。")
                draft.add(line.name, "选择备份中明确存在的 VTY 范围。")
                draft.add("transport input " + (" ".join(remaining) if remaining else "none"), "仅移除 Telnet；若它是唯一协议，此范围将不再允许远程协议接入。")
                draft.add(draft.exit, "返回全局配置视图。")
        summary = "关闭 Telnet；只更改已明确识别的服务或 VTY 协议配置。"

    if not summary and re.fullmatch(r"(?:启用|开启|打开|设置)\s*SSH\s*(?:v?\s*2|版本\s*2)(?:\s*服务)?", text, re.I):
        if not ios:
            return _answer(goal, "unsupported", "本版未建模该厂商强制 SSHv2 的完整版本限制语法；不能用开启 SSH 服务代替此要求。")
        draft.add("ip ssh version 2", "把 SSH 协议版本限制为 2；不创建账号或密钥，也不更改 VTY 允许协议。")
        summary = "设置 SSHv2 协议版本；是否能够登录仍取决于已有用户、密钥和 VTY 配置。"

    if not summary and re.fullmatch(r"(?:启用|开启|打开)\s*SSH\s*(?:服务)?", text, re.I):
        if ios:
            return _answer(goal, "needs-input", "开启 SSH 还涉及版本、已有密钥和 VTY 允许协议，不能假定登录条件齐备。",
                           questions=["若只要设置协议版本，请写“启用 SSH2”；其他条件请在模拟命令行逐项练习。"])
        draft.add("stelnet server enable" if cfg.vendor == "huawei" else "ssh server enable", "开启 SSH 服务配置；仍需要已有用户、密钥、认证和访问控制。")
        summary = "开启 SSH 服务的配置开关；不保证实际登录可用，也不声称已强制只允许 SSHv2。"

    if not summary:
        match = re.fullmatch(rf"(添加|增加|创建|删除|移除)\s*(?:一条\s*)?静态路由\s*(?:到|至)?\s*({_IP_WITH_MASK})\s*[,，]?\s*(?:下一跳(?:为)?|经由|通过)\s*({_ADDRESS})", text, re.I)
        if match:
            try:
                network, mask = _ip_and_mask(match[2], network=True)
                hop = str(ipaddress.IPv4Address(match[3]))
            except ValueError:
                return _answer(goal, "needs-input", "目的网段、掩码或下一跳无效；目的地址必须是网段起始地址。", questions=["例如：添加静态路由 192.0.2.0/24 下一跳 198.51.100.1。"])
            removing = match[1] in ("删除", "移除")
            prefix = (draft.inverse if removing else "") + ("ip route" if ios else "ip route-static")
            draft.add(f"{prefix} {network} {mask} {hop}", "仅修改默认 VRF 的该目的网段与下一跳组合；下一跳在线状态和实际选路未模拟。")
            summary = "删除指定静态路由配置。" if removing else "添加默认 VRF 的 IPv4 静态路由；不验证下一跳可达性。"

    if not summary:
        if re.search(r"(?:接口|端口)|VLAN|静态路由|trunk|IPv4|\bIP\b", text, re.I):
            return _answer(goal, "needs-input", "尚不能完整确定这个配置目标，未生成部分命令。", questions=[
                "请一次提供一个完整目标，例如：把接口 GigabitEthernet0/1 加入 VLAN 20。",
                "trunk 请给出完整允许列表；IP 请给出地址和掩码；静态路由请给出目的网段和下一跳。",
            ])
        return _answer(goal, "unsupported", "本版中文模板暂不理解此目标；可以改写为一个具体动作，或在模拟命令行练习已支持命令。")

    draft.finish()
    commands = "\n".join(step["command"] for step in draft.steps)
    try:
        simulation = simulate_configuration(config, cfg.vendor, commands, context)
    except (ValueError, UnicodeError):
        return _answer(goal, "blocked", "草案未通过配置、视图或参数验证；请检查输入后再试。")
    # Explicit allowlist: no config, inventory, diff, output, or echoed original
    # configuration lines can escape through a goal-validation response.
    validation = {"vendor": simulation["vendor"], **simulation["summary"],
                  "results": [{key: row[key] for key in ("status", "reason", "suggestion")}
                              for row in simulation["results"]],
                  "note": "仅通过离线配置模型检查；不保证实机支持、登录成功或业务连通。"}
    failures = [row for row in simulation["results"] if row["status"] in ("blocked", "invalid", "unsupported")]
    if failures or simulation["summary"]["rolled_back"]:
        result = _answer(goal, "unsupported" if failures and all(row["status"] == "unsupported" for row in failures) else "blocked",
                         "草案当前不能完整运行：" + (failures[0]["reason"] if failures else "整批校验已回滚。"),
                         questions=[failures[0]["suggestion"]] if failures and failures[0]["suggestion"] else [])
        result["validation"] = validation
        return result
    result = _answer(goal, "ready", summary + " 草案已通过离线检查，尚未应用；请先查看每步理由。")
    result.update(commands=commands, steps=draft.steps, validation=validation)
    return result
