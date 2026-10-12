from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Evidence:
    line: int
    text: str


@dataclass
class Interface:
    name: str
    line: int
    shutdown: bool | None = None
    description: str = ""
    mode: str | None = None
    access_vlan: int | None = None
    native_vlan: int | None = None
    allowed_vlans: list[int] | None = None
    addresses: list[str] = field(default_factory=list)
    vrf: str = "default"
    acl_bindings: dict[str, str] = field(default_factory=dict)
    nat_role: str | None = None
    # None means the supplied configuration does not establish the state.
    stp_enabled: bool | None = None
    stp_edge: bool | None = None
    bpdu_guard: bool | None = None
    bpdu_filter: bool | None = None
    stp_evidence: list[Evidence] = field(default_factory=list)
    ospf_binding: dict | None = None
    ospf_authentication: str | None = None
    ospf_evidence: list[Evidence] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    # Protected ports provide isolation; this does not establish STP protection.
    protected: bool | None = None


@dataclass
class ACLRule:
    sequence: int
    action: str
    protocol: str
    source: str = "any"
    destination: str = "any"
    source_port: str | None = None
    destination_port: str | None = None
    complete: bool = True
    evidence: Evidence | None = None


@dataclass
class ACL:
    name: str
    kind: str
    line: int
    rules: list[ACLRule] = field(default_factory=list)
    ordered: bool = True


@dataclass
class Route:
    destination: str
    next_hop: str | None
    interface: str | None
    vrf: str
    distance: int | None
    evidence: Evidence
    complete: bool = True
    unparsed_tokens: list[str] = field(default_factory=list)


@dataclass
class NAT:
    kind: str
    interface: str | None
    acl: str | None
    pool: str | None
    protocol: str | None
    inside: str | None
    outside: str | None
    outside_port: str | None
    evidence: Evidence
    complete: bool = True
    outside_interface: str | None = None
    unparsed_tokens: list[str] = field(default_factory=list)


@dataclass
class ManagementLine:
    name: str
    line: int
    transport: list[str] | None = None
    authentication: str | None = None
    idle_seconds: int | None = None
    acl_bindings: dict[str, str] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class Config:
    vendor: str
    detection: str
    hostname: str
    interfaces: dict[str, Interface] = field(default_factory=dict)
    vlans: dict[int, dict] = field(default_factory=dict)
    routes: list[Route] = field(default_factory=list)
    routing_processes: list[dict] = field(default_factory=list)
    acls: dict[str, ACL] = field(default_factory=dict)
    nat: list[NAT] = field(default_factory=list)
    nat_pools: dict[str, dict] = field(default_factory=dict)
    management_lines: list[ManagementLine] = field(default_factory=list)
    global_commands: list[Evidence] = field(default_factory=list)
    stp: dict = field(default_factory=lambda: {
        "enabled": None, "mode": None, "edge_default": None,
        "bpdu_guard_default": None, "bpdu_filter_default": None,
        "vlan_enabled": {}, "evidence": [],
    })
    warnings: list[dict] = field(default_factory=list)
    line_count: int = 0
    relevant_lines: int = 0
    recognized_lines: int = 0
    unsupported_count: int = 0

    def to_dict(self) -> dict:
        value = asdict(self)
        # Keep wire reports small even for hundreds of allow-all trunks.
        for iface in value["interfaces"].values():
            ids = iface.pop("allowed_vlans")
            ranges = None
            if ids is not None:
                ranges = []
                for vid in ids:
                    if ranges and vid == ranges[-1][1] + 1:
                        ranges[-1][1] = vid
                    else:
                        ranges.append([vid, vid])
            iface["allowed_vlan_ranges"] = ranges
        return value


@dataclass
class Finding:
    rule_id: str
    severity: str
    category: str
    title: str
    problem: str
    risk: str
    recommendation: str
    evidence: list[Evidence]
    confidence: str = "confirmed-config"
    commands: list[str] = field(default_factory=list)
    verification_commands: list[str] = field(default_factory=list)
    command_templates: list[str] = field(default_factory=list)
    command_notes: str = ""
    affected_objects: list[str] = field(default_factory=list)
    occurrences: int = 1

    def to_dict(self) -> dict:
        return asdict(self)
