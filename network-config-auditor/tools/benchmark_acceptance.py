"""Independent golden-data acceptance; never writes or repairs expectations."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
FIELD_MINIMUM = 0.95
PRECISION_MINIMUM = 0.90
# Unknown is a semantic category, not simply every needs-review confidence.
# An explicit mapping/restricted state still is a configured risk to be reviewed.
UNKNOWN_RULES = frozenset({"PARSE-INCOMPLETE", "PARSE-NUMBER",
                          "MGMT-VTY-UNKNOWN", "MGMT-VTY-SOURCE", "ACL-UNBOUND",
                          "OSPF-AUTH-REVIEW"})
INTERFACE_FIELDS = ("name", "shutdown", "description", "mode", "access_vlan", "native_vlan",
                    "allowed_vlan_ranges", "addresses", "vrf", "acl_bindings", "nat_role",
                    "stp_enabled", "stp_edge", "bpdu_guard", "bpdu_filter", "protected")
ACL_RULE_FIELDS = ("sequence", "action", "protocol", "source", "destination", "source_port",
                   "destination_port", "complete")
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


def _take(value, names):
    return {name: value[name] for name in names if name in value}


def supported_projection(inventory):
    """Freeze semantic coverage, retain all observed objects within that scope."""
    result = {}
    if "hostname" in inventory:
        result["hostname"] = inventory["hostname"]
    for collection, fields in (("interfaces", INTERFACE_FIELDS), ("vlans", ("name",))):
        if collection in inventory:
            result[collection] = {str(key): _take(value, fields) for key, value in inventory[collection].items()}
    for collection, fields in (("routes", ROUTE_FIELDS), ("nat", NAT_FIELDS), ("management_lines", MANAGEMENT_FIELDS)):
        if collection in inventory:
            result[collection] = [_take(value, fields) for value in inventory[collection]]
    if "acls" in inventory:
        result["acls"] = {}
        for name, acl in inventory["acls"].items():
            value = _take(acl, ("name", "kind", "ordered"))
            if "rules" in acl:
                value["rules"] = [_take(rule, ACL_RULE_FIELDS) for rule in acl["rules"]]
            result["acls"][str(name)] = value
    if "nat_pools" in inventory:
        # Pool address ranges are not yet modeled. Existence/name is supported.
        result["nat_pools"] = {str(name): {} for name in inventory["nat_pools"]}
    if "stp" in inventory:
        result["stp"] = _take(inventory["stp"], STP_FIELDS)
        if "vlan_enabled" in result["stp"]:
            result["stp"]["vlan_enabled"] = {str(k): v for k, v in result["stp"]["vlan_enabled"].items()}
    return result


def _flatten(value, path=()):
    if isinstance(value, dict) and value:
        result = {}
        for key, child in value.items():
            result.update(_flatten(child, path + (str(key),)))
        return result
    if isinstance(value, list) and value and any(isinstance(item, dict) for item in value):
        result = {}
        for index, child in enumerate(value):
            result.update(_flatten(child, path + (str(index),)))
        return result
    # Lists of scalar values/ranges and empty containers are semantic values.
    return {path: value}


def _same_value(expected, actual):
    if type(expected) is not type(actual):
        return False
    if isinstance(expected, list):
        return len(expected) == len(actual) and all(_same_value(a, b) for a, b in zip(expected, actual))
    return expected == actual


def score_fields(expected, actual):
    expected_fields, actual_fields = _flatten(expected), _flatten(actual)
    keys = expected_fields.keys() | actual_fields.keys()
    correct, mismatches = 0, []
    for key in sorted(keys):
        if key not in actual_fields:
            kind = "missing"
        elif key not in expected_fields:
            kind = "extra"
        elif _same_value(expected_fields[key], actual_fields[key]):
            correct += 1
            continue
        else:
            kind = "wrong-value"
        mismatches.append({"path": "/" + "/".join(key), "module": key[0] if key else "root",
                           "kind": kind, "expected": expected_fields.get(key), "actual": actual_fields.get(key)})
    return {"correct": correct, "total": len(keys), "accuracy": correct / len(keys) if keys else 1.0,
            "mismatches": mismatches}


def _finding_keys(file, findings):
    return {(file, finding["rule_id"], obj)
            for finding in findings for obj in (finding.get("affected_objects") or ["device"])}


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def score_findings(file, expected, actual):
    gold, observed = _finding_keys(file, expected), _finding_keys(file, actual)
    tp, fp, fn = gold & observed, observed - gold, gold - observed
    return {"tp": len(tp), "fp": len(fp), "fn": len(fn),
            "precision": _ratio(len(tp), len(tp) + len(fp)),
            "recall": _ratio(len(tp), len(tp) + len(fn)),
            "false_positives": [list(v) for v in sorted(fp)],
            "false_negatives": [list(v) for v in sorted(fn)]}


def split_conclusions(findings):
    return ([f for f in findings if f["rule_id"] not in UNKNOWN_RULES],
            [f for f in findings if f["rule_id"] in UNKNOWN_RULES])


def _rule_module(rule_id):
    return {"MGMT": "management_lines", "ACL": "acls", "VLAN": "vlans", "IF": "interfaces",
            "ROUTE": "routes", "NAT": "nat", "STP": "stp", "OSPF": "ospf", "PARSE": "coverage"}.get(
                rule_id.split("-", 1)[0], "other")


def module_findings(file, expected, actual):
    domains = {_rule_module(f["rule_id"]) for f in expected + actual}
    return {domain: score_findings(file, [f for f in expected if _rule_module(f["rule_id"]) == domain],
                                  [f for f in actual if _rule_module(f["rule_id"]) == domain])
            for domain in sorted(domains)}


def aggregate_fields(scores):
    correct, total = sum(s["correct"] for s in scores), sum(s["total"] for s in scores)
    return {"correct": correct, "total": total, "accuracy": correct / total if total else 1.0}


def aggregate_findings(scores):
    result = {key: sum(s[key] for s in scores) for key in ("tp", "fp", "fn")}
    result["precision"] = _ratio(result["tp"], result["tp"] + result["fp"])
    result["recall"] = _ratio(result["tp"], result["tp"] + result["fn"])
    return result


def passes_gate(field_accuracy, precision):
    return field_accuracy >= FIELD_MINIMUM and precision is not None and precision >= PRECISION_MINIMUM


def run_acceptance(dataset):
    # Import only for measurement, never for expected-data creation.
    sys.path.insert(0, str(ROOT))
    from netaudit import audit, parse_config

    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    if manifest["frozen_supported_paths"] != SUPPORTED_PATHS:
        raise ValueError("Frozen supported-field schema differs; review a versioned dataset change")
    if set(manifest["unknown_rule_ids"]) != UNKNOWN_RULES:
        raise ValueError("Frozen unknown semantics differ")
    cases, vendors, modules = [], defaultdict(list), defaultdict(list)
    module_risks, module_unknown = defaultdict(list), defaultdict(list)
    positive_rules, negative_rules = Counter(), Counter()
    for entry in manifest["cases"]:
        for name, checksum in entry["sha256"].items():
            if hashlib.sha256((dataset / name).read_bytes()).hexdigest() != checksum:
                raise ValueError("Frozen dataset hash mismatch: " + name)
        text = (dataset / entry["config"]).read_text(encoding="utf-8")
        expected = json.loads((dataset / entry["expected"]).read_text(encoding="utf-8"))
        config = parse_config(text, entry["vendor"])
        result = audit(config)
        actual = supported_projection(result["inventory"])
        fields = score_fields(expected["inventory"], actual)
        risks, unknown = split_conclusions(result["findings"])
        findings = score_findings(entry["config"], expected["risk_findings"], risks)
        unknown_score = score_findings(entry["config"], expected["unknown_findings"], unknown)
        warning_misses = [command for command in expected.get("unknown_commands", [])
                          if not any(command in warning.get("text", "") for warning in config.warnings)]
        case = {"id": entry["id"], "file": entry["config"], "vendor": entry["vendor"],
                "fields": fields, "findings": findings, "unknown": unknown_score,
                "unknown_warning_misses": warning_misses,
                "warnings": config.warnings,
                "negative_assertion_failures": sorted(set(expected["must_not_report"]) & {f["rule_id"] for f in result["findings"]})}
        cases.append(case)
        vendors[entry["vendor"]].append(case)
        for module in expected["inventory"].keys() | actual.keys():
            modules[module].append(score_fields({module: expected["inventory"][module]} if module in expected["inventory"] else {},
                                               {module: actual[module]} if module in actual else {}))
        for domain, values in module_findings(entry["config"], expected["risk_findings"], risks).items():
            module_risks[domain].append(values)
        for domain, values in module_findings(entry["config"], expected["unknown_findings"], unknown).items():
            module_unknown[domain].append(values)
        positive_rules.update(set(f["rule_id"] for f in expected["risk_findings"]))
        negative_rules.update(set(expected["must_not_report"]))
    fields = aggregate_fields([c["fields"] for c in cases])
    findings = aggregate_findings([c["findings"] for c in cases])
    unknown = aggregate_findings([c["unknown"] for c in cases])
    counts = {vendor: len(values) for vendor, values in vendors.items()}
    paired_rules = sorted(positive_rules.keys() & negative_rules.keys())
    integrity = (len(cases) >= 50 and counts.get("cisco", 0) >= 18 and counts.get("huawei", 0) >= 16
                 and counts.get("h3c", 0) >= 16 and len(paired_rules) >= 20)
    negative_errors = sum(len(c["negative_assertion_failures"]) for c in cases)
    warning_errors = sum(len(c["unknown_warning_misses"]) for c in cases)
    return {"schema_version": "1.0", "dataset": manifest["dataset_id"], "scope": manifest["scope"],
            "gold_provenance": manifest["gold_provenance"],
            "supported_paths": SUPPORTED_PATHS, "unknown_rule_ids": sorted(UNKNOWN_RULES),
            "thresholds": {"field_accuracy": FIELD_MINIMUM, "risk_precision": PRECISION_MINIMUM},
            "coverage": {"case_count": len(cases), "vendor_counts": counts, "paired_risk_rules": paired_rules,
                         "paired_risk_rule_count": len(paired_rules), "integrity_passed": integrity},
            "fields": fields, "findings": findings, "unknown": unknown,
            "by_vendor": {vendor: {"fields": aggregate_fields([c["fields"] for c in values]),
                                   "findings": aggregate_findings([c["findings"] for c in values]),
                                   "unknown": aggregate_findings([c["unknown"] for c in values])}
                          for vendor, values in sorted(vendors.items())},
            "by_module": {name: {"fields": aggregate_fields(modules[name]) if name in modules else None,
                                 "findings": aggregate_findings(module_risks[name]),
                                 "unknown": aggregate_findings(module_unknown[name])}
                          for name in sorted(modules.keys() | module_risks.keys() | module_unknown.keys())},
            "negative_assertion_failures": negative_errors, "unknown_warning_misses": warning_errors,
            "passed": integrity and passes_gate(fields["accuracy"], findings["precision"])
                      and negative_errors == 0 and warning_errors == 0,
            "cases": cases}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "benchmarks")
    parser.add_argument("--out", type=Path, default=ROOT / "reports" / "acceptance.json")
    args = parser.parse_args(argv)
    try:
        report = run_acceptance(args.dataset.resolve())
    except (OSError, ValueError, KeyError) as exc:
        print("Acceptance dataset error: " + str(exc), file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    precision, recall = report["findings"]["precision"], report["findings"]["recall"]
    precision_text = f"{precision:.2%}" if precision is not None else "N/A"
    recall_text = f"{recall:.2%}" if recall is not None else "N/A"
    print(f"cases={report['coverage']['case_count']} fields={report['fields']['accuracy']:.2%} "
          f"precision={precision_text} recall={recall_text} "
          f"TP={report['findings']['tp']} FP={report['findings']['fp']} FN={report['findings']['fn']} "
          f"passed={report['passed']} out={args.out}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
