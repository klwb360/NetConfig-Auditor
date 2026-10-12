import copy
import json
import os
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from netaudit import audit, parse_config
from netaudit.ai import MAX_ITEM_CHARS, MAX_RESPONSE_BYTES, explain_report, validate_ai_settings


@contextmanager
def fake_ollama(callback=None):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            payload = json.loads(raw)
            requests.append({"path": self.path, "raw": raw, "payload": payload})
            facts = json.loads(payload["messages"][1]["content"])["rules"]
            if callback:
                callback(self, facts)
                return
            value = {"items": [{"rule_id": f["rule_id"], "explanation": "此规则提示配置风险，需核对现网。",
                                "remediation": "先确认备用管理路径，再人工制定变更与回退方案。"} for f in facts]}
            respond(self, {"done": True, "message": {"content": json.dumps(value, ensure_ascii=False)}})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:" + str(server.server_port), requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def respond(handler, value, status=200):
    data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    try:
        handler.wfile.write(data)
    except (BrokenPipeError, ConnectionResetError):
        pass


def report():
    return audit(parse_config("hostname PRIVATE-DEVICE-XYZ\nusername admin password 0 SECRET-XYZ\nip http server", "cisco"))


def enabled(endpoint):
    return {"enabled": True, "model": "qwen2.5:7b", "endpoint": endpoint, "timeout": 2}


def model_items_response(transform):
    def callback(handler, facts):
        items = [{"rule_id": f["rule_id"], "explanation": "请核对规则事实。", "remediation": "先核实再人工整改。"} for f in facts]
        value = transform(items)
        respond(handler, {"done": True, "message": {"content": json.dumps(value, ensure_ascii=False)}})
    return callback


class AISettingsTests(unittest.TestCase):
    def test_default_disabled_makes_no_request(self):
        with patch("netaudit.ai.urllib.request.build_opener") as opener:
            value = explain_report(report())
        opener.assert_not_called()
        self.assertEqual(value["status"], "disabled")
        self.assertEqual(value["items"], [])

    def test_localhost_normalized_without_dns(self):
        self.assertEqual(validate_ai_settings({"endpoint": "http://localhost:11434/"})["endpoint"], "http://127.0.0.1:11434")
        self.assertEqual(validate_ai_settings({"endpoint": "http://[::1]:11434"})["endpoint"], "http://[::1]:11434")
        self.assertEqual(validate_ai_settings({"endpoint": "http://[::ffff:127.0.0.1]:11434"})["endpoint"], "http://127.0.0.1:11434")

    def test_reject_remote_or_ambiguous_endpoints(self):
        invalid = ["https://example.com", "http://192.168.1.1", "http://0.0.0.0", "file:///tmp/test",
                   "http://127.0.0.1.evil.example", "http://127.0.0.1@evil.example", "http://evil@127.0.0.1",
                   "http://localhost:11434/api/chat", "http://localhost?x=y", "http://localhost#x",
                   "http://localhost:99999", "http://localhost:0", "http://[::ffff:192.168.1.1]", "http://127.1"]
        for endpoint in invalid:
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                validate_ai_settings({"endpoint": endpoint})

    def test_explicit_enable_and_valid_model_timeout(self):
        invalid = [{"enabled": "true"}, {"enabled": True}, {"model": "../model name"},
                   {"model": "gpt-oss:120b-cloud"}, {"model": "cloud:test"},
                   {"provider": "openai"}, {"api_key": "SECRET"}, {"timeout": True},
                   {"timeout": 0}, {"timeout": 121}, {"timeout": float("nan")}, {"timeout": "30"}]
        for settings in invalid:
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                validate_ai_settings(settings)

    def test_bad_settings_have_clear_non_ai_result(self):
        result = explain_report(report(), {"enabled": True, "model": "x", "endpoint": "https://example.com"})
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["items"], [])
        self.assertNotIn("example.com", result["message"])

    def test_empty_findings_do_not_request_model(self):
        with patch("netaudit.ai.urllib.request.build_opener") as opener:
            result = explain_report({"findings": []}, enabled("http://localhost:11434"))
        opener.assert_not_called()
        self.assertEqual(result["status"], "not-needed")


class AIRequestTests(unittest.TestCase):
    def test_real_loopback_generation_contains_only_minimal_facts(self):
        original = report()
        snapshot = copy.deepcopy(original)
        with fake_ollama() as (endpoint, requests):
            result = explain_report(original, enabled(endpoint))
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(original, snapshot)
        self.assertEqual(len(requests), 1)
        sent = requests[0]
        self.assertEqual(sent["path"], "/api/chat")
        body = sent["raw"].decode("utf-8")
        for sensitive in ("SECRET-XYZ", "PRIVATE-DEVICE-XYZ", "username admin", "ip http server", "evidence", "inventory", "hostname"):
            self.assertNotIn(sensitive, body)
        facts = json.loads(sent["payload"]["messages"][1]["content"])["rules"]
        self.assertEqual(set(facts[0]), {"rule_id", "title", "severity", "risk", "recommendation"})
        self.assertFalse(sent["payload"]["stream"])
        self.assertEqual(sent["payload"]["format"], "json")

    def test_environment_proxy_is_never_used(self):
        proxies = {"HTTP_PROXY": "http://127.0.0.1:1", "HTTPS_PROXY": "http://127.0.0.1:1",
                   "ALL_PROXY": "http://127.0.0.1:1", "NO_PROXY": "", "no_proxy": ""}
        with fake_ollama() as (endpoint, requests), patch.dict(os.environ, proxies):
            result = explain_report(report(), enabled(endpoint))
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(len(requests), 1)

    def test_repeat_findings_deduplicated(self):
        value = report()
        value["findings"].append(copy.deepcopy(value["findings"][0]))
        with fake_ollama() as (endpoint, requests):
            result = explain_report(value, enabled(endpoint))
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(len(result["items"]), 2)

    def test_cve_fact_whitelist_and_candidate_status(self):
        value = report()
        value["intelligence"] = {"asset": {"product": "PRIVATE-PRODUCT", "version": "PRIVATE-VERSION"},
                                 "matches": [], "candidates": [{"cve_id": "CVE-2024-12345", "known_exploited": True,
                                 "confidence": "user-provided-candidate", "kev": {"requiredAction": "Apply vendor mitigation.",
                                 "notes": "SECRET-NOTES", "dueDate": "2024-01-01"}}]}

        def transform(items):
            items[-1]["explanation"] = "CVE-2024-12345 仅是候选线索；KEV 收录不证明本机受影响。"
            return {"items": items}

        with fake_ollama(model_items_response(transform)) as (endpoint, requests):
            result = explain_report(value, enabled(endpoint))
        self.assertEqual(result["status"], "completed", result)
        body = requests[0]["raw"].decode("utf-8")
        for sensitive in ("PRIVATE-PRODUCT", "PRIVATE-VERSION", "SECRET-NOTES", "2024-01-01"):
            self.assertNotIn(sensitive, body)
        fact = json.loads(requests[0]["payload"]["messages"][1]["content"])["rules"][-1]
        self.assertEqual(fact["status"], "candidate")
        self.assertTrue(fact["known_exploited"])
        self.assertEqual(result["items"][-1]["rule_id"], "INTEL:CVE-2024-12345")

    def test_failure_keeps_original_report_and_no_template_items(self):
        value = report()
        snapshot = copy.deepcopy(value)
        with fake_ollama(lambda handler, _: respond(handler, b"SERVER-SECRET", status=500)) as (endpoint, _):
            result = explain_report(value, enabled(endpoint))
        self.assertEqual(value, snapshot)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["items"], [])
        self.assertIn("HTTP 500", result["message"])
        self.assertNotIn("SERVER-SECRET", result["message"])

    def test_redirect_is_not_followed(self):
        def redirect(handler, _):
            handler.send_response(302)
            handler.send_header("Location", "http://127.0.0.1:" + str(handler.server.server_port) + "/leaked")
            handler.send_header("Content-Length", "0")
            handler.end_headers()

        with fake_ollama(redirect) as (endpoint, requests):
            result = explain_report(report(), enabled(endpoint))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(requests), 1)

    def test_closed_socket_has_readable_failure(self):
        with fake_ollama() as (endpoint, _):
            pass
        result = explain_report(report(), enabled(endpoint))
        self.assertEqual(result["status"], "failed")
        self.assertIn("无法连接", result["message"])

    def test_response_size_limit(self):
        with fake_ollama(lambda handler, _: respond(handler, b"x" * (MAX_RESPONSE_BYTES + 1))) as (endpoint, _):
            result = explain_report(report(), enabled(endpoint))
        self.assertEqual(result["status"], "failed")
        self.assertIn("大小限制", result["message"])

    def test_slow_response_respects_total_deadline(self):
        def slow(handler, _):
            handler.send_response(200)
            handler.send_header("Content-Length", "20")
            handler.end_headers()
            for _ in range(10):
                try:
                    handler.wfile.write(b"xx")
                    handler.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
                time.sleep(0.25)

        with fake_ollama(slow) as (endpoint, _):
            settings = enabled(endpoint)
            settings["timeout"] = 1
            started = time.monotonic()
            result = explain_report(report(), settings)
            elapsed = time.monotonic() - started
        self.assertEqual(result["status"], "failed")
        self.assertLess(elapsed, 1.7)

    def test_malformed_and_unfinished_response_rejected(self):
        malformed = [b"SERVER-SECRET", {"done": False, "message": {"content": "{}"}},
                     {"done": True, "message": None}, {"done": True, "message": {"content": "SERVER-SECRET"}}]
        for value in malformed:
            with self.subTest(value=value), fake_ollama(lambda handler, _, v=value: respond(handler, v)) as (endpoint, _):
                result = explain_report(report(), enabled(endpoint))
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["items"], [])
                self.assertNotIn("SERVER-SECRET", result["message"])

    def test_unknown_duplicate_or_missing_rules_rejected(self):
        transforms = [lambda items: {"items": items + [dict(items[0])]},
                      lambda items: {"items": items[1:]},
                      lambda items: {"items": [{**items[0], "rule_id": "MADE-UP"}] + items[1:]},
                      lambda items: {"items": [{**items[0], "severity": "critical"}] + items[1:]},
                      lambda items: {"items": items, "confidence": "confirmed"}]
        for transform in transforms:
            with self.subTest(transform=transform), fake_ollama(model_items_response(transform)) as (endpoint, _):
                result = explain_report(report(), enabled(endpoint))
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["items"], [])

    def test_cve_invention_rejected_even_without_word_boundary(self):
        def transform(items):
            items[0]["explanation"] = "设备存在CVE-2024-12345漏洞。"
            return {"items": items}

        with fake_ollama(model_items_response(transform)) as (endpoint, _):
            result = explain_report(report(), enabled(endpoint))
        self.assertEqual(result["status"], "failed")
        self.assertIn("CVE", result["message"])

    def test_malformed_cve_invention_rejected(self):
        def transform(items):
            items[0]["explanation"] = "CVE-20245-1"
            return {"items": items}

        with fake_ollama(model_items_response(transform)) as (endpoint, _):
            result = explain_report(report(), enabled(endpoint))
        self.assertEqual(result["status"], "failed")

    def test_deeply_nested_json_is_readable_failure(self):
        data = b"[" * 1500 + b"0" + b"]" * 1500
        with fake_ollama(lambda handler, _: respond(handler, data)) as (endpoint, _):
            result = explain_report(report(), enabled(endpoint))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["items"], [])

    def test_input_rule_and_prompt_limits_make_no_requests(self):
        row = report()["findings"][0]
        too_many = {"findings": [{**row, "rule_id": f"TEST-{number}"} for number in range(65)]}
        too_large = {"findings": [{**row, "rule_id": f"TEST-{number}", "title": "字" * 1900,
                                   "risk": "字" * 1900, "recommendation": "字" * 1900} for number in range(4)]}
        for value in (too_many, too_large):
            with self.subTest(size=len(value["findings"])), patch("netaudit.ai.urllib.request.build_opener") as opener:
                result = explain_report(value, enabled("http://localhost:11434"))
                self.assertEqual(result["status"], "failed")
                opener.assert_not_called()

    def test_malformed_intelligence_never_makes_requests(self):
        value = report()
        value["intelligence"] = {"candidates": [{"cve_id": "CVE-2024-1234", "known_exploited": "yes"}]}
        with patch("netaudit.ai.urllib.request.build_opener") as opener:
            result = explain_report(value, enabled("http://localhost:11434"))
        self.assertEqual(result["status"], "failed")
        opener.assert_not_called()

    def test_long_or_empty_explanation_rejected(self):
        for output in ("", " " * 5, "x" * (MAX_ITEM_CHARS + 1)):
            def transform(items):
                items[0]["explanation"] = output
                return {"items": items}
            with self.subTest(length=len(output)), fake_ollama(model_items_response(transform)) as (endpoint, _):
                result = explain_report(report(), enabled(endpoint))
                self.assertEqual(result["status"], "failed")

    def test_overlong_or_malformed_facts_never_make_requests(self):
        invalid = [[], {"findings": [None]}, {"findings": [{"rule_id": "arbitrary"}]},
                   {"findings": [{**report()["findings"][0], "risk": "x" * (MAX_ITEM_CHARS + 1)}]}]
        for value in invalid:
            with self.subTest(value=value), patch("netaudit.ai.urllib.request.build_opener") as opener:
                result = explain_report(value, enabled("http://localhost:11434"))
                self.assertEqual(result["status"], "failed")
                opener.assert_not_called()

    def test_html_output_is_text_and_never_executed(self):
        def transform(items):
            items[0]["explanation"] = "<script>alert(1)</script>"
            return {"items": items}

        with fake_ollama(model_items_response(transform)) as (endpoint, _):
            result = explain_report(report(), enabled(endpoint))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["items"][0]["explanation"], "<script>alert(1)</script>")


if __name__ == "__main__":
    unittest.main()
