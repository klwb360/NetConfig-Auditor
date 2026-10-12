import http.client
import json
import threading
import unittest
from unittest.mock import patch

from netaudit.parser import MAX_BYTES, MAX_LINES, detect_vendor
from netaudit.server import LocalServer, MAX_REQUEST_BYTES, make_handler


class VendorDetectionAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = LocalServer(("127.0.0.1", 0), make_handler("detect-token"))
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(
            target=cls.server.serve_forever, kwargs={"poll_interval": 0.05})
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        if cls.thread.is_alive():
            raise AssertionError("Detection test server did not stop")

    def request(self, value=None, *, raw=None, headers=None, path="/api/detect"):
        body = json.dumps(value).encode("utf-8") if raw is None else raw
        request_headers = {
            "Origin": f"http://127.0.0.1:{self.port}",
            "X-NetAudit-Token": "detect-token",
            "Content-Type": "application/json",
        }
        for key, value in (headers or {}).items():
            if value is None:
                request_headers.pop(key, None)
            else:
                request_headers[key] = value
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request("POST", path, body, headers=request_headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), json.loads(response.read())
        finally:
            connection.close()

    def test_four_vendors_reuse_parser_and_return_only_detection_metadata(self):
        configs = {
            "cisco": "hostname PRIVATE-DEVICE\nusername admin password 0 SECRET-VALUE",
            "huawei": "sysname PRIVATE-DEVICE\ninterface Vlanif10\n description SECRET-VALUE",
            "h3c": "sysname PRIVATE-DEVICE\ninterface Vlan-interface10\n description SECRET-VALUE",
            "ruijie": "version S29_RGOS 11.4\nhostname PRIVATE-DEVICE\nusername admin password SECRET-VALUE",
        }
        for vendor, config in configs.items():
            with self.subTest(vendor=vendor):
                status, headers, value = self.request({"config": config})
                self.assertEqual(status, 200)
                expected_vendor, expected_reason = detect_vendor(config)
                self.assertEqual(value, {"status": "detected", "vendor": expected_vendor,
                                         "detection": expected_reason})
                self.assertEqual(expected_vendor, vendor)
                serialized = json.dumps(value)
                self.assertNotIn("PRIVATE-DEVICE", serialized)
                self.assertNotIn("SECRET-VALUE", serialized)
                self.assertEqual(headers["Cache-Control"], "no-store")

    def test_ambiguous_and_mixed_configs_request_manual_selection(self):
        for config in ("sysname PRIVATE-DEVICE", "vlan 10", "hostname PRIVATE-DEVICE\nport trunk permit vlan 10",
                       "version S29_RGOS 11.4\ninterface Vlanif10"):
            with self.subTest(config=config):
                status, _, value = self.request({"config": config})
                self.assertEqual(status, 200)
                self.assertEqual(set(value), {"status", "vendor", "message"})
                self.assertEqual(value["status"], "needs-manual")
                self.assertEqual(value["vendor"], "auto")
                self.assertIn("手动选择", value["message"])
                self.assertNotIn("PRIVATE-DEVICE", json.dumps(value))

    def test_detection_does_not_parse_audit_render_or_call_ai(self):
        with patch("netaudit.server.audit_configuration") as audit, \
                patch("netaudit.server.render") as render, \
                patch("netaudit.pipeline.parse_config") as parse, \
                patch("netaudit.pipeline.explain_report") as ai, \
                patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Unexpected network request")):
            status, _, value = self.request({
                "config": "hostname PRIVATE-DEVICE\nip http server",
                "ai": {"enabled": True, "model": "remote", "endpoint": "https://example.test"},
                "asset": {"cve_ids": ["CVE-2023-20198"]},
            })
            self.assertEqual(status, 200)
            self.assertEqual(value["vendor"], "cisco")
            for operation in (audit, render, parse, ai):
                operation.assert_not_called()

    def test_host_origin_and_session_checks_are_shared(self):
        for headers in ({"Host": "evil.example"}, {"Origin": "https://evil.example"},
                        {"Origin": None}, {"X-NetAudit-Token": None}, {"X-NetAudit-Token": "wrong"}):
            with self.subTest(headers=headers):
                status, _, value = self.request({"config": "hostname PRIVATE-DEVICE"}, headers=headers)
                self.assertEqual(status, 403)
                self.assertNotIn("PRIVATE-DEVICE", json.dumps(value))

    def test_non_json_and_transfer_encoded_requests_are_rejected(self):
        for headers in ({"Content-Type": "text/plain"}, {"Transfer-Encoding": "chunked"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request({"config": "hostname LAB"}, headers=headers)[0], 415)

    def test_invalid_json_shape_and_encoding_are_rejected_without_input_echo(self):
        for raw in (b"null", b"[]", b'{"config":5}', b'{"vendor":"cisco"}', b'{broken}', b'\xff',
                    b'{"config":"hostname LAB\\ud800"}'):
            with self.subTest(raw=raw):
                status, _, value = self.request(raw=raw)
                self.assertEqual(status, 400)
                self.assertEqual(set(value), {"error"})
                self.assertNotIn("hostname LAB", value["error"])

    def test_control_characters_and_empty_configs_are_rejected(self):
        for config in ("", " \n\t", "hostname PRIVATE-DEVICE\x00", "hostname PRIVATE-DEVICE\x1b[31m"):
            with self.subTest(config=config):
                status, _, value = self.request({"config": config})
                self.assertEqual(status, 400)
                self.assertNotIn("PRIVATE-DEVICE", value["error"])

    def test_multibyte_size_and_line_limit_match_parser(self):
        for config, message in (("hostname LAB\n" + "汉" * (MAX_BYTES // 3), "2 MiB"),
                                ("hostname LAB\n" + "!\n" * MAX_LINES, "30000")):
            with self.subTest(message=message):
                status, _, value = self.request({"config": config})
                self.assertEqual(status, 400)
                self.assertIn(message, value["error"])

    def test_exact_size_and_line_boundaries_are_accepted(self):
        prefix = "hostname LAB\n"
        for config in (prefix + "!" * (MAX_BYTES - len(prefix.encode("utf-8"))),
                       prefix + "!\n" * (MAX_LINES - 1)):
            with self.subTest(size=len(config)):
                self.assertEqual(self.request({"config": config})[0], 200)

    def test_oversized_request_header_is_rejected_before_reading_body(self):
        status, _, value = self.request(raw=b"", headers={"Content-Length": str(MAX_REQUEST_BYTES + 1)})
        self.assertEqual(status, 413)
        self.assertIn("限制", value["error"])

    def test_invalid_content_length_is_rejected(self):
        self.assertEqual(self.request(raw=b"", headers={"Content-Length": "not-a-number"})[0], 400)

    def test_detection_obeys_shared_concurrency_limit(self):
        with patch("netaudit.server._SLOTS") as slots:
            slots.acquire.return_value = False
            self.assertEqual(self.request({"config": "hostname LAB"})[0], 429)
            slots.acquire.assert_called_once_with(blocking=False)
            slots.release.assert_not_called()

    def test_unknown_post_route_is_still_rejected(self):
        self.assertEqual(self.request({"config": "hostname LAB"}, path="/api/detect/extra")[0], 404)


if __name__ == "__main__":
    unittest.main()
