#!/usr/bin/env python3
"""Exercise actual source/BAT/frozen processes without installing NetAudit.

Examples::

    python tools/smoke_portable.py --source . --report build/source-smoke.json
    python tools/smoke_portable.py --onedir dist/onedir/NetAudit/NetAudit.exe --report build/onedir-smoke.json
    python tools/smoke_portable.py --onefile dist/onefile/NetAudit.exe --report build/onefile-smoke.json

Frozen checks require Windows. All copies, configurations, reports, logs and
extraction files live in a disposable Unicode/space-containing temporary tree.
No graphical browser is launched during this unattended check. Real no-argument
processes dispatch an observable browser stub; GUI interaction needs a manual test.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import http.client
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from typing import Callable


WINDOWS = os.name == "nt"
STARTUP_TIMEOUT = 90
COMMAND_TIMEOUT = 90
URL_PATTERN = re.compile(rb"http://127\.0\.0\.1:(\d+)")


class SmokeFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def no_python_environment(base: dict[str, str]) -> dict[str, str]:
    """Keep only OS executable locations in PATH, never setup-python/shims."""
    env = {k: v for k, v in base.items() if not k.upper().startswith("PYTHON")}
    windows = Path(env.get("SystemRoot", r"C:\Windows"))
    # A system-wide Python launcher can itself reside in C:\Windows; include
    # only System32, which contains cmd/where and the ordinary OS tools.
    env["PATH"] = str(windows / "System32")
    env.pop("VIRTUAL_ENV", None)
    return env


def bat_command(path: Path) -> list[str]:
    # The extra outer quotes are cmd.exe /s /c's required quoting convention.
    # CLI arguments are appended below with subprocess.list2cmdline, rather
    # than exposing an executable path containing spaces to cmd's tokenizer.
    return [os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"), "/d", "/s", "/c", str(path)]


@dataclass
class Target:
    name: str
    command: list[str]
    env: dict[str, str]
    bat: bool = False

    def argv(self, args: list[str]) -> list[str] | str:
        if self.bat:
            # Pass a raw Windows command line. Passing nested cmd quotes as a
            # list argument makes Popen insert backslashes before the quotes;
            # cmd.exe does not interpret those backslashes as quote escaping.
            return subprocess.list2cmdline(self.command[:-1]) + ' "' + subprocess.list2cmdline([self.command[-1], *args]) + '"'
        return self.command + args


def windows_descendants(parent_pid: int) -> set[int]:
    """Read a process snapshot without depending on PowerShell or WMI."""
    if not WINDOWS:
        return {parent_pid}
    import ctypes
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    require(handle not in (None, ctypes.c_void_p(-1).value), "Unable to inspect Windows process tree")
    entries: list[tuple[int, int]] = []
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        more = kernel.Process32FirstW(handle, ctypes.byref(entry))
        while more:
            entries.append((int(entry.th32ProcessID), int(entry.th32ParentProcessID)))
            more = kernel.Process32NextW(handle, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(handle)
    descendants = {parent_pid}
    while True:
        found = {pid for pid, parent in entries if parent in descendants}
        if found <= descendants:
            return descendants
        descendants.update(found)


def process_alive(pid: int) -> bool:
    if WINDOWS:
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def port_open(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.3)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def kill_tree(process: subprocess.Popen) -> None:
    if WINDOWS:
        try:
            pids = windows_descendants(process.pid)
        except Exception:
            # Even a failed diagnostic must still attempt taskkill /T.
            pids = {process.pid}
        taskkill = str(Path(os.environ["SystemRoot"]) / "System32" / "taskkill.exe")
        for pid in [process.pid, *sorted(pids - {process.pid})]:
            if process_alive(pid):
                subprocess.run([taskkill, "/PID", str(pid), "/T", "/F"],
                               stdin=subprocess.DEVNULL, capture_output=True, timeout=15)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=15)


def run_command(target: Target, args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """A CLI timeout must terminate the BAT/bootloader's entire process tree."""
    argv = target.argv(args)
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {"start_new_session": True}
    process = subprocess.Popen(argv, cwd=cwd, env=target.env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options)
    try:
        out, err = process.communicate(timeout=COMMAND_TIMEOUT)
        return subprocess.CompletedProcess(argv, process.returncode, out, err)
    except subprocess.TimeoutExpired:
        kill_tree(process)
        process.communicate(timeout=15)
        raise SmokeFailure(f"CLI timed out after {COMMAND_TIMEOUT}s; its process tree was terminated")
    except BaseException:
        if process.poll() is None:
            kill_tree(process)
        raise


class Service:
    def __init__(self, target: Target, cwd: Path, log: Path, args: list[str]):
        self.target, self.cwd, self.log, self.args = target, cwd, log, args
        self.process: subprocess.Popen | None = None
        self.output = None
        self.port: int | None = None
        self.shutdown: dict = {}

    def start(self) -> int:
        self.output = self.log.open("wb")
        options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {"start_new_session": True}
        self.process = subprocess.Popen(self.target.argv(self.args), cwd=self.cwd, env=self.target.env,
                                        stdin=subprocess.DEVNULL, stdout=self.output, stderr=subprocess.STDOUT, **options)
        deadline = time.monotonic() + STARTUP_TIMEOUT
        while time.monotonic() < deadline:
            data = self.log.read_bytes()
            matches = URL_PATTERN.findall(data)
            if matches:
                self.port = int(matches[-1])
                if port_open(self.port):
                    return self.port
            if self.process.poll() is not None:
                raise SmokeFailure(f"Server exited with {self.process.returncode}: {data.decode('utf-8', 'replace')[-2000:]}")
            time.sleep(0.1)
        raise SmokeFailure("Server did not publish a reachable actual address before timeout")

    def stop(self) -> dict:
        if self.process is None:
            if self.output:
                self.output.close()
            return {}
        process = self.process
        pids = {process.pid}
        inspection_error = None
        try:
            if process.poll() is None:
                pids = windows_descendants(process.pid)
        except Exception as exc:
            # Snapshot errors must not prevent terminating the actual server.
            inspection_error = str(exc)
        forced = False
        signal_error = None
        try:
            if process.poll() is None:
                try:
                    if WINDOWS:
                        process.send_signal(signal.CTRL_BREAK_EVENT)
                    else:
                        os.killpg(process.pid, signal.SIGINT)
                    process.wait(timeout=15)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    forced, signal_error = True, str(exc)
            if process.poll() is None:
                kill_tree(process)
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and (any(process_alive(pid) for pid in pids)
                                                  or self.port is not None and port_open(self.port)):
                time.sleep(0.1)
            remaining = sorted(pid for pid in pids if process_alive(pid))
            # Kill descendants even if their original launcher has exited.
            for pid in remaining:
                forced = True
                if WINDOWS:
                    subprocess.run([str(Path(os.environ["SystemRoot"]) / "System32" / "taskkill.exe"),
                                    "/PID", str(pid), "/T", "/F"],
                                   stdin=subprocess.DEVNULL, capture_output=True, timeout=15)
                else:
                    os.kill(pid, signal.SIGKILL)
            if remaining:
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and any(process_alive(pid) for pid in pids):
                    time.sleep(0.1)
            self.shutdown = {"exit_code": process.returncode, "forced_cleanup": forced,
                             "signal_error": signal_error, "process_inspection_error": inspection_error,
                             "observed_pids": sorted(pids),
                             "remaining_pids": sorted(pid for pid in pids if process_alive(pid)),
                             "port_closed": self.port is None or not port_open(self.port)}
            require(not self.shutdown["remaining_pids"], f"Service left processes: {self.shutdown}")
            require(self.shutdown["port_closed"], f"Service port remained open: {self.shutdown}")
            require(inspection_error is None, f"Process-tree inspection failed: {inspection_error}")
            require(not forced, f"Graceful interruption failed; forced cleanup was necessary: {self.shutdown}")
            native_cmd_interrupt = WINDOWS and self.target.bat and process.returncode in (0xC000013A, -1073741510)
            self.shutdown["interrupt_code_accepted_as_native_cmd_status"] = native_cmd_interrupt
            require(process.returncode == 0 or native_cmd_interrupt, f"Service interruption returned {process.returncode}")
            return self.shutdown
        finally:
            self.output.close()


def request(port: int, method: str, path: str, body: str | None = None,
            headers: dict[str, str] | None = None) -> tuple[str, dict[str, str]]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        data = response.read().decode("utf-8")
        require(response.status == 200, f"{method} {path}: HTTP {response.status}: {data[:300]}")
        return data, dict(response.getheaders())
    finally:
        conn.close()


def validate_report(text: str, format_: str, vendor: str | None = None) -> None:
    if format_ == "json":
        report = json.loads(text)
        require({"device", "summary", "findings", "inventory"} <= report.keys(), "Incomplete JSON report")
        if vendor:
            require(report["device"]["vendor"] == vendor, f"Wrong vendor in report: {report['device']}")
    elif format_ == "md":
        require(text.startswith("# 网络配置审计报告") and "配置清单" in text, "Incomplete Markdown export")
    else:
        require(text.lower().startswith("<!doctype html>") and "</html>" in text and "网络配置审计报告" in text,
                "Incomplete HTML export")


def exercise_web(port: int, reference: Path, examples: Path) -> dict:
    resources: dict[str, str] = {}
    for route, filename, mime in (("/", "index.html", "text/html"), ("/style.css", "style.css", "text/css"),
                                   ("/app.js", "app.js", "text/javascript")):
        text, headers = request(port, "GET", route)
        require(headers.get("Content-Type", "").startswith(mime), f"Wrong MIME type for {route}")
        require(text == (reference / filename).read_text(encoding="utf-8"), f"Packaged {filename} differs from source")
        resources[filename] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    token = json.loads(request(port, "GET", "/api/session")[0])["token"]
    require(isinstance(token, str) and len(token) >= 16, "Invalid session token")
    headers = {"Origin": f"http://127.0.0.1:{port}", "X-NetAudit-Token": token,
               "Content-Type": "application/json"}
    totals = {}
    for vendor in ("cisco", "huawei", "h3c"):
        body = json.dumps({"vendor": vendor, "config": (examples / f"{vendor}.cfg").read_text(encoding="utf-8")})
        value = json.loads(request(port, "POST", "/api/audit", body, headers)[0])
        require(value["report"]["device"]["vendor"] == vendor, "Audit API selected wrong vendor")
        require(set(value["exports"]) == {"json", "md", "html"}, "Audit API missing exports")
        for format_, text in value["exports"].items():
            validate_report(text, format_, vendor)
        require(json.loads(value["exports"]["json"]) == value["report"], "JSON export differs from API report")
        totals[vendor] = value["report"]["summary"]["total"]
    return {"resources_sha256": resources, "vendors_findings": totals,
            "exports": ["json", "md", "html"], "session_token": "validated; omitted"}


def readonly_directory(path: Path) -> Callable[[], None]:
    """Deny writes to this temporary application copy, then restore on cleanup."""
    if WINDOWS:
        result = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"],
                                check=True, capture_output=True, text=True, timeout=10)
        # icacls requires '*' before a numeric SID; otherwise it resolves the
        # SID text as an account name and fails with ERROR_NONE_MAPPED (1332).
        sid = "*" + next(csv.reader(result.stdout.splitlines()))[1]
        icacls = str(Path(os.environ["SystemRoot"]) / "System32" / "icacls.exe")

        def restore() -> None:
            subprocess.run([icacls, str(path), "/remove:d", sid, "/T", "/C"],
                           check=True, capture_output=True, timeout=60)

        try:
            # Generic W includes READ_CONTROL/SYNCHRONIZE, which would also
            # reject ordinary reads. Deny only data/append/attribute writes.
            subprocess.run([icacls, str(path), "/deny", f"{sid}:(OI)(CI)(WD,AD,WEA,WA)", "/T", "/C"],
                           check=True, capture_output=True, timeout=60)
        except BaseException as exc:
            # /T /C can apply some ACLs before reporting a failure. Always
            # revoke the deny entries before the temporary tree is removed.
            try:
                restore()
            except Exception as rollback:
                raise SmokeFailure(f"Write-deny ACL failed: {exc}; ACL rollback failed: {rollback}") from exc
            raise
    else:
        modes = {p: p.stat().st_mode & 0o777 for p in [path, *path.rglob("*")] if not p.is_symlink()}
        for p, mode in modes.items():
            p.chmod(mode & ~0o222)

        def restore() -> None:
            for p, mode in modes.items():
                p.chmod(mode)

    try:
        probe = path / "__smoke_write_must_fail__.tmp"
        try:
            probe.write_text("probe", encoding="utf-8")
        except PermissionError:
            return restore
        probe.unlink()
        raise SmokeFailure("This account bypasses read-only permissions; read-only runtime check cannot be claimed")
    except Exception:
        restore()
        raise


class Harness:
    def __init__(self, report: dict, root: Path, install: Path, reference: Path, mode: str):
        self.report, self.root, self.install, self.reference, self.mode = report, root, install, reference, mode
        self.cwd = root / "外部 工作目录"
        self.cwd.mkdir()
        self.runtime = root / "用户 临时目录"
        self.runtime.mkdir()
        self.results = root / "中文 输入输出"
        self.results.mkdir()
        self.env = dict(os.environ, TEMP=str(self.runtime), TMP=str(self.runtime), TMPDIR=str(self.runtime),
                        PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")

    def check(self, name: str, target: str, operation: Callable[[], dict]) -> None:
        started = time.monotonic()
        record = {"name": name, "target": target}
        try:
            record.update(operation())
            record["status"] = "passed"
        except Exception as exc:
            record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        record["seconds"] = round(time.monotonic() - started, 3)
        self.report["checks"].append(record)
        print(f"{record['status'].upper()}: {target}: {name}", flush=True)
        if record["status"] == "failed":
            print(record["error"], flush=True)

    def cli(self, target: Target) -> dict:
        output_dir = self.results / target.name
        output_dir.mkdir()
        runs = []
        for vendor in ("cisco", "huawei", "h3c"):
            cfg = output_dir / f"设备 配置 {vendor}.cfg"
            shutil.copyfile(self.install / "examples" / f"{vendor}.cfg", cfg)
            for format_ in ("json", "md", "html"):
                out = output_dir / f"审计 报告 {vendor}.{format_}"
                args = ["audit", str(cfg), "--vendor", vendor, "--format", format_, "--out", str(out)]
                result = run_command(target, args, self.cwd)
                require(result.returncode == 0, f"CLI {vendor}/{format_} exit {result.returncode}: {result.stderr.decode('utf-8', 'replace')[-1500:]}")
                require(out.is_file(), f"CLI did not write {out.name}")
                validate_report(out.read_text(encoding="utf-8"), format_, vendor)
                runs.append({"vendor": vendor, "format": format_, "exit_code": result.returncode})
        cfg = output_dir / "退出码 配置.cfg"
        cfg.write_text("hostname PortableSmoke\nip http server\nunknown smoke-command\n", encoding="utf-8")
        for expected, extra in ((1, ["--fail-on", "high"]), (2, ["--strict"]), (2, ["--vendor", "invalid"])):
            result = run_command(target, ["audit", str(cfg), "--format", "json", *extra], self.cwd)
            require(result.returncode == expected, f"CLI exit-code check expected {expected}, got {result.returncode}")
            runs.append({"arguments": extra, "exit_code": result.returncode})
        return {"runs": runs, "stdin": "DEVNULL", "timeout_seconds": COMMAND_TIMEOUT,
                "external_cwd": True, "unicode_and_spaces_in_paths": True}

    def browser_stub(self, target: Target) -> tuple[Target, Path, str]:
        marker = self.results / f"{target.name}-browser-url.txt"
        if WINDOWS:
            stub = self.results / f"{target.name}-browser-stub.vbs"
            escaped = str(marker).replace('"', '""')
            stub.write_text('Set fs = CreateObject("Scripting.FileSystemObject")\n'
                            f'Set output = fs.CreateTextFile("{escaped}", True, True)\n'
                            'output.Write WScript.Arguments(0)\noutput.Close\nWScript.Quit 0\n', encoding="utf-16")
            browser = Path(os.environ["SystemRoot"]) / "System32" / "cscript.exe"
            require(browser.is_file(), "Windows cscript browser stub is unavailable")
            command = f'"{browser}" //Nologo "{stub}" %s'
            encoding = "utf-16"
        else:
            stub = self.results / f"{target.name}-browser-stub.py"
            stub.write_text("from pathlib import Path\nimport sys\n"
                            f"Path({str(marker)!r}).write_text(sys.argv[1], encoding='utf-8')\n", encoding="utf-8")
            command = f'"{sys.executable}" "{stub}" %s'
            encoding = "utf-8"
        return Target(target.name, target.command, dict(target.env, BROWSER=command), target.bat), marker, encoding

    def web(self, target: Target, fallback: bool, default_browser: bool = False) -> dict:
        holder = None
        if fallback:
            holder = socket.socket()
            try:
                holder.bind(("127.0.0.1", 8765))
                holder.listen(1)
            except OSError:
                holder.close()
                holder = None
                require(port_open(8765), "Could not occupy default port and no existing listener was detected")
        marker = None
        if default_browser:
            target, marker, marker_encoding = self.browser_stub(target)
        label = "default-browser" if default_browser else "fallback" if fallback else "readonly"
        service = Service(target, self.cwd, self.results / f"{target.name}-{label}.log",
                          [] if default_browser else ["serve", "--port", "8765" if fallback else "0", "--no-browser"])
        extraction_before = {p.name for p in self.runtime.glob("_MEI*")}
        metadata = {}
        failure = None
        cleanup_failure = None
        try:
            port = service.start()
            require(not fallback or port != 8765, "Occupied default port was not replaced")
            if marker:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and not marker.is_file():
                    time.sleep(0.1)
                require(marker.is_file(), "No-argument startup did not dispatch the observable browser stub")
                require(marker.read_text(encoding=marker_encoding) == f"http://127.0.0.1:{port}",
                        "Browser was not opened at the actual selected port")
                metadata["browser_dispatch"] = "actual subprocess dispatched configured stub; OS default GUI not tested"
            metadata.update(exercise_web(port, self.reference, self.install / "examples"))
            metadata.update(actual_port=port, requested_port=8765 if fallback else 0, no_browser=not default_browser,
                            arguments=[] if default_browser else service.args)
            extraction_during = {p.name for p in self.runtime.glob("_MEI*")} - extraction_before
            if self.mode == "onefile":
                require(bool(extraction_during), "onefile extraction was not observed in the writable user temporary directory")
            metadata["extraction_directories_observed"] = sorted(extraction_during)
        except BaseException as exc:
            failure = exc
        finally:
            try:
                metadata["shutdown"] = service.stop()
                remaining = {p.name for p in self.runtime.glob("_MEI*")} - extraction_before
                require(not remaining, f"onefile temporary extraction was left behind: {sorted(remaining)}")
                metadata["extraction_cleanup"] = "verified"
            except BaseException as exc:
                cleanup_failure = exc
            finally:
                if holder:
                    holder.close()
        if failure is not None or cleanup_failure is not None:
            output = service.log.read_bytes().decode("utf-8", "replace")[-4000:] if service.log.exists() else ""
            details = f"{type(failure).__name__}: {failure}" if failure is not None else ""
            if cleanup_failure is not None:
                details += f"; cleanup: {type(cleanup_failure).__name__}: {cleanup_failure}"
            raise SmokeFailure(f"{details}; server output: {output}") from (failure or cleanup_failure)
        return metadata

    def missing_python(self, bat: Path) -> dict:
        env = no_python_environment(self.env)
        require(shutil.which("python", path=env["PATH"]) is None and shutil.which("py", path=env["PATH"]) is None,
                "No-Python test PATH still contains an interpreter")
        target = Target("source-BAT-no-Python", bat_command(bat), env, True)
        runs = []
        for args in ([], ["--help"]):
            result = run_command(target, args, self.cwd)
            text = (result.stdout + result.stderr).decode("utf-8", "replace")
            require(result.returncode != 0, "Missing interpreter should have returned an error")
            require("Python" in text and "EXE" in text.upper() and "github.com" in text.lower(),
                    f"Missing-interpreter message does not explain where to download the portable EXE: {text}")
            runs.append({"arguments": args, "exit_code": result.returncode})
        return {"runs": runs, "stdin": "DEVNULL", "python_and_py_not_in_path": True,
                "download_guidance": "verified"}

    def run(self) -> None:
        bat = self.install / "Start-NetAudit.bat"
        if self.mode == "source":
            direct_env = dict(self.env, PYTHONPATH=str(self.install))
            targets = [Target("source-python", [sys.executable, "-m", "netaudit"], direct_env)]
            if WINDOWS:
                bat_env = dict(self.env)
                bat_env.pop("PYTHONPATH", None)
                targets.append(Target("source-BAT", bat_command(bat), bat_env, True))
                self.check("missing Python gives guidance without pausing", "source-BAT", lambda: self.missing_python(bat))
            else:
                self.report["not_tested"].append("Windows BAT source launcher (host is not Windows)")
        else:
            env = no_python_environment(self.env)
            require(shutil.which("python", path=env["PATH"]) is None and shutil.which("py", path=env["PATH"]) is None,
                    "Frozen no-Python PATH still resolves an interpreter")
            targets = [Target(f"{self.mode}-EXE-no-Python", [str(self.install / "NetAudit.exe")], env),
                       Target(f"{self.mode}-BAT-no-Python", bat_command(bat), env, True)]
            self.report["python_independence"] = "EXE/BAT child PATH excludes Python, py and Python-related environment variables; host still has build Python installed"
        for target in targets:
            self.check("CLI vendors, three exports and exit codes 0/1/2; no pause", target.name,
                       lambda target=target: self.cli(target))
            self.check("occupied default port, resources, audit API and process cleanup", target.name,
                       lambda target=target: self.web(target, True))
            self.check("no arguments start web and dispatch browser at actual port", target.name,
                       lambda target=target: self.web(target, True, True))
        restore = None
        try:
            restore = readonly_directory(self.install)
            for target in targets:
                self.check("read-only application directory with writable user temporary directory", target.name,
                           lambda target=target: self.web(target, False))
        except Exception as exc:
            self.check("read-only permissions enforced", self.mode, lambda: (_ for _ in ()).throw(exc))
        finally:
            if restore:
                restore()


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--source", type=Path, help="source project directory")
    mode.add_argument("--onedir", type=Path, help="onedir NetAudit.exe path (Windows only)")
    mode.add_argument("--onefile", type=Path, help="onefile NetAudit.exe path (Windows only)")
    parser.add_argument("--report", type=Path, required=True, help="machine-readable acceptance report")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    mode = "source" if args.source else "onedir" if args.onedir else "onefile"
    reference = Path(__file__).resolve().parents[1] / "netaudit" / "web"
    report = {"schema": 1, "mode": mode, "platform": platform.platform(), "machine": platform.machine(),
              "python": sys.version, "checks": [], "not_tested": [
                  "Actual OS default-browser GUI launch and interactive file picker/filter/export clicks; real no-argument processes dispatch an observable configured browser stub",
                  "A separate Windows computer with Python physically absent; subprocess no-Python PATH checks do not uninstall host build Python"],
              "path_case": "application/config/report/runtime locations contain Chinese characters and spaces; external working directory"}
    if WINDOWS:
        import ctypes
        report["windows_process_is_admin"] = bool(ctypes.windll.shell32.IsUserAnAdmin())
        if report["windows_process_is_admin"]:
            report["not_tested"].append("A standard non-administrator Windows account; this runner is administrative, with write-deny ACLs applied during read-only checks")
    console_allocated = False
    try:
        require(mode == "source" or WINDOWS, "Windows EXE acceptance must run on a real Windows host")
        if WINDOWS:
            # GitHub Actions may start this script without a console. Windows
            # CTRL_BREAK_EVENT needs a shared console even with redirected IO.
            import ctypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            if kernel.GetConsoleCP() == 0:
                require(bool(kernel.AllocConsole()), f"Cannot allocate console for CTRL_BREAK_EVENT: {ctypes.get_last_error()}")
                console_allocated = True
            report["console_allocated_for_process_group_signals"] = console_allocated
        with tempfile.TemporaryDirectory(prefix="NetAudit-便携 验收-") as directory:
            root = Path(directory)
            install = root / "迁移后 中文 程序目录"
            if mode == "source":
                project = args.source.resolve()
                install.mkdir()
                for name in ("netaudit", "examples"):
                    shutil.copytree(project / name, install / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                if (project / "Start-NetAudit.bat").exists():
                    shutil.copyfile(project / "Start-NetAudit.bat", install / "Start-NetAudit.bat")
            else:
                executable = (args.onedir or args.onefile).resolve()
                require(executable.name == "NetAudit.exe", "Expected executable named NetAudit.exe")
                require(executable.is_file(), f"Executable does not exist: {executable}")
                report["executable_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
                # base_library.zip is a required PyInstaller runtime file;
                # migration must preserve ZIP files inside the application.
                shutil.copytree(executable.parent, install, ignore=shutil.ignore_patterns("__pycache__"))
                if mode == "onedir":
                    libraries = list(executable.parent.rglob("base_library.zip"))
                    require(bool(libraries), "onedir package is missing base_library.zip")
                    migrated_libraries = {}
                    for library in libraries:
                        relative = library.relative_to(executable.parent)
                        copied = install / relative
                        require(copied.is_file(), f"Migration lost required runtime file: {relative}")
                        digest = hashlib.sha256(library.read_bytes()).hexdigest()
                        require(hashlib.sha256(copied.read_bytes()).hexdigest() == digest,
                                f"Migrated runtime file differs from the original: {relative}")
                        migrated_libraries[str(relative)] = digest
                    report["migration_base_libraries_sha256"] = migrated_libraries
                require((install / "Start-NetAudit.bat").is_file(), "BAT must be next to packaged EXE before acceptance")
            Harness(report, root, install, reference, mode).run()
    except Exception as exc:
        report["fatal_error"] = f"{type(exc).__name__}: {exc}"
        print(report["fatal_error"], flush=True)
    finally:
        if console_allocated:
            kernel.FreeConsole()
    report["passed"] = "fatal_error" not in report and bool(report["checks"]) and all(c["status"] == "passed" for c in report["checks"])
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
