"""Group repeated, equivalent risks without hiding objects or evidence.

Only rules with an explicitly shared remediation are grouped. Object-specific
ACL ordering, OSPF process/area, NAT mapping, and route checks stay separate.
VLAN-UNDEFINED is already grouped by VLAN ID in NetworkChecks and is deliberately
not grouped here, so two distinct missing VLANs never become one issue.
"""
from __future__ import annotations

from copy import deepcopy

from .model import Config, Evidence, Finding


SHARED_REMEDIATION_RULES = frozenset({
    "MGMT-CREDENTIAL", "MGMT-SNMP-COMMUNITY", "MGMT-VTY-TELNET",
    "MGMT-VTY-UNKNOWN", "MGMT-VTY-NOAUTH", "MGMT-VTY-TIMEOUT",
    "MGMT-VTY-SOURCE", "STP-EDGE-TRUNK", "STP-BPDU-FILTER",
    "VLAN-TRUNK-ALL", "VLAN-NATIVE-1",
})


def unique_evidence(values) -> list[Evidence]:
    """Keep source line and redacted text together when removing duplicates."""
    seen = set()
    result = []
    for value in values:
        if value is None:
            continue
        identity = (value.line, value.text)
        if identity not in seen:
            seen.add(identity)
            result.append(value)
    return sorted(result, key=lambda value: value.line)


def _unique(values):
    return list(dict.fromkeys(values))


def populate_affected_objects(findings: list[Finding], config: Config) -> None:
    """Attach known source scopes before commands and grouping are generated."""
    scopes: dict[int, list[str]] = {}
    for interface in config.interfaces.values():
        evidence = interface.evidence + interface.stp_evidence + interface.ospf_evidence
        for value in evidence:
            scopes.setdefault(value.line, []).append(interface.name)
    for management in config.management_lines:
        for value in management.evidence:
            scopes.setdefault(value.line, []).append(management.name)
    for name, acl in config.acls.items():
        scopes.setdefault(acl.line, []).append("ACL " + name)
        for rule in acl.rules:
            if rule.evidence is not None:
                scopes.setdefault(rule.evidence.line, []).append("ACL " + name)

    for finding in findings:
        if finding.affected_objects:
            continue
        objects = []
        for value in finding.evidence:
            objects.extend(scopes.get(value.line, []))
            if finding.rule_id == "MGMT-CREDENTIAL" and value.line not in scopes:
                words = value.text.split()
                if len(words) >= 2 and words[0] in ("username", "local-user"):
                    objects.append("账号 " + words[1])
                elif words and words[0] == "enable":
                    objects.append("enable 特权凭据")
                else:
                    objects.append(f"凭据配置行 {value.line}")
        finding.affected_objects = _unique(objects)
        if not finding.affected_objects and finding.evidence:
            finding.affected_objects = [f"配置行 {value.line}" for value in unique_evidence(finding.evidence)]


def _group_key(finding: Finding):
    allowed = finding.rule_id in SHARED_REMEDIATION_RULES
    # STP-DISABLED has global, per-VLAN, and per-interface scopes. Only the
    # repeated interface case shares the same exact remediation context.
    if finding.rule_id == "STP-DISABLED":
        allowed = finding.problem.startswith("接口 ")
    if not allowed or not finding.affected_objects:
        return None
    return (finding.rule_id, finding.severity, finding.category,
            finding.confidence, finding.title, finding.risk,
            finding.recommendation)


def group_findings(findings: list[Finding]) -> list[Finding]:
    """Return independent grouped findings with every original scope retained.

    Commands and templates are concatenated as complete independent scripts;
    repeated lines such as ``exit`` or ``interface`` must never be removed.
    Only an identical *whole* script is redundant. Read-only verification
    commands can safely be deduplicated individually.
    """
    result = []
    groups = {}
    command_scripts = {}
    template_scripts = {}
    problems = {}
    notes = {}
    for finding in findings:
        key = _group_key(finding)
        if key is None or key not in groups:
            copied = deepcopy(finding)
            copied.evidence = unique_evidence(copied.evidence)
            copied.affected_objects = _unique(copied.affected_objects)
            copied.verification_commands = _unique(copied.verification_commands)
            result.append(copied)
            if key is not None:
                groups[key] = copied
                command_scripts[key] = {tuple(copied.commands)}
                template_scripts[key] = {tuple(copied.command_templates)}
                problems[key] = [copied.problem]
                notes[key] = [copied.command_notes] if copied.command_notes else []
            continue
        grouped = groups[key]
        grouped.occurrences += finding.occurrences
        grouped.affected_objects = _unique(grouped.affected_objects + finding.affected_objects)
        grouped.evidence = unique_evidence(grouped.evidence + finding.evidence)
        grouped.verification_commands = _unique(grouped.verification_commands + finding.verification_commands)
        for field, scripts in (("commands", command_scripts), ("command_templates", template_scripts)):
            incoming = getattr(finding, field)
            identity = tuple(incoming)
            if incoming and identity not in scripts[key]:
                getattr(grouped, field).extend(incoming)
                scripts[key].add(identity)
        if finding.problem not in problems[key]:
            problems[key].append(finding.problem)
            grouped.problem = "\n".join(problems[key])
        if finding.command_notes and finding.command_notes not in notes[key]:
            notes[key].append(finding.command_notes)
            grouped.command_notes = "\n\n".join(notes[key])
    return result
