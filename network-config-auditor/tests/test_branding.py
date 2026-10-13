from contextlib import redirect_stdout
import http.client
import io
import json
from pathlib import Path
import re
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

from netaudit import __version__
from netaudit.cli import main
from netaudit.pipeline import audit_configuration
from netaudit.server import LocalServer, make_handler, serve
from netaudit.simulator import simulate_configuration


class RuntimeBrandingTests(unittest.TestCase):
    def test_cli_version_and_distribution_version_match_new_name(self):
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as exited:
            main(["--version"])
        self.assertEqual(exited.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), "NetConfig Auditor 1.1.1")
        project = Path(__file__).resolve().parents[1] / "pyproject.toml"
        self.assertEqual(re.search(r'^version = "([^"]+)"$', project.read_text(encoding="utf-8"), re.M)[1], __version__)

    def test_startup_console_displays_product_name(self):
        bound = MagicMock()
        bound.server_port = 43210
        bound.__enter__.return_value = bound
        bound.serve_forever.side_effect = KeyboardInterrupt
        output = io.StringIO()
        with patch("netaudit.server._bind_server", return_value=bound), redirect_stdout(output):
            serve(0, open_browser=False)
        self.assertIn("NetConfig Auditor 已启动：http://127.0.0.1:43210", output.getvalue())
        self.assertNotIn("NetAudit", output.getvalue())

    def test_remediation_product_note_does_not_rename_device(self):
        config = "hostname NetAudit\nip http server\n"
        report = audit_configuration(config, "cisco")
        self.assertEqual(report["device"]["hostname"], "NetAudit")
        finding = next(item for item in report["findings"] if item["command_notes"])
        self.assertIn("NetConfig Auditor 不连接设备", finding["command_notes"])
        self.assertNotIn("NetAudit 不连接设备", finding["command_notes"])

    def test_simulator_product_prompt_for_all_vendors(self):
        for vendor, expected in (("cisco", "NetConfig Auditor#"), ("ruijie", "NetConfig Auditor#"),
                                 ("huawei", "<NetConfig Auditor>"), ("h3c", "<NetConfig Auditor>")):
            with self.subTest(vendor=vendor):
                result = simulate_configuration("interface GigabitEthernet0/1\n shutdown\n", vendor)
                self.assertEqual(result["prompt"], expected)
                self.assertEqual(result["inventory"]["hostname"], "unknown")

    def test_simulator_preserves_actual_hostname_and_raw_config(self):
        for vendor, directive, prompt in (("cisco", "hostname", "NetConfig Auditor#"),
                                           ("huawei", "sysname", "<NetConfig Auditor>")):
            with self.subTest(vendor=vendor):
                config = f"{directive} NetAudit\r\ninterface GigabitEthernet0/1\r\n shutdown\r\n"
                result = simulate_configuration(config, vendor)
                self.assertEqual(result["prompt"], prompt)
                self.assertEqual(result["inventory"]["hostname"], "NetAudit")
                self.assertEqual(result["config"], config)

    def test_simulator_config_prompt_uses_product_name_and_keeps_inventory(self):
        for vendor, directive, command, prompt in (("cisco", "hostname", "configure terminal", "NetConfig Auditor(config)#"),
                                                   ("huawei", "sysname", "system-view", "[NetConfig Auditor]")):
            with self.subTest(vendor=vendor):
                result = simulate_configuration(f"{directive} Lab-Switch\n", vendor, command)
                self.assertEqual(result["prompt"], prompt)
                self.assertEqual(result["inventory"]["hostname"], "Lab-Switch")

    def test_old_intelligence_cache_location_remains_usable(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"LOCALAPPDATA": directory}), \
                patch("netaudit.intelligence.fetch_official_kev") as fetch, redirect_stdout(io.StringIO()):
            self.assertEqual(main(["intel-update"]), 0)
            self.assertEqual(fetch.call_args.kwargs["destination"], Path(directory) / "NetAudit" / "kev.json")


class ServerBrandingCompatibilityTests(unittest.TestCase):
    def test_server_header_is_new_brand_and_legacy_session_header_still_authorizes(self):
        with LocalServer(("127.0.0.1", 0), make_handler("brand-token")) as server:
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                connection.request("POST", "/api/simulate", json.dumps({"config": "hostname NetAudit\n"}), {
                    "Origin": f"http://127.0.0.1:{server.server_port}",
                    "X-NetAudit-Token": "brand-token", "Content-Type": "application/json"})
                response = connection.getresponse()
                body = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader("Server").strip(), "NetConfig-Auditor")
                self.assertEqual(body["inventory"]["hostname"], "NetAudit")
            finally:
                connection.close()
                server.shutdown()
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
