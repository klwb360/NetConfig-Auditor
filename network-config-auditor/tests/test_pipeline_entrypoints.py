from contextlib import redirect_stderr, redirect_stdout
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from netaudit.cli import main
from netaudit import __version__
from netaudit.pipeline import audit_configuration
from netaudit.server import LocalServer, make_handler


class PipelineTests(unittest.TestCase):
    def test_version_without_starting_service(self):
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as exited:
            main(["--version"])
        self.assertEqual(exited.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), f"NetConfig Auditor {__version__}")

    def test_default_pipeline_is_local_and_honest_about_missing_inputs(self):
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Unexpected network request")):
            report = audit_configuration("hostname Example\nip http server", "cisco")
        self.assertEqual([s["stage"] for s in report["pipeline"]],
                         ["parser", "architecture", "security", "intelligence", "ai", "reports"])
        self.assertEqual(len(report["architecture"]["domains"]), 6)
        self.assertEqual(report["tool_version"], __version__)
        self.assertEqual(report["intelligence"]["status"], "not-configured")
        self.assertEqual(report["intelligence"]["sources"][0]["origin"], "bundled-official-snapshot")
        self.assertEqual(report["ai"]["status"], "disabled")

    def test_candidate_kev_does_not_confirm_device_vulnerability(self):
        report = audit_configuration("hostname Example", "cisco", asset={"cve_ids": ["CVE-2023-20198"]})
        self.assertEqual(report["intelligence"]["matches"], [])
        candidate = report["intelligence"]["candidates"][0]
        self.assertTrue(candidate["known_exploited"])
        self.assertEqual(candidate["confidence"], "user-provided-candidate")

    def test_protected_output_stops_before_ai_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "设备 配置.cfg"
            asset = Path(directory) / "设备 信息.json"
            config.write_text("hostname Example", encoding="utf-8")
            asset.write_text('{"cve_ids": []}', encoding="utf-8")
            with patch("netaudit.cli.audit_configuration") as pipeline, redirect_stderr(io.StringIO()):
                code = main(["audit", str(config), "--asset-info", str(asset), "--out", str(asset), "--ai-model", "local"])
            self.assertEqual(code, 2)
            pipeline.assert_not_called()
            self.assertEqual(asset.read_text(encoding="utf-8"), '{"cve_ids": []}')


class PipelineAPITests(unittest.TestCase):
    def setUp(self):
        self.server = LocalServer(("127.0.0.1", 0), make_handler("pipeline-token"))
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive())

    def request(self, value=None, raw=None):
        port = self.server.server_port
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        body = json.dumps(value).encode() if raw is None else raw
        try:
            connection.request("POST", "/api/audit", body, headers={
                "Origin": f"http://127.0.0.1:{port}", "X-NetAudit-Token": "pipeline-token",
                "Content-Type": "application/json"})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_api_candidates_and_three_exports_include_new_stages(self):
        status, value = self.request({"config": "hostname Example", "vendor": "cisco",
                                     "asset": {"cve_ids": ["CVE-2023-20198"]}})
        self.assertEqual(status, 200)
        self.assertEqual(value["report"]["intelligence"]["status"], "needs-review")
        for format_ in ("json", "md", "html"):
            self.assertIn("CVE-2023-20198", value["exports"][format_])

    def test_api_rejects_invalid_ai_without_request(self):
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Unexpected network request")):
            status, _ = self.request({"config": "hostname Example", "vendor": "cisco",
                                      "ai": {"enabled": True, "model": "local", "endpoint": "http://192.0.2.1:11434"}})
        self.assertEqual(status, 400)

    def test_nested_json_returns_readable_error(self):
        status, value = self.request(raw=b'{"config":"hostname Example","vendor":"cisco","asset":' + b'[' * 2000 + b'0' + b']' * 2000 + b'}')
        self.assertEqual(status, 400)
        self.assertIn("JSON", value["error"])
