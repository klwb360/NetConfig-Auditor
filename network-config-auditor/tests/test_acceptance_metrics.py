"""Acceptance must expose wrong values, omissions, extras and wrong objects."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


TOOL = Path(__file__).resolve().parents[1] / "tools" / "benchmark_acceptance.py"


class AcceptanceMetricTests(unittest.TestCase):
    def tool(self):
        self.assertTrue(TOOL.is_file(), "Independent acceptance scorer has not been implemented")
        spec = importlib.util.spec_from_file_location("benchmark_acceptance", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_wrong_value_missing_field_and_extra_field_use_union(self):
        result = self.tool().score_fields(
            {"hostname": "R1", "interfaces": {"Gi0/1": {"mode": "access", "access_vlan": 10}}},
            {"hostname": "R1", "interfaces": {"Gi0/1": {"mode": "trunk", "native_vlan": 20}}},
        )
        self.assertEqual(result["correct"], 1)
        self.assertEqual(result["total"], 4)
        self.assertEqual(result["accuracy"], 0.25)
        self.assertEqual({v["kind"] for v in result["mismatches"]}, {"wrong-value", "missing", "extra"})

    def test_extra_object_is_not_hidden_by_expected_keys(self):
        result = self.tool().score_fields({"interfaces": {}}, {"interfaces": {"Gi0/9": {"mode": "access"}}})
        self.assertEqual(result["correct"], 0)
        self.assertGreater(result["total"], 0)
        self.assertTrue(any(v["kind"] == "extra" for v in result["mismatches"]))

    def test_list_values_and_types_are_compared_exactly(self):
        result = self.tool().score_fields({"addresses": ["10.1.0.1/24"], "vid": 10},
                                          {"addresses": ["10.1.0.2/24"], "vid": "10"})
        self.assertEqual(result["accuracy"], 0)

    def test_range_list_does_not_treat_boolean_as_vlan_integer(self):
        result = self.tool().score_fields({"allowed_vlan_ranges": [[1, 20]]},
                                          {"allowed_vlan_ranges": [[True, 20]]})
        self.assertEqual(result["accuracy"], 0)

    def test_findings_expose_false_positive_and_false_negative(self):
        result = self.tool().score_findings("r.cfg", [
            {"rule_id": "VLAN-UNDEFINED", "affected_objects": ["Gi0/1", "Gi0/2"]},
        ], [
            {"rule_id": "VLAN-UNDEFINED", "affected_objects": ["Gi0/1", "Gi0/9"]},
            {"rule_id": "MGMT-HTTP", "affected_objects": ["device"]},
        ])
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 2, 1))
        self.assertAlmostEqual(result["precision"], 1 / 3)
        self.assertEqual(result["recall"], 0.5)

    def test_duplicate_grouped_objects_do_not_inflate_metrics(self):
        finding = {"rule_id": "MGMT-VTY-TELNET", "affected_objects": ["vty 0 4", "vty 0 4"]}
        result = self.tool().score_findings("r.cfg", [finding], [finding, finding])
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 0, 0))

    def test_unknown_findings_are_separate_from_risk_precision(self):
        module = self.tool()
        findings = [{"rule_id": "PARSE-INCOMPLETE", "affected_objects": []},
                    {"rule_id": "MGMT-HTTP", "affected_objects": ["配置行 2"]}]
        risks, unknown = module.split_conclusions(findings)
        self.assertEqual([f["rule_id"] for f in risks], ["MGMT-HTTP"])
        self.assertEqual([f["rule_id"] for f in unknown], ["PARSE-INCOMPLETE"])

    def test_micro_average_weights_by_supported_field_count(self):
        result = self.tool().aggregate_fields([
            {"correct": 1, "total": 1}, {"correct": 0, "total": 9}])
        self.assertEqual(result, {"correct": 1, "total": 10, "accuracy": 0.1})

    def test_gate_preserves_required_thresholds(self):
        module = self.tool()
        self.assertFalse(module.passes_gate(0.9499, 1.0))
        self.assertFalse(module.passes_gate(1.0, 0.8999))
        self.assertTrue(module.passes_gate(0.95, 0.90))

    def test_supported_projection_freezes_scope_but_keeps_extra_objects(self):
        projected = self.tool().supported_projection({
            "hostname": "R", "interfaces": {"Gi0/9": {"mode": "trunk", "complete": True}},
            "line_count": 100, "routing_processes": [{"router_id": "1.1.1.1"}],
        })
        self.assertEqual(projected, {"hostname": "R", "interfaces": {"Gi0/9": {"mode": "trunk"}}})

    def test_module_risk_metrics_use_rule_domain_and_object_identity(self):
        module = self.tool()
        self.assertTrue(callable(getattr(module, "module_findings", None)), "Per-module risk scorer is missing")
        result = module.module_findings("r.cfg", [
            {"rule_id": "MGMT-HTTP", "affected_objects": ["配置行 2"]},
            {"rule_id": "ACL-UNDEFINED", "affected_objects": ["Gi0/1"]},
        ], [
            {"rule_id": "MGMT-HTTP", "affected_objects": ["配置行 2"]},
            {"rule_id": "ACL-UNDEFINED", "affected_objects": ["Gi0/2"]},
        ])
        self.assertEqual(result["management_lines"]["tp"], 1)
        self.assertEqual((result["acls"]["tp"], result["acls"]["fp"], result["acls"]["fn"]), (0, 1, 1))

    def test_frozen_dataset_has_required_vendor_counts_and_positive_negative_pairs(self):
        dataset = TOOL.parent.parent / "benchmarks"
        manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
        cases = manifest["cases"]
        self.assertEqual(len(cases), 50)
        self.assertEqual({vendor: sum(c["vendor"] == vendor for c in cases) for vendor in ("cisco", "huawei", "h3c")},
                         {"cisco": 18, "huawei": 16, "h3c": 16})
        positive = {c["focus_rule"] for c in cases if c["polarity"] == "risk"}
        negative = {c["focus_rule"] for c in cases if c["polarity"] == "control"}
        self.assertGreaterEqual(len(positive & negative), 20)
        self.assertEqual(manifest["frozen_supported_paths"], self.tool().SUPPORTED_PATHS)

    def test_hash_mismatch_rejects_data_before_measurement(self):
        module = self.tool()
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory)
            (dataset / "bad.cfg").write_text("hostname CHANGED", encoding="utf-8")
            manifest = {"frozen_supported_paths": module.SUPPORTED_PATHS,
                        "unknown_rule_ids": sorted(module.UNKNOWN_RULES),
                        "cases": [{"sha256": {"bad.cfg": "0" * 64}}]}
            (dataset / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                module.run_acceptance(dataset)


if __name__ == "__main__":
    unittest.main()
