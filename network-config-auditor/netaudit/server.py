from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import errno
import json
from pathlib import Path
import secrets
import signal
import threading
import webbrowser

from .parser import MAX_BYTES, MAX_LINES, detect_vendor
from .branding import APPLICATION_NAME, FILE_STEM
from .reports import render
from .pipeline import audit_configuration
from .simulator import simulate_configuration
from .simulation_goals import plan_goal

_SLOTS = threading.BoundedSemaphore(4)
WEB_DIR = Path(__file__).resolve().parent / "web"
MAX_REQUEST_BYTES = 36 * 1024 * 1024


def _detect_configuration(text: str) -> dict[str, str]:
    # Match parser limits without parsing the device or running the audit/AI
    # pipeline. Only fixed status information leaves this endpoint.
    try:
        size = len(text.encode("utf-8"))
    except UnicodeError:
        raise ValueError("配置文本须为有效 UTF-8") from None
    if size > MAX_BYTES:
        raise ValueError("配置超过 2 MiB 限制")
    if any(ord(c) < 32 and c not in "\n\r\t" for c in text):
        raise ValueError("配置含控制字符，请先移除终端转义序列")
    if len(text.splitlines()) > MAX_LINES:
        raise ValueError("配置超过 30000 行限制")
    if not text.strip():
        raise ValueError("配置为空")
    try:
        vendor, reason = detect_vendor(text)
    except ValueError:
        return {"status": "needs-manual", "vendor": "auto",
                "message": "无法可靠自动识别厂商；请手动选择，并每次导入一台设备的完整配置。"}
    return {"status": "detected", "vendor": vendor, "detection": reason}


class LocalServer(ThreadingHTTPServer):
    # A stalled browser request must not keep the executable alive on exit.
    daemon_threads = True

    def get_request(self):
        sock, addr = super().get_request()
        sock.settimeout(15)
        return sock, addr


def make_handler(token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = FILE_STEM
        sys_version = ""

        def log_message(self, *_):
            # Do not log user input, errors containing input or URL tokens.
            pass

        def _host_ok(self):
            return self.headers.get("Host") in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")

        def _send(self, status, body, mime="application/json; charset=utf-8"):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
            self.close_connection = True

        def _error(self, status, message):
            self._send(status, json.dumps({"error": message}, ensure_ascii=False))

        def do_GET(self):
            if not self._host_ok():
                return self._error(403, "Host 不允许")
            if self.path == "/api/session":
                origin = self.headers.get("Origin")
                if origin and origin not in (f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"):
                    return self._error(403, "Origin 不允许")
                return self._send(200, json.dumps({"token": token}))
            paths = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/simulator.js": ("simulator.js", "text/javascript; charset=utf-8"),
                "/vendor-syntax.js": ("vendor-syntax.js", "text/javascript; charset=utf-8"),
                "/vendor-highlight.js": ("vendor-highlight.js", "text/javascript; charset=utf-8"),
                "/style.css": ("style.css", "text/css; charset=utf-8"),
            }
            if self.path not in paths:
                return self._error(404, "路径不存在")
            name, mime = paths[self.path]
            return self._send(200, (WEB_DIR / name).read_text(encoding="utf-8"), mime)

        def do_POST(self):
            if not self._host_ok():
                return self._error(403, "Host 不允许")
            origin = self.headers.get("Origin")
            expected_origins = (f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}")
            if origin not in expected_origins or self.headers.get("X-NetAudit-Token") != token:
                return self._error(403, "请求来源或会话令牌不允许")
            if self.path not in ("/api/audit", "/api/detect", "/api/simulate", "/api/plan"):
                return self._error(404, "路径不存在")
            if self.headers.get_content_type() != "application/json" or self.headers.get("Transfer-Encoding"):
                return self._error(415, "仅接受带 Content-Length 的 JSON")
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                return self._error(400, "Content-Length 不合法")
            if not 0 < length <= MAX_REQUEST_BYTES:
                return self._error(413, "输入超过限制")
            if not _SLOTS.acquire(blocking=False):
                return self._error(429, "并发请求过多，请稍后重试")
            try:
                self.connection.settimeout(15)
                data = self.rfile.read(length)
                if len(data) != length:
                    return self._error(400, "请求内容不完整")
                value = json.loads(data.decode("utf-8"))
                if not isinstance(value, dict) or not isinstance(value.get("config"), str):
                    return self._error(400, "config/vendor 类型不合法")
                if self.path == "/api/detect":
                    result = _detect_configuration(value["config"])
                    return self._send(200, json.dumps(result, ensure_ascii=False))
                if not isinstance(value.get("vendor", "auto"), str):
                    return self._error(400, "config/vendor 类型不合法")
                if self.path in ("/api/simulate", "/api/plan"):
                    operation = simulate_configuration if self.path == "/api/simulate" else plan_goal
                    field = "commands" if self.path == "/api/simulate" else "goal"
                    result = operation(value["config"], value.get("vendor", "auto"),
                                       value.get(field, ""), value.get("context"))
                    return self._send(200, json.dumps(result, ensure_ascii=False))
                result = audit_configuration(
                    value["config"], value.get("vendor", "auto"), asset=value.get("asset"),
                    kev=value.get("kev"), nvd=value.get("nvd"), ai=value.get("ai"))
                self._send(200, json.dumps({"report": result, "exports": {f: render(result, f) for f in ("json", "md", "html")}}, ensure_ascii=False))
            except (ValueError, UnicodeError) as exc:
                # Parse errors intentionally never contain credential values.
                self._error(400, str(exc) if not isinstance(exc, json.JSONDecodeError) else "JSON 格式不合法")
            except RecursionError:
                self._error(400, "JSON 嵌套超过限制")
            except (TimeoutError, OSError):
                self.close_connection = True
            finally:
                _SLOTS.release()

    return Handler


def _bind_server(port: int, handler):
    try:
        return LocalServer(("127.0.0.1", port), handler)
    except OSError as exc:
        # Windows may reject an excluded/reserved port with WSAEACCES.
        # Other errors must remain visible instead of being hidden by retries.
        occupied = exc.errno in (errno.EADDRINUSE, errno.EACCES) or getattr(exc, "winerror", None) in (10048, 10013)
        if not port or not occupied:
            raise
        return LocalServer(("127.0.0.1", 0), handler)


def serve(port: int = 8765, *, open_browser: bool = True):
    # Ctrl+Break also permits a Windows automation runner to stop the whole
    # console process group cleanly, including a BAT launcher.
    break_signal = getattr(signal, "SIGBREAK", None)
    previous = None
    if break_signal is not None and threading.current_thread() is threading.main_thread():
        previous = signal.signal(break_signal, signal.default_int_handler)
    try:
        token = secrets.token_urlsafe(32)
        with _bind_server(port, make_handler(token)) as server:
            if port and server.server_port != port:
                print(f"端口 {port} 已被占用或不可用，已自动选择空闲端口。", flush=True)
            url = f"http://127.0.0.1:{server.server_port}"
            print(f"{APPLICATION_NAME} 已启动：{url}", flush=True)
            print("关闭程序：在此窗口按 Ctrl+C，或关闭此窗口。仅关闭网页不会停止服务。", flush=True)
            if open_browser:
                try:
                    opened = webbrowser.open(url, new=2)
                except (OSError, webbrowser.Error):
                    opened = False
                if not opened:
                    print("未能自动打开浏览器，请复制上方地址到浏览器。", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if previous is not None:
            signal.signal(break_signal, previous)
