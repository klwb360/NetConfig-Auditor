"""Synthetic NVD fixtures exercise matching logic, not product advisories."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from netaudit.intelligence import (
    KEV_URL, MAX_INTELLIGENCE_BYTES, analyze_intelligence, fetch_official_kev,
    load_default_kev, load_intelligence_file, normalize_kev, normalize_nvd,
)
from netaudit.model import Config

CVE = "CVE-2023-20198"
CPE = "cpe:2.3:o:cisco:ios_xe:16.12.1:*:*:*:*:*:*:*"
CRITERIA = "cpe:2.3:o:cisco:ios_xe:*:*:*:*:*:*:*:*"


def kev():
    return {"catalogVersion": "2026.10.02", "dateReleased": "2026-10-02T00:00:00Z", "count": 1, "vulnerabilities": [{"cveID": CVE, "dateAdded": "2023-10-16", "dueDate": "2023-10-20", "vulnerabilityName": "Synthetic fixture", "requiredAction": "Apply vendor instructions."}]}


def nvd(criteria=CRITERIA, **bounds):
    return {"format": "NVD_CVE", "version": "2.0", "timestamp": "2026-10-02T00:00:00.000", "vulnerabilities": [{"cve": {"id": CVE, "descriptions": [{"lang": "en", "value": "Synthetic matching fixture; not a product advisory."}], "metrics": {"cvssMetricV31": [{"cvssData": {"baseSeverity": "CRITICAL"}}]}, "configurations": [{"nodes": [{"operator": "OR", "negate": False, "cpeMatch": [{"vulnerable": True, "criteria": criteria, **bounds}]}]}]}}]}


def analyze(asset=None, document=None, catalog=None):
    return analyze_intelligence(Config("cisco", "explicit", "test"), {"cpe": CPE} if asset is None else asset, kev() if catalog is None else catalog, nvd() if document is None else document)


class IntelligenceTests(unittest.TestCase):
    def test_exact_cpe_version_and_kev_are_separate_facts(self):
        result = analyze(document=nvd(CPE))
        self.assertEqual(result["status"], "matched")
        item = result["matches"][0]
        self.assertEqual(item["confidence"], "cpe-version-match")
        self.assertTrue(item["known_exploited"])
        self.assertEqual(item["kev"]["requiredAction"], "Apply vendor instructions.")
        self.assertEqual(item["severity"], "critical")
        self.assertTrue(any("已被攻陷" in text for text in result["limitations"]))

    def test_range_inclusive_and_exclusive_boundaries(self):
        document = nvd(versionStartIncluding="16.12.1", versionEndExcluding="17.0")
        self.assertEqual(len(analyze(document=document)["matches"]), 1)
        self.assertEqual(analyze({"cpe": CPE.replace("16.12.1", "17.0")}, document)["status"], "no-matches")
        self.assertEqual(analyze({"cpe": CPE.replace("16.12.1", "16.12")}, document)["status"], "no-matches")

    def test_numeric_comparison_pads_components(self):
        result = analyze({"cpe": CPE.replace("16.12.1", "16.12.0.0")}, nvd(versionStartIncluding="16.12", versionEndIncluding="16.12.0"))
        self.assertEqual(len(result["matches"]), 1)

    def test_opaque_vendor_version_is_not_numerically_guessed(self):
        result = analyze({"cpe": CPE.replace("16.12.1", "16.12.1a")}, nvd(versionEndExcluding="17.0"))
        self.assertEqual(result["status"], "needs-review")
        self.assertEqual(result["matches"], [])

    def test_unknown_version_never_confirms_all_versions_cpe(self):
        result = analyze({"cpe": CRITERIA})
        self.assertEqual(result["status"], "needs-review")
        self.assertEqual(result["matches"], [])

    def test_brand_same_but_product_different_is_not_a_match(self):
        result = analyze({"cpe": CPE.replace("ios_xe", "adaptive_security_appliance")})
        self.assertEqual(result["matches"], [])
        self.assertEqual(result["candidates"], [])
        self.assertIn("不等同于", result["message"])

    def test_wildcard_products_never_become_exact_product_matches(self):
        for component in ("vendor", "product"):
            for unknown in ("*", "-", "foo?", "foo*"):
                replacement = "cisco" if component == "vendor" else "ios_xe"
                asset = {"cpe": CPE.replace(replacement, unknown)}
                document = nvd(CRITERIA.replace(replacement, unknown))
                with self.subTest(component=component, unknown=unknown):
                    result = analyze(asset, document)
                    self.assertEqual(result["matches"], [])
                    self.assertEqual(result["status"], "needs-review")

    def test_config_vendor_never_guesses_cpe(self):
        result = analyze({})
        self.assertEqual(result["status"], "not-configured")
        self.assertEqual(result["matches"], [])

    def test_explicit_cve_without_asset_is_only_user_candidate(self):
        result = analyze({"cve_ids": [CVE]})
        self.assertEqual(result["matches"], [])
        self.assertEqual(result["candidates"][0]["confidence"], "user-provided-candidate")
        self.assertTrue(result["candidates"][0]["known_exploited"])

    def test_user_candidate_with_wrong_product_remains_unconfirmed(self):
        result = analyze({"cpe": CPE.replace("ios_xe", "other"), "cve_ids": [CVE]})
        self.assertEqual(result["matches"], [])
        self.assertIn("不匹配", result["candidates"][0]["match_basis"])

    def test_candidate_absent_from_nvd_still_links_kev_without_claiming_applicability(self):
        result = analyze_intelligence(None, {"cve_ids": [CVE]}, kev(), {"vulnerabilities": []})
        self.assertEqual(result["matches"], [])
        self.assertTrue(result["candidates"][0]["known_exploited"])

    def test_and_and_negated_conditions_require_review(self):
        for update in ({"operator": "AND"}, {"negate": True}, {"operator": "XOR"}):
            document = nvd()
            document["vulnerabilities"][0]["cve"]["configurations"][0]["nodes"][0].update(update)
            with self.subTest(update=update):
                result = analyze(document=document)
                self.assertEqual(result["status"], "needs-review")
                self.assertEqual(result["matches"], [])

    def test_non_vulnerable_environment_condition_does_not_confirm_device(self):
        document = nvd()
        document["vulnerabilities"][0]["cve"]["configurations"][0]["nodes"][0]["cpeMatch"][0]["vulnerable"] = False
        self.assertEqual(analyze(document=document)["status"], "needs-review")

    def test_missing_condition_operator_is_not_assumed_true(self):
        document = nvd()
        del document["vulnerabilities"][0]["cve"]["configurations"][0]["nodes"][0]["operator"]
        self.assertEqual(analyze(document=document)["status"], "needs-review")

    def test_unknown_condition_or_version_field_is_preserved_for_review(self):
        for scope in ("node", "match"):
            document = nvd()
            node = document["vulnerabilities"][0]["cve"]["configurations"][0]["nodes"][0]
            if scope == "node":
                node["unsupportedEnvironmentConstraint"] = "other platform required"
            else:
                node["cpeMatch"][0]["versionEndUnsupported"] = "15.0"
            with self.subTest(scope=scope):
                result = analyze(document=document)
                self.assertEqual(result["matches"], [])
                self.assertEqual(result["status"], "needs-review")

    def test_concrete_platform_attribute_unknown_in_asset_requires_review(self):
        result = analyze(document=nvd(CRITERIA.replace("ios_xe:*:*:*:*:*:*:*:*", "ios_xe:*:*:*:*:*:x64:*:*")))
        self.assertEqual(result["matches"], [])
        self.assertEqual(result["status"], "needs-review")

    def test_rejected_nvd_record_is_not_an_active_vulnerability(self):
        document = nvd()
        document["vulnerabilities"][0]["cve"]["vulnStatus"] = "Rejected"
        self.assertEqual(analyze(document=document)["matches"], [])
        self.assertEqual(analyze({"cpe": CPE, "cve_ids": [CVE]}, document)["status"], "needs-review")

    def test_malformed_documents_and_duplicates_are_rejected(self):
        cases = [(normalize_kev, {"vulnerabilities": [{}]}), (normalize_kev, {**kev(), "count": 2}), (normalize_nvd, {"version": "1.1", "vulnerabilities": []}), (normalize_nvd, {"vulnerabilities": [{"cve": {"id": "bad"}}]})]
        duplicated = nvd()
        duplicated["vulnerabilities"] *= 2
        cases.append((normalize_nvd, duplicated))
        wrong_bool = nvd()
        wrong_bool["vulnerabilities"][0]["cve"]["configurations"][0]["nodes"][0]["negate"] = "false"
        cases.append((normalize_nvd, wrong_bool))
        invalid_cpe = nvd("cpe:2.3:z:cisco:ios_xe:*:*:*:*:*:*:*:*")
        cases.append((normalize_nvd, invalid_cpe))
        for function, value in cases:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    function(value)

    def test_source_age_and_missing_date_are_explicit(self):
        old = kev()
        old["dateReleased"] = "2020-01-01T00:00:00Z"
        result = analyze(catalog=old)
        self.assertTrue(result["sources"][0]["stale"])
        self.assertGreater(result["sources"][0]["age_days"], 30)
        unknown = nvd()
        unknown.pop("timestamp")
        self.assertTrue(analyze(document=unknown)["sources"][1]["stale"])

    def test_user_metadata_cannot_self_authenticate_source(self):
        catalog = kev()
        catalog["_netaudit"] = {"origin": "official-download", "sha256": "fake"}
        source = analyze(catalog=catalog)["sources"][0]
        self.assertEqual(source["origin"], "caller-provided-unverified")
        self.assertEqual(source["sha256"], "")

    def test_bundled_official_snapshot_has_verified_hash_license_and_real_kev(self):
        with patch("netaudit.intelligence.urllib.request.urlopen", side_effect=AssertionError("network prohibited")):
            document = load_default_kev()
            result = analyze_intelligence(None, {"cve_ids": [CVE]})
        self.assertEqual(document["count"], 1733)
        self.assertEqual(document["catalogVersion"], "2026.10.02")
        self.assertEqual(document.metadata["sha256"], "d2c8c6cb23291b46ff2b086197641a6b1fa35e6b746bba714cc280a1778f9e48")
        self.assertEqual(document.metadata["license"], "CC0-1.0")
        self.assertTrue(result["candidates"][0]["known_exploited"])
        self.assertEqual(result["sources"][0]["origin"], "bundled-official-snapshot")

    def test_loader_hashes_actual_bytes_and_preserves_import_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "情报 data.json"
            data = json.dumps(nvd()).encode()
            path.write_bytes(data)
            document = load_intelligence_file(path, "nvd")
            source = analyze(document=document)["sources"][1]
            self.assertEqual(source["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(source["origin"], "user-import")
            path.write_bytes(b"{}")
            with self.assertRaises(ValueError):
                load_intelligence_file(path, "nvd")

    def test_oversized_import_is_rejected_before_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oversized.json"
            with path.open("wb") as stream:
                stream.truncate(MAX_INTELLIGENCE_BYTES + 1)
            with self.assertRaisesRegex(ValueError, "16 MiB"):
                load_intelligence_file(path, "kev")

    def test_invalid_asset_and_identifiers_are_rejected(self):
        for asset in ({"cpe": "cisco ios"}, {"cpe": "cpe:2.3:z:cisco:ios_xe:16:*:*:*:*:*:*:*"}, {"cve_ids": ["not-a-cve"]}, {"cve_ids": CVE}):
            with self.subTest(asset=asset), self.assertRaises(ValueError):
                analyze(asset)

    def test_in_memory_web_document_cannot_bypass_size_limit(self):
        document = nvd()
        document["vulnerabilities"][0]["cve"]["descriptions"][0]["value"] = "x" * 1000
        with patch("netaudit.intelligence.MAX_INTELLIGENCE_BYTES", 900), self.assertRaisesRegex(ValueError, "16 MiB"):
            normalize_nvd(document)

    def test_json_duplicate_keys_and_nonstandard_numbers_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            for data in (b'{"vulnerabilities":[],"vulnerabilities":[]}', b'{"vulnerabilities":[],"extra":NaN}'):
                with self.subTest(data=data):
                    path.write_bytes(data)
                    with self.assertRaises(ValueError):
                        load_intelligence_file(path, "nvd")

    def test_explicit_fetch_writes_only_chosen_path_atomically(self):
        data = json.dumps(kev()).encode()
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def geturl(self): return KEV_URL
            def read(self, size): return data[:size]
        with tempfile.TemporaryDirectory() as directory, patch("netaudit.intelligence.urllib.request.urlopen", return_value=Response()) as request:
            path = Path(directory) / "缓存 data" / "kev.json"
            document = fetch_official_kev(path)
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(list(path.parent.iterdir()), [path])
            self.assertEqual(document.metadata["origin"], "official-download")
            self.assertEqual(request.call_count, 1)
            self.assertEqual(request.call_args.args[0].full_url, KEV_URL)


if __name__ == "__main__":
    unittest.main()
