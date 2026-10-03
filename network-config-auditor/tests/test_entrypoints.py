from contextlib import redirect_stderr, redirect_stdout
import http.client
import io
import json
import os
from pathlib import Path
import tempfile
import threading
from http.server import ThreadingHTTPServer
import unittest

from netaudit.cli import main
from netaudit.server import make_handler


class CLITests(unittest.TestCase):
    def test_json_export_and_exit_thresholds(self):
        with tempfile.TemporaryDirectory() as d:
            cfg, out = Path(d) / "input.cfg", Path(d) / "report.json"
            cfg.write_text("hostname X\nip http server")
            with redirect_stderr(io.StringIO()):
                code = main(["audit", str(cfg), "--format", "json", "--out", str(out), "--fail-on", "high"])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(out.read_text())["device"]["hostname"], "X")
            if os.name != "nt":
                self.assertEqual(out.stat().st_mode & 0o777, 0o600)

    def test_strict_coverage_returns_2_but_writes_report(self):
        with tempfile.TemporaryDirectory() as d:
            cfg, out = Path(d) / "input.cfg", Path(d) / "report.json"
            cfg.write_text("hostname X\nunknown command")
            with redirect_stderr(io.StringIO()):
                code = main(["audit", str(cfg), "--strict", "--format", "json", "--out", str(out)])
            self.assertEqual(code, 2)
            self.assertTrue(out.exists())

    def test_input_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "input.cfg"
            cfg.write_text("hostname X")
            with redirect_stderr(io.StringIO()):
                code = main(["audit", str(cfg), "--out", str(cfg)])
            self.assertEqual(code, 2)
            self.assertEqual(cfg.read_text(), "hostname X")

    def test_invalid_utf8_has_clean_error(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "input.cfg"
            cfg.write_bytes(b"\xff\x00")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(["audit", str(cfg)]), 2)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler("test-token"))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        conn.request(method, path, body, headers or {})
        r = conn.getresponse()
        result = r.status, dict(r.getheaders()), r.read().decode()
        conn.close()
        return result

    def headers(self):
        return {"Origin": f"http://127.0.0.1:{self.port}", "X-NetAudit-Token": "test-token", "Content-Type": "application/json"}

    def test_static_ui_and_headers(self):
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("NetAudit", body)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])

    def test_dns_rebinding_host_rejected(self):
        self.assertEqual(self.request("GET", "/api/session", headers={"Host": "evil.example"})[0], 403)

    def test_cross_origin_token_rejected(self):
        self.assertEqual(self.request("GET", "/api/session", headers={"Origin": "https://evil.example"})[0], 403)

    def test_session_token_same_origin(self):
        self.assertEqual(json.loads(self.request("GET", "/api/session")[2])["token"], "test-token")

    def test_post_without_token_rejected(self):
        self.assertEqual(self.request("POST", "/api/audit", "{}", {"Content-Type": "application/json"})[0], 403)

    def test_cross_origin_post_rejected(self):
        h = self.headers();h["Origin"] = "https://evil.example"
        self.assertEqual(self.request("POST", "/api/audit", "{}", h)[0], 403)

    def test_full_audit_and_exports(self):
        status, _, body = self.request("POST", "/api/audit", json.dumps({"config": "hostname X\nip http server"}), self.headers())
        self.assertEqual(status, 200)
        value = json.loads(body)
        self.assertEqual(value["report"]["summary"]["severity"]["high"], 1)
        self.assertEqual(set(value["exports"]), {"json", "md", "html"})

    def test_bad_body_types_rejected(self):
        for body in ("null", "[]", '{"config":5}', '{"config":"hostname X","vendor":5}', '{notjson}'):
            with self.subTest(body=body):
                self.assertEqual(self.request("POST", "/api/audit", body, self.headers())[0], 400)

    def test_traversal_not_supported(self):
        self.assertEqual(self.request("GET", "/../../etc/passwd")[0], 404)


if __name__ == "__main__":
    unittest.main()
