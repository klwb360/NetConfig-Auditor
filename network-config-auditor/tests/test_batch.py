from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class BatchAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = self.root / "inputs"
        self.outputs = self.root / "outputs"
        self.inputs.mkdir()

    def audit(self, **options):
        from netaudit.batch import audit_directory
        return audit_directory(self.inputs, self.outputs, **options)

    def write(self, name, data=b"hostname LAB\nip http server\n"):
        path = self.inputs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_fifty_files_and_all_report_artifacts(self):
        for index in range(50):
            self.write(f"device-{index:02}.cfg")
        result = self.audit()
        self.assertEqual(result["schema_version"], "1.0")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["summary"]["total"], 50)
        self.assertEqual(result["summary"]["succeeded"], 50)
        self.assertEqual(result["summary"]["failed"], 0)
        self.assertEqual(result["summary"]["severity"]["high"], 50)
        self.assertEqual(len(list(self.outputs.glob("*.json"))), 51)
        self.assertEqual(len(list(self.outputs.glob("*.html"))), 51)
        self.assertEqual(json.loads((self.outputs / "batch.json").read_text(encoding="utf-8")), result)

    def test_failure_isolated_and_does_not_leak_config(self):
        self.write("a-bad.cfg", b"hostname SECRET_CONFIG\x00password TOP_SECRET")
        self.write("b-good.cfg")
        result = self.audit(fail_on="high")
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(result["summary"]["succeeded"], 1)
        self.assertEqual(result["summary"]["failed"], 1)
        bad, good = result["devices"]
        self.assertEqual(bad["status"], "error")
        self.assertIsNone(bad["report"])
        self.assertEqual(good["status"], "ok")
        self.assertNotIn("SECRET_CONFIG", json.dumps(bad))
        self.assertNotIn("TOP_SECRET", json.dumps(bad))

    def test_source_hash_encoding_and_evidence_line_numbers(self):
        raw = "hostname LAB\r\n! 中文说明\r\nip http server\r\n".encode("gb18030")
        self.write("nested/设备.cfg", raw)
        device = self.audit(recursive=True)["devices"][0]
        self.assertEqual(device["source"], {"path": "nested/设备.cfg", "sha256": hashlib.sha256(raw).hexdigest(), "encoding": "gb18030"})
        self.assertEqual(device["report"]["schema_version"], "1.1")
        finding = next(f for f in device["report"]["findings"] if f["rule_id"] == "MGMT-HTTP")
        self.assertEqual(finding["evidence"][0]["line"], 3)

    def test_scan_extensions_recursion_and_stable_duplicate_names(self):
        for name in ("one.cfg", "two.CONF", "three.config", "four.txt", "running-config", "nested/one.cfg"):
            self.write(name)
        for name in ("report.json", "script.py", "archive.zip"):
            self.write(name)
        first = self.audit()
        self.assertEqual(first["summary"]["total"], 5)
        recursive = self.audit(recursive=True)
        self.assertEqual(recursive["summary"]["total"], 6)
        names = [d["outputs"]["json"] for d in recursive["devices"]]
        self.assertEqual(len(set(names)), 6)
        self.assertEqual(names, [d["outputs"]["json"] for d in self.audit(recursive=True)["devices"]])
        self.assertTrue(all(Path(name).name == name and "/" not in name and "\\" not in name for name in names))

    def test_html_escapes_hostname_filename_and_error_text(self):
        self.write("host&evil.cfg", b"hostname <script>alert(1)</script>\nip http server\n")
        self.write("bad&file.cfg", b"bad\x00")
        self.audit()
        aggregate = (self.outputs / "batch.html").read_text(encoding="utf-8")
        self.assertIn("host&amp;evil.cfg", aggregate)
        self.assertIn("bad&amp;file.cfg", aggregate)
        for path in self.outputs.glob("*.html"):
            self.assertNotIn("<script>", path.read_text(encoding="utf-8"))

    def test_input_output_overlap_is_rejected_without_mutation(self):
        source = self.write("original.cfg")
        from netaudit.batch import audit_directory
        for output in (self.inputs, self.inputs / "reports"):
            with self.subTest(output=output):
                result = audit_directory(self.inputs, output)
                self.assertEqual(result["exit_code"], 2)
                self.assertEqual(result["summary"]["total"], 0)
        self.assertEqual(source.read_bytes(), b"hostname LAB\nip http server\n")
        self.assertFalse((self.inputs / "reports").exists())

    def test_empty_missing_and_non_directory_input(self):
        self.assertEqual(self.audit()["exit_code"], 2)
        from netaudit.batch import audit_directory
        missing = self.root / "missing"
        self.assertEqual(audit_directory(missing, self.outputs)["exit_code"], 2)
        file_input = self.write("file.cfg")
        self.assertEqual(audit_directory(file_input, self.outputs)["exit_code"], 2)

    def test_strict_takes_priority_over_high_threshold(self):
        self.write("unmodeled.cfg", b"hostname LAB\nip http server\nunknown command\n")
        result = self.audit(strict=True, fail_on="high")
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(result["summary"]["review_required"], 1)
        self.assertEqual(result["devices"][0]["status"], "ok")
        self.assertEqual(self.audit(fail_on="high")["exit_code"], 1)

    def test_no_findings_is_not_labeled_safe(self):
        self.write("minimal.cfg", b"hostname LAB\n")
        result = self.audit()
        self.assertEqual(result["summary"]["severity"]["high"], 0)
        output = (self.outputs / "batch.html").read_text(encoding="utf-8")
        self.assertIn("无告警不表示安全", output)
        self.assertNotIn("审计安全", output)

    def test_size_limit_and_explicit_encoding_failure_continue(self):
        self.write("a-large.cfg", b"x" * (2 * 1024 * 1024 + 1))
        self.write("b-encoded.cfg", "hostname LAB\n! 中文说明\n".encode("gbk"))
        self.write("c-good.cfg")
        result = self.audit(encoding="utf-8")
        self.assertEqual(result["summary"]["failed"], 2)
        self.assertEqual(result["summary"]["succeeded"], 1)
        self.assertEqual(result["exit_code"], 2)

    def test_errors_from_audit_do_not_expose_configuration(self):
        self.write("a-bad.cfg")
        self.write("b-good.cfg")
        from netaudit.pipeline import audit_configuration
        calls = iter((True, False))
        def audit(text, vendor):
            if next(calls):
                raise ValueError("SECRET_CONFIGURATION <script>")
            return audit_configuration(text, vendor)
        with patch("netaudit.batch.audit_configuration", side_effect=audit):
            result = self.audit()
        self.assertEqual(result["summary"]["succeeded"], 1)
        self.assertNotIn("SECRET_CONFIGURATION", json.dumps(result))

    def test_unexpected_audit_failure_is_isolated(self):
        self.write("a-bad.cfg")
        self.write("b-good.cfg")
        from netaudit.pipeline import audit_configuration
        calls = iter((True, False))
        def audit(text, vendor):
            if next(calls):
                raise IndexError("SECRET_CONFIGURATION")
            return audit_configuration(text, vendor)
        with patch("netaudit.batch.audit_configuration", side_effect=audit):
            result = self.audit()
        self.assertEqual(result["summary"]["succeeded"], 1)
        self.assertEqual(result["summary"]["failed"], 1)
        self.assertNotIn("SECRET_CONFIGURATION", json.dumps(result))

    def test_output_preflight_rejects_symlink_before_any_artifact_write(self):
        self.write("source.cfg")
        self.outputs.mkdir()
        target = self.root / "protected.txt"
        target.write_text("protected", encoding="utf-8")
        linked = self.outputs / "batch.html"
        try:
            linked.symlink_to(target)
        except OSError:
            self.skipTest("platform does not allow test symlink creation")
        self.assertEqual(self.audit()["exit_code"], 2)
        self.assertEqual(target.read_text(encoding="utf-8"), "protected")
        self.assertEqual(sorted(path.name for path in self.outputs.iterdir()), ["batch.html"])

    def test_html_output_failure_is_recorded_in_json_summary(self):
        self.write("source.cfg")
        from netaudit.batch import _write_atomic
        def write(path, content):
            if path.name == "batch.html":
                raise PermissionError("SECRET_CONFIG")
            return _write_atomic(path, content)
        with patch("netaudit.batch._write_atomic", side_effect=write):
            result = self.audit()
        self.assertEqual(result["exit_code"], 2)
        self.assertNotIn("SECRET_CONFIG", json.dumps(result))
        self.assertTrue((self.outputs / "batch.json").exists())
        self.assertEqual(json.loads((self.outputs / "batch.json").read_text(encoding="utf-8")), result)

    def test_input_and_output_symlink_directories_are_rejected(self):
        self.write("source.cfg")
        alias_input = self.root / "input-link"
        alias_output = self.root / "output-link"
        self.outputs.mkdir()
        try:
            alias_input.symlink_to(self.inputs, target_is_directory=True)
            alias_output.symlink_to(self.outputs, target_is_directory=True)
        except OSError:
            self.skipTest("platform does not allow test symlink creation")
        from netaudit.batch import audit_directory
        self.assertEqual(audit_directory(alias_input, self.outputs)["exit_code"], 2)
        self.assertEqual(audit_directory(self.inputs, alias_output)["exit_code"], 2)
        self.assertEqual(list(self.outputs.iterdir()), [])

    def test_symlink_configuration_is_not_followed(self):
        target = self.root / "secret.cfg"
        target.write_bytes(b"hostname OUTSIDE_SECRET\n")
        linked = self.inputs / "linked.cfg"
        try:
            linked.symlink_to(target)
        except OSError:
            self.skipTest("platform does not allow test symlink creation")
        result = self.audit()
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(result["devices"][0]["status"], "error")
        self.assertIsNone(result["devices"][0]["source"]["sha256"])
        self.assertNotIn("OUTSIDE_SECRET", json.dumps(result))

    def test_atomic_output_replaces_symlink_without_modifying_target(self):
        self.write("source.cfg")
        first = self.audit()
        target = self.root / "protected.txt"
        target.write_text("protected", encoding="utf-8")
        output = self.outputs / first["devices"][0]["outputs"]["json"]
        output.unlink()
        try:
            output.symlink_to(target)
        except OSError:
            self.skipTest("platform does not allow test symlink creation")
        self.assertEqual(self.audit()["exit_code"], 2)
        self.assertEqual(target.read_text(encoding="utf-8"), "protected")

    def test_cli_returns_batch_exit_code_and_summary(self):
        from netaudit.cli import main
        self.write("high.cfg")
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            code = main(["audit-batch", str(self.inputs), "--out-dir", str(self.outputs), "--fail-on", "high"])
        self.assertEqual(code, 1)
        self.assertIn("1", stdout.getvalue())
        self.assertTrue((self.outputs / "batch.json").exists())


if __name__ == "__main__":
    unittest.main()
