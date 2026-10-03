from contextlib import redirect_stderr, redirect_stdout
import errno
import http.client
import io
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

from netaudit.cli import main
from netaudit import server


class PortableCLITests(unittest.TestCase):
    def test_double_click_opens_default_web(self):
        with patch("netaudit.server.serve") as serve:
            self.assertEqual(main([]), 0)
        serve.assert_called_once_with(8765, open_browser=True)

    def test_no_browser_works_with_and_without_serve(self):
        for args in (["--no-browser"], ["serve", "--no-browser"]):
            with self.subTest(args=args), patch("netaudit.server.serve") as serve:
                self.assertEqual(main(args), 0)
                serve.assert_called_once_with(8765, open_browser=False)

    def test_custom_port_zero_and_invalid_port(self):
        with patch("netaudit.server.serve") as serve:
            self.assertEqual(main(["--port=0", "--no-browser"]), 0)
            serve.assert_called_once_with(0, open_browser=False)
        with patch("netaudit.server.serve") as serve, redirect_stderr(io.StringIO()):
            self.assertEqual(main(["serve", "--port", "65536"]), 2)
            serve.assert_not_called()

    def test_cli_three_exports_in_chinese_and_space_path(self):
        with tempfile.TemporaryDirectory(prefix="网络审计 空格 ") as directory:
            cfg = Path(directory) / "交换机 配置.cfg"
            cfg.write_text("hostname Portable\nip http server", encoding="utf-8")
            for fmt in ("json", "md", "html"):
                with self.subTest(format=fmt), redirect_stderr(io.StringIO()):
                    report = Path(directory) / f"审计 报告.{fmt}"
                    self.assertEqual(main(["audit", str(cfg), "--format", fmt, "--out", str(report)]), 0)
                    content = report.read_text(encoding="utf-8")
                    self.assertIn("Portable", content)
                    if fmt == "json":
                        self.assertEqual(json.loads(content)["device"]["hostname"], "Portable")


class PortableServerTests(unittest.TestCase):
    def test_occupied_port_falls_back_to_free_loopback_port(self):
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            requested = occupied.getsockname()[1]
            with server._bind_server(requested, server.make_handler("test")) as bound:
                self.assertNotEqual(bound.server_port, requested)
                self.assertEqual(bound.server_address[0], "127.0.0.1")
                selected = bound.server_port
            # The context manager releases the listener immediately.
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", selected))

    def test_unrelated_bind_error_is_not_hidden(self):
        with patch("netaudit.server.LocalServer", side_effect=OSError(errno.EMFILE, "too many files")) as create:
            with self.assertRaises(OSError):
                server._bind_server(8765, server.make_handler("test"))
            self.assertEqual(create.call_count, 1)

    def test_windows_reserved_port_can_fall_back(self):
        error = OSError(errno.EACCES, "reserved port")
        fallback = object()
        with patch("netaudit.server.LocalServer", side_effect=[error, fallback]) as create:
            self.assertIs(server._bind_server(8765, server.make_handler("test")), fallback)
            self.assertEqual(create.call_args.args[0], ("127.0.0.1", 0))

    def test_port_zero_bind_error_is_not_retried(self):
        with patch("netaudit.server.LocalServer", side_effect=OSError(errno.EACCES, "denied")) as create:
            with self.assertRaises(OSError):
                server._bind_server(0, server.make_handler("test"))
            self.assertEqual(create.call_count, 1)

    def fake_server(self):
        bound = MagicMock()
        bound.server_port = 43210
        bound.__enter__.return_value = bound
        bound.serve_forever.side_effect = KeyboardInterrupt
        return bound

    def test_browser_uses_actual_fallback_url_and_interrupt_closes_server(self):
        bound = self.fake_server()
        output = io.StringIO()
        with patch("netaudit.server._bind_server", return_value=bound), patch("netaudit.server.webbrowser.open", return_value=True) as browser, redirect_stdout(output):
            server.serve(8765)
        browser.assert_called_once_with("http://127.0.0.1:43210", new=2)
        self.assertIn("8765", output.getvalue())
        self.assertIn("http://127.0.0.1:43210", output.getvalue())
        self.assertIn("Ctrl+C", output.getvalue())
        bound.__exit__.assert_called_once()

    def test_no_browser_and_browser_failure_keep_service_available(self):
        for open_browser, result in ((False, False), (True, False), (True, OSError("no desktop"))):
            with self.subTest(open_browser=open_browser, result=result):
                bound = self.fake_server()
                output = io.StringIO()
                with patch("netaudit.server._bind_server", return_value=bound), patch("netaudit.server.webbrowser.open") as browser, redirect_stdout(output):
                    if isinstance(result, Exception):
                        browser.side_effect = result
                    else:
                        browser.return_value = result
                    server.serve(0, open_browser=open_browser)
                bound.serve_forever.assert_called_once()
                self.assertEqual(browser.call_count, int(open_browser))
                if open_browser:
                    self.assertIn("复制上方地址", output.getvalue())

    def test_all_web_resources_are_independent_of_working_directory(self):
        with tempfile.TemporaryDirectory(prefix="资源 空格 ") as directory:
            web = Path(directory) / "netaudit" / "web"
            web.mkdir(parents=True)
            resources = {"/": ("index.html", "网页正文"), "/app.js": ("app.js", "// javascript"), "/style.css": ("style.css", "body {}")}
            for name, content in resources.values():
                (web / name).write_text(content, encoding="utf-8")
            with patch("netaudit.server.WEB_DIR", web), server.LocalServer(("127.0.0.1", 0), server.make_handler("test")) as bound:
                thread = threading.Thread(target=bound.serve_forever)
                thread.start()
                try:
                    for path, (_, expected) in resources.items():
                        with self.subTest(path=path):
                            conn = http.client.HTTPConnection("127.0.0.1", bound.server_port, timeout=3)
                            try:
                                conn.request("GET", path)
                                response = conn.getresponse()
                                self.assertEqual(response.status, 200)
                                self.assertEqual(response.read().decode("utf-8"), expected)
                            finally:
                                conn.close()
                finally:
                    bound.shutdown()
                    thread.join(timeout=3)
                    self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
