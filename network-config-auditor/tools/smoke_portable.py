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
from http.server import BaseHTTPRequestHandler, HTTPServer
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
import threading
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


class WindowsProcessTree:
    """Track process objects, not recyclable PIDs, until shutdown is verified."""

    def __init__(self, parent_pid: int, parent_handle=None):
        self.records: dict[int, dict] = {}
        self.excluded: list[dict] = []
        self._configure_api()
        try:
            entries = self._snapshot()
            root = self._open_record(parent_pid, entries.get(parent_pid, {}), parent_handle)
            require(root is not None, f"Cannot inspect launcher process {parent_pid}")
            self.records[parent_pid] = root
            seen = {parent_pid}
            while True:
                added = False
                for pid, entry in entries.items():
                    parent = self.records.get(entry["parent_pid"])
                    if pid in seen or parent is None:
                        continue
                    seen.add(pid)
                    child = self._open_record(pid, entry)
                    if child is None:
                        continue  # This snapshot entry has already exited.
                    if child["created_ticks"] < parent["created_ticks"]:
                        self.excluded.append({k: v for k, v in child.items() if k != "handle"} |
                                             {"parent_created_ticks": parent["created_ticks"],
                                              "reason": "child predates current parent PID; historical PID reuse"})
                        self._close_handle(child["handle"])
                        continue
                    self.records[pid] = child
                    added = True
                if not added:
                    break
        except BaseException:
            self.close()
            raise

    def _configure_api(self) -> None:
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.wintypes = ctypes, wintypes
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        self.kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
        self.kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.GetCurrentProcess.argtypes = []
        self.kernel.GetCurrentProcess.restype = wintypes.HANDLE
        self.kernel.DuplicateHandle.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
                                                ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD,
                                                wintypes.BOOL, wintypes.DWORD]

    def _snapshot(self) -> dict[int, dict]:
        ctypes, wintypes = self.ctypes, self.wintypes

        class ProcessEntry(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                        ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                        ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

        self.kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        self.kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        snapshot = self.kernel.CreateToolhelp32Snapshot(2, 0)
        require(snapshot not in (None, ctypes.c_void_p(-1).value), "Unable to inspect Windows process tree")
        entries = {}
        try:
            entry = ProcessEntry()
            entry.dwSize = ctypes.sizeof(entry)
            more = self.kernel.Process32FirstW(snapshot, ctypes.byref(entry))
            while more:
                entries[int(entry.th32ProcessID)] = {"parent_pid": int(entry.th32ParentProcessID),
                                                      "image": entry.szExeFile}
                more = self.kernel.Process32NextW(snapshot, ctypes.byref(entry))
            require(ctypes.get_last_error() == 18, "Windows process snapshot did not finish normally")
        finally:
            self._close_handle(snapshot)
        return entries

    def _open_record(self, pid: int, entry: dict, existing_handle=None) -> dict | None:
        ctypes, wintypes = self.ctypes, self.wintypes
        # SYNCHRONIZE lets us inspect the original object's signaled state.
        if existing_handle is not None:
            duplicate = wintypes.HANDLE()
            current = self.kernel.GetCurrentProcess()
            require(bool(self.kernel.DuplicateHandle(current, existing_handle, current,
                                                      ctypes.byref(duplicate), 0, False, 2)),
                    f"DuplicateHandle({pid}) failed with Windows error {ctypes.get_last_error()}")
            handle = duplicate.value
        else:
            handle = self.kernel.OpenProcess(0x1000 | 0x100000, False, pid)
        if not handle:
            error = ctypes.get_last_error()
            require(error == 87, f"OpenProcess({pid}) failed with Windows error {error}")
            return None
        try:
            created, exited, system, user = (wintypes.FILETIME() for _ in range(4))
            require(bool(self.kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                                     ctypes.byref(system), ctypes.byref(user))),
                    f"GetProcessTimes({pid}) failed with Windows error {ctypes.get_last_error()}")
            return {"pid": pid, "parent_pid": entry.get("parent_pid"), "image": entry.get("image", "unknown"),
                    "created_ticks": (int(created.dwHighDateTime) << 32) | int(created.dwLowDateTime),
                    "handle": handle}
        except BaseException:
            self._close_handle(handle)
            raise

    def _handle_alive(self, handle) -> bool:
        state = self.kernel.WaitForSingleObject(handle, 0)
        require(state in (0, 258), f"WaitForSingleObject failed with Windows error {self.ctypes.get_last_error()}")
        return state == 258

    def _exit_code(self, handle) -> int:
        code = self.wintypes.DWORD()
        require(bool(self.kernel.GetExitCodeProcess(handle, self.ctypes.byref(code))),
                f"GetExitCodeProcess failed with Windows error {self.ctypes.get_last_error()}")
        return int(code.value)

    def _close_handle(self, handle) -> None:
        self.kernel.CloseHandle(handle)

    @property
    def pids(self) -> set[int]:
        return set(self.records)

    def alive(self, pid: int) -> bool:
        return self._handle_alive(self.records[pid]["handle"])

    def describe(self) -> list[dict]:
        return [{k: v for k, v in record.items() if k != "handle"} |
                {"alive": self._handle_alive(record["handle"]), "exit_code": self._exit_code(record["handle"])}
                for record in self.records.values()]

    def close(self) -> None:
        for record in self.records.values():
            if record["handle"] is not None:
                self._close_handle(record["handle"])
                record["handle"] = None


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


def taskkill_process(pid: int) -> dict:
    result = subprocess.run([str(Path(os.environ["SystemRoot"]) / "System32" / "taskkill.exe"),
                             "/PID", str(pid), "/F"],
                            stdin=subprocess.DEVNULL, capture_output=True, timeout=15)
    return {"pid": pid, "returncode": result.returncode,
            "stdout": result.stdout.decode("utf-8", "replace")[-1500:],
            "stderr": result.stderr.decode("utf-8", "replace")[-1500:]}


def kill_tree(process: subprocess.Popen) -> list[dict]:
    diagnostics = []
    if WINDOWS:
        tree = None
        try:
            tree = WindowsProcessTree(process.pid, int(process._handle))
            for pid in [process.pid, *sorted(tree.pids - {process.pid})]:
                if tree.alive(pid):
                    diagnostics.append(taskkill_process(pid))
        except Exception as exc:
            # Diagnostic failures still trigger cleanup of the live launcher.
            diagnostics.append({"inspection_error": f"{type(exc).__name__}: {exc}"})
            if process.poll() is None:
                diagnostics.append(taskkill_process(process.pid))
        finally:
            if tree:
                tree.close()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=15)
    return diagnostics


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
        tree = None
        inspection_error = None
        try:
            if WINDOWS:
                tree = WindowsProcessTree(process.pid, int(process._handle))
                pids = tree.pids
        except Exception as exc:
            # Snapshot errors must not prevent terminating the actual server.
            inspection_error = str(exc)
        alive = tree.alive if tree else process_alive
        forced = False
        signal_error = None
        kill_diagnostics = []
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
                kill_diagnostics.extend(kill_tree(process))
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and (any(alive(pid) for pid in pids)
                                                  or self.port is not None and port_open(self.port)):
                time.sleep(0.1)
            remaining = sorted(pid for pid in pids if alive(pid))
            # Kill descendants even if their original launcher has exited.
            for pid in remaining:
                forced = True
                if WINDOWS:
                    # The retained original handle prevents targeting an
                    # unrelated process that later reuses this PID.
                    if alive(pid):
                        kill_diagnostics.append(taskkill_process(pid))
                else:
                    os.kill(pid, signal.SIGKILL)
            if remaining:
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and any(alive(pid) for pid in pids):
                    time.sleep(0.1)
            self.shutdown = {"exit_code": process.returncode, "forced_cleanup": forced,
                             "signal_error": signal_error, "process_inspection_error": inspection_error,
                             "observed_pids": sorted(pids),
                             "remaining_pids": sorted(pid for pid in pids if alive(pid)),
                             "processes": tree.describe() if tree else [],
                             "excluded_historical_pid_links": tree.excluded if tree else [],
                             "taskkill": kill_diagnostics,
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
            if tree:
                tree.close()
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


def validate_report(text: str, format_: str, vendor: str | None = None, *,
                    expected_cve: str | None = None, ai_status: str = "disabled") -> None:
    if format_ == "json":
        report = json.loads(text)
        require({"device", "summary", "findings", "inventory"} <= report.keys(), "Incomplete JSON report")
        if vendor:
            require(report["device"]["vendor"] == vendor, f"Wrong vendor in report: {report['device']}")
        validate_pipeline(report, expected_cve=expected_cve, ai_status=ai_status)
    elif format_ == "md":
        require(text.startswith("# 网络配置审计报告") and "配置清单" in text, "Incomplete Markdown export")
    else:
        require(text.lower().startswith("<!doctype html>") and "</html>" in text and "网络配置审计报告" in text,
                "Incomplete HTML export")
    if format_ != "json":
        for section in ("审计流程", "网络架构检查", "CVE / KEV 情报", "AI 解释与整改建议"):
            require(section in text, f"Missing pipeline export section: {section}")


def validate_pipeline(report: dict, *, expected_cve: str | None = None, ai_status: str = "disabled") -> None:
    require([item.get("stage") for item in report.get("pipeline", [])] ==
            ["parser", "architecture", "security", "intelligence", "ai", "reports"],
            "Incomplete or out-of-order audit pipeline")
    domains = report.get("architecture", {}).get("domains", [])
    require({item.get("domain") for item in domains} ==
            {"vlan", "stp", "ospf", "acl", "nat", "management_plane"}, "Incomplete architecture domains")
    intel = report.get("intelligence", {})
    require(isinstance(intel.get("sources"), list) and bool(intel["sources"]),
            "Bundled KEV source/provenance was not loaded")
    sources = [item for item in intel["sources"] if item.get("kind") == "kev"]
    require(len(sources) == 1 and sources[0].get("origin") == "bundled-official-snapshot",
            "Runtime did not load the bundled official KEV snapshot")
    reference_kev = Path(__file__).resolve().parents[1] / "netaudit" / "data" / "kev.json"
    require(sources[0].get("sha256") == hashlib.sha256(reference_kev.read_bytes()).hexdigest(),
            "Runtime KEV differs from the committed source snapshot")
    require(report.get("ai", {}).get("status") == ai_status, "Unexpected AI state")
    if expected_cve is None:
        require(not intel.get("matches"), "Default audit invented a precise vulnerability match")
        require(intel.get("status") == "not-configured", "Default report does not disclose missing asset/NVD evidence")
    else:
        matches = [item for item in intel.get("matches", []) if item.get("cve_id") == expected_cve]
        require(len(matches) == 1, f"Exact local NVD CPE/version match missing for {expected_cve}")
        require(matches[0].get("known_exploited") is True, "Real bundled KEV did not enrich the matched CVE")
        require(matches[0].get("confidence") == "cpe-version-match", "NVD match lacks precise version confidence")


def pipeline_fixture() -> tuple[dict, dict]:
    """Synthetic NVD applicability, real KEV CVE; this is an engine fixture."""
    cpe = "cpe:2.3:o:cisco:ios_xe:16.12.1:*:*:*:*:*:*:*"
    asset = {"cpe": cpe}
    nvd = {"format": "NVD_CVE", "version": "2.0", "timestamp": "2026-10-03T00:00:00.000",
           "vulnerabilities": [{"cve": {
               "id": "CVE-2023-20198", "sourceIdentifier": "smoke-fixture@netaudit.invalid",
               "published": "2023-10-16T00:00:00.000", "lastModified": "2026-10-03T00:00:00.000",
               "vulnStatus": "Analyzed",
               "descriptions": [{"lang": "en", "value": "Synthetic applicability fixture; not a vendor vulnerability assertion."}],
               "configurations": [{"nodes": [{"operator": "OR", "negate": False, "cpeMatch": [
                   {"vulnerable": True, "criteria": cpe, "matchCriteriaId": "00000000-0000-0000-0000-000000000001"}]}]}],
               "references": [{"url": "https://nvd.nist.gov/vuln/detail/CVE-2023-20198"}],
           }}]}
    return asset, nvd


def exercise_pipeline_web(port: int, headers: dict) -> dict:
    asset, nvd = pipeline_fixture()
    body = json.dumps({"vendor": "cisco", "config": "hostname PortablePipeline\nip http server\n",
                       "asset": asset, "nvd": nvd}, ensure_ascii=False)
    value = json.loads(request(port, "POST", "/api/audit", body, headers)[0])
    validate_pipeline(value["report"], expected_cve="CVE-2023-20198")
    for format_, text in value["exports"].items():
        if format_ == "json":
            require(json.loads(text) == value["report"], "Pipeline JSON export differs from API report")
        else:
            validate_report(text, format_, "cisco")
            require("CVE-2023-20198" in text, "Matched CVE was omitted from an exported report")
    return {"pipeline": [item["stage"] for item in value["report"]["pipeline"]],
            "nvd_applicability": "synthetic local exact CPE/version fixture; real bundled CISA KEV enrichment",
            "matched_cve": "CVE-2023-20198", "ai": "disabled; no model requested"}


def exercise_simulator_web(port: int, headers: dict) -> dict:
    """Exercise actual state transitions; record assertions, never raw backups."""
    vendors = ("cisco", "huawei", "h3c", "ruijie")
    for vendor in vendors:
        ios = vendor in ("cisco", "ruijie")
        separator = "!" if ios else "#"
        config = (f"{('hostname' if ios else 'sysname')} SimulatorSmoke\r\n"
                  f"{separator} keep original spacing and line endings\r\n"
                  "unknown-preserved-setting   keep-this\r\n"
                  f"{separator}\r\ninterface GigabitEthernet0/1\r\n"
                  f" description Original  spacing\r\n{separator}\r\n")
        entry, leave, finish = ("configure terminal", "exit", "end") if ios else ("system-view", "quit", "return")
        mode = "switchport mode access" if ios else "port link-type access"
        membership = "switchport access vlan" if ios else "port default vlan" if vendor == "huawei" else "port access vlan"

        def simulate(commands: str) -> dict:
            value = json.loads(request(port, "POST", "/api/simulate", json.dumps(
                {"config": config, "vendor": vendor, "commands": commands}), headers)[0])
            require(not ({"report", "exports", "findings", "pipeline", "ai"} & set(value)),
                    "Simulation unexpectedly returned an audit or AI report")
            return value

        untouched = simulate("")
        require(untouched["config"] == config and untouched["summary"]["changed"] is False,
                f"Simulator import rewrote original {vendor} backup")
        commands = "\n".join((entry, "vlan 20", leave, "interface GigabitEthernet0/1", mode,
                               membership + " 20", finish))
        accepted = simulate(commands)
        require(accepted["summary"]["changed"] is True and accepted["summary"]["rolled_back"] is False,
                f"Simulator rejected supported VLAN/interface transaction for {vendor}")
        require(accepted["context"] == {"mode": "exec", "target": ""}, "Successful simulator batch lost CLI context")
        require(accepted["inventory"]["interfaces"]["GigabitEthernet0/1"]["access_vlan"] == 20,
                "Simulation did not update interface VLAN state")
        require("vlan 20" in accepted["config"] and "unknown-preserved-setting   keep-this\r\n" in accepted["config"]
                and " description Original  spacing\r\n" in accepted["config"],
                "Simulation lost unrelated original lines or CRLF")
        for label, failed_commands in (
            ("missing VLAN", commands.replace(membership + " 20", membership + " 999")),
            ("unknown command", "\n".join((entry, "vlan 30", leave, "unknown-simulator-command", finish))),
        ):
            rejected = simulate(failed_commands)
            require(rejected["summary"]["rolled_back"] is True and rejected["summary"]["applied"] == 0
                    and rejected["config"] == config and rejected["context"] == untouched["context"]
                    and rejected["inventory"] == untouched["inventory"] and rejected["diff"] == "",
                    f"{vendor} {label} did not atomically roll back original text, state and context")
            require(any(r["status"] in ("blocked", "unsupported", "invalid") and r["reason"] and r["suggestion"]
                        for r in rejected["results"]), "Blocked simulation lacks a reason and next step")
        plan = json.loads(request(port, "POST", "/api/plan", json.dumps({"config": config, "vendor": vendor,
            "goal": "把接口 GigabitEthernet0/1 加入 VLAN 20"}), headers)[0])
        require(plan["status"] == "ready" and plan["commands"] and plan["steps"] and not plan["questions"],
                f"Chinese goal did not produce a ready, explained command draft for {vendor}")
        require(not ({"config", "report", "exports", "findings", "pipeline", "ai"} & set(plan)),
                "Planning unexpectedly applied a candidate or returned an audit")
        replay = simulate(plan["commands"])
        require(replay["config"] == accepted["config"] and replay["summary"]["rolled_back"] is False,
                "Chinese goal draft did not replay to the expected configuration")
        # Only this explicit request audits the candidate after simulation.
        audited = json.loads(request(port, "POST", "/api/audit", json.dumps({
            "config": accepted["config"], "vendor": vendor}), headers)[0])
        require(not any(f["rule_id"] == "VLAN-UNDEFINED" for f in audited["report"]["findings"]),
                "Explicit audit did not observe simulated VLAN definition")
        require(set(audited["exports"]) == {"json", "md", "html"}, "Candidate audit is missing report exports")
        for format_, content in audited["exports"].items():
            validate_report(content, format_, vendor)
    return {"vendors": list(vendors), "transaction": "committed", "missing_vlan_rollback": True,
            "unknown_command_rollback": True, "original_text_preserved": True,
            "chinese_goal": "ready", "plan_replay_matches": True, "automatic_audit": False,
            "audit_after_simulation": "explicit", "candidate_exports": ["json", "md", "html"]}


def exercise_web(port: int, reference: Path, examples: Path) -> dict:
    resources: dict[str, str] = {}
    for route, filename, mime in (("/", "index.html", "text/html"), ("/style.css", "style.css", "text/css"),
                                   ("/app.js", "app.js", "text/javascript"),
                                   ("/simulator.js", "simulator.js", "text/javascript"),
                                   ("/vendor-syntax.js", "vendor-syntax.js", "text/javascript"),
                                   ("/vendor-highlight.js", "vendor-highlight.js", "text/javascript")):
        text, headers = request(port, "GET", route)
        require(headers.get("Content-Type", "").startswith(mime), f"Wrong MIME type for {route}")
        require(text == (reference / filename).read_text(encoding="utf-8"), f"Packaged {filename} differs from source")
        resources[filename] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    token = json.loads(request(port, "GET", "/api/session")[0])["token"]
    require(isinstance(token, str) and len(token) >= 16, "Invalid session token")
    headers = {"Origin": f"http://127.0.0.1:{port}", "X-NetAudit-Token": token,
               "Content-Type": "application/json"}
    totals = {}
    rgos = {}
    detections = {}
    for vendor in ("cisco", "huawei", "h3c", "ruijie"):
        config = (examples / f"{vendor}.cfg").read_text(encoding="utf-8")
        detection = json.loads(request(port, "POST", "/api/detect", json.dumps({"config": config}), headers)[0])
        require(detection.get("status") == "detected" and detection.get("vendor") == vendor,
                f"File-import vendor detection failed for {vendor}")
        require(set(detection) == {"status", "vendor", "detection"}, "Detection API returned device content")
        detections[vendor] = detection["vendor"]
        body = json.dumps({"vendor": "auto" if vendor == "ruijie" else vendor,
                           "config": config})
        value = json.loads(request(port, "POST", "/api/audit", body, headers)[0])
        require(value["report"]["device"]["vendor"] == vendor, "Audit API selected wrong vendor")
        require(set(value["exports"]) == {"json", "md", "html"}, "Audit API missing exports")
        for format_, text in value["exports"].items():
            validate_report(text, format_, vendor)
        require(json.loads(value["exports"]["json"]) == value["report"], "JSON export differs from API report")
        totals[vendor] = value["report"]["summary"]["total"]
        if vendor == "ruijie":
            report = value["report"]
            require(len(report["inventory"]["vlans"]) == 5, "RGOS batch VLAN declaration was lost")
            require(not any(f["rule_id"] == "VLAN-UNDEFINED" for f in report["findings"]),
                    "Defined RGOS VLAN incorrectly reported missing")
            grouped = [f for f in report["findings"] if f["rule_id"] == "MGMT-VTY-SOURCE"]
            require(len(grouped) == 1 and grouped[0]["occurrences"] == 2,
                    "RGOS identical VTY source risks were not grouped")
            require(len(grouped[0]["affected_objects"]) == 2 and len(grouped[0]["command_templates"]) == 2,
                    "RGOS grouping lost VTY objects or independent scripts")
            ssh = next((f for f in report["findings"] if f["rule_id"] == "MGMT-SSHV1"), {})
            require(ssh.get("commands") == ["configure terminal\nip ssh version 2\nend"],
                    "RGOS SSH suggestion lost explicit configuration modes")
            require(all(f.get("verification_commands") and f.get("command_notes") for f in report["findings"]),
                    "RGOS findings are missing checks or command prerequisites")
            rgos = {"automatic_vendor": "ruijie", "batch_vlans": 5, "false_missing_vlan": 0,
                    "grouped_vty_occurrences": 2, "independent_vty_templates": 2,
                    "command_modes_and_prerequisites": "verified"}
    ambiguous = json.loads(request(port, "POST", "/api/detect", json.dumps({"config": "sysname LAB"}), headers)[0])
    require(ambiguous.get("status") == "needs-manual" and ambiguous.get("vendor") == "auto",
            "Ambiguous file import guessed a vendor")
    return {"resources_sha256": resources, "vendors_findings": totals,
            "file_import_detection": {"vendors": detections, "ambiguous": "needs-manual"},
            "rgos_regression": rgos,
            "simulation": exercise_simulator_web(port, headers),
            "pipeline_integration": exercise_pipeline_web(port, headers),
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


def wait_for_browser_url(marker: Path, encoding: str, expected: str, timeout: float = 10) -> None:
    """Wait for the stub to finish writing, rather than treating file creation as completion."""
    deadline = time.monotonic() + timeout
    observed = "marker not created"
    while time.monotonic() < deadline:
        try:
            value = marker.read_text(encoding=encoding)
            if value == expected:
                return
            observed = repr(value)
        except (FileNotFoundError, UnicodeError) as exc:
            observed = f"{type(exc).__name__}: {exc}"
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in (32, 33):
                raise
            observed = f"Windows marker sharing error: {exc}"
        time.sleep(0.1)
    raise SmokeFailure(f"Browser stub did not finish writing the actual URL {expected!r}: {observed}")


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
        for vendor in ("cisco", "huawei", "h3c", "ruijie"):
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
        return {"runs": runs, "simulator_cli": self.simulator_cli(target, output_dir),
                "stdin": "DEVNULL", "timeout_seconds": COMMAND_TIMEOUT,
                "external_cwd": True, "unicode_and_spaces_in_paths": True}

    def simulator_cli(self, target: Target, directory: Path) -> dict:
        config = directory / "模拟 原始备份.cfg"
        original = ("hostname SimulatorCLISmoke\r\n!\r\nunknown-setting  preserve-this\r\n!\r\n"
                    "interface GigabitEthernet0/1\r\n description Keep  original\r\n!\r\n").encode("utf-8")
        config.write_bytes(original)
        result = run_command(target, ["plan", str(config), "--vendor", "cisco", "--goal",
                                      "把接口 GigabitEthernet0/1 加入 VLAN 20"], self.cwd)
        require(result.returncode == 0, "Chinese goal CLI failed")
        plan = json.loads(result.stdout.decode("utf-8"))
        require(plan.get("status") == "ready" and plan.get("commands") and plan.get("steps"),
                "Chinese goal CLI did not return an explained ready draft")
        script = directory / "模拟 命令.txt"
        script.write_bytes(plan["commands"].encode("utf-8"))
        output = directory / "模拟 候选配置.cfg"
        result = run_command(target, ["simulate", str(config), "--vendor", "cisco", "--commands",
                                      str(script), "--out", str(output)], self.cwd)
        require(result.returncode == 0, "Supported simulation command-file CLI failed")
        simulation = json.loads(result.stdout.decode("utf-8"))
        require(simulation["summary"]["changed"] is True and simulation["summary"]["rolled_back"] is False
                and simulation["inventory"]["interfaces"]["GigabitEthernet0/1"]["access_vlan"] == 20,
                "Simulation CLI did not update the intended VLAN/interface state")
        candidate = output.read_bytes()
        require(candidate == simulation["config"].encode("utf-8")
                and b"unknown-setting  preserve-this\r\n" in candidate
                and b" description Keep  original\r\n" in candidate
                and b"\n" not in candidate.replace(b"\r\n", b""),
                "Simulation CLI output lost original text or CRLF")
        require(not ({"report", "findings", "exports", "pipeline", "ai"} & set(simulation)),
                "Simulation CLI unexpectedly returned an audit report")
        repeated = [part for command in plan["commands"].splitlines() for part in ("--command", command)]
        result = run_command(target, ["simulate", str(config), "--vendor", "cisco", *repeated], self.cwd)
        require(result.returncode == 0 and json.loads(result.stdout.decode("utf-8"))["config"] == simulation["config"],
                "Repeated --command arguments differ from command-file simulation")
        script.write_text(plan["commands"] + "\nunknown-simulator-command\n", encoding="utf-8")
        for rejected_output in (output, directory / "失败 不应创建.cfg"):
            result = run_command(target, ["simulate", str(config), "--vendor", "cisco", "--commands",
                                          str(script), "--out", str(rejected_output)], self.cwd)
            require(result.returncode == 2, "Failed simulation CLI must return exit 2 without pausing")
            rejected = json.loads(result.stdout.decode("utf-8"))
            require(rejected["summary"]["rolled_back"] is True and rejected["summary"]["applied"] == 0
                    and rejected["config"].encode("utf-8") == original,
                    "Failed CLI batch did not roll back the complete original configuration")
            require(output.read_bytes() == candidate and (rejected_output == output or not rejected_output.exists()),
                    "Failed CLI batch wrote or overwrote a candidate output")
        require(config.read_bytes() == original, "Simulation CLI modified the imported backup")
        return {"plan_ready": True, "successful_transaction": True, "command_file": True,
                "repeated_arguments": True, "crlf_preserved": True, "failed_batch_exit": 2,
                "failed_output_unchanged": True, "input_unchanged": True, "no_automatic_audit": True,
                "unicode_and_spaces_in_paths": True}

    def pipeline(self, target: Target) -> dict:
        extraction_before = {path.name for path in self.runtime.glob("_MEI*")}
        output_dir = self.results / "流程 情报 验收" / target.name
        output_dir.mkdir(parents=True)
        config = output_dir / "设备 配置.cfg"
        config.write_text("hostname PortablePipeline\nenable secret SmokeOnlySecret123\nip http server\n", encoding="utf-8")
        asset, nvd = pipeline_fixture()
        asset_path, nvd_path = output_dir / "设备 信息.json", output_dir / "离线 NVD.json"
        asset_path.write_text(json.dumps(asset), encoding="utf-8")
        nvd_path.write_text(json.dumps(nvd), encoding="utf-8")
        base_args = ["audit", str(config), "--vendor", "cisco", "--asset-info", str(asset_path),
                     "--nvd-file", str(nvd_path)]
        reference = None
        runs = []
        for format_ in ("json", "md", "html"):
            output = output_dir / ("完整 流程报告." + format_)
            result = run_command(target, [*base_args, "--format", format_, "--out", str(output)], self.cwd)
            require(result.returncode == 0, f"Pipeline CLI {format_} failed: {result.stderr.decode('utf-8', 'replace')[-1500:]}")
            content = output.read_text(encoding="utf-8")
            validate_report(content, format_, "cisco", expected_cve="CVE-2023-20198")
            require("CVE-2023-20198" in content, "Matched CVE was omitted from pipeline CLI export")
            if format_ == "json":
                reference = json.loads(content)
            runs.append({"format": format_, "exit_code": result.returncode})

        requests = []

        class ProtocolStub(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                value = json.loads(raw)
                requests.append({"path": self.path, "body": raw.decode("utf-8"), "model": value.get("model")})
                facts = json.loads(value["messages"][1]["content"])["rules"]
                items = [{"rule_id": fact["rule_id"], "explanation": "协议验收 fixture 解释；没有运行真实模型。",
                          "remediation": "协议验收 fixture 建议；实际变更需要人工核对。"} for fact in facts]
                content = json.dumps({"done": True, "message": {"role": "assistant", "content": json.dumps({"items": items})}}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

        with HTTPServer(("127.0.0.1", 0), ProtocolStub) as stub:
            stub_port = stub.server_port
            thread = threading.Thread(target=stub.serve_forever)
            thread.start()
            try:
                output = output_dir / "AI 协议报告.json"
                result = run_command(target, [*base_args, "--format", "json", "--out", str(output),
                                               "--ai-model", "netaudit-smoke-stub", "--ai-endpoint",
                                               f"http://127.0.0.1:{stub_port}", "--ai-timeout", "10"], self.cwd)
                require(result.returncode == 0, f"AI protocol CLI failed: {result.stderr.decode('utf-8', 'replace')[-1500:]}")
                ai_report = json.loads(output.read_text(encoding="utf-8"))
                validate_pipeline(ai_report, expected_cve="CVE-2023-20198", ai_status="completed")
                require(ai_report["findings"] == reference["findings"], "AI changed the rule findings")
                require(ai_report["intelligence"] == reference["intelligence"], "AI changed intelligence evidence")
                require(len(requests) == 1 and requests[0]["path"] == "/api/chat", "Unexpected model protocol requests")
                require(requests[0]["model"] == "netaudit-smoke-stub", "Model selection was not sent to protocol stub")
                for private in ("PortablePipeline", "SmokeOnlySecret123", "cpe:2.3"):
                    require(private not in requests[0]["body"], "AI protocol disclosed raw configuration or asset information")
            finally:
                stub.shutdown()
                thread.join(timeout=10)
                require(not thread.is_alive(), "AI protocol stub thread survived cleanup")
        require(not port_open(stub_port), "AI protocol stub listener survived cleanup")
        require(not ({path.name for path in self.runtime.glob("_MEI*")} - extraction_before),
                "Pipeline CLI left a onefile temporary extraction directory")
        return {"runs": runs, "stages": [item["stage"] for item in reference["pipeline"]],
                "extraction_cleanup": "verified",
                "matched_cve": "CVE-2023-20198", "nvd_applicability": "synthetic local exact CPE/version fixture",
                "kev": "real bundled CISA snapshot loaded and enriched the matched CVE",
                "ai": {"backend": "HTTP protocol stub, not an actual Ollama model", "status": "completed",
                       "rule_findings_unchanged": True, "raw_config_and_asset_not_sent": True,
                       "stub_thread_stopped": True, "stub_port_closed": True}}

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
                wait_for_browser_url(marker, marker_encoding, f"http://127.0.0.1:{port}")
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
        self.check("pipeline, exact local NVD/KEV, three reports and explicit AI protocol stub",
                   ", ".join(target.name for target in targets),
                   lambda: {"targets": {target.name: self.pipeline(target) for target in targets}})
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
                  "Actual Ollama model inference; AI integration is tested with a local HTTP protocol stub only",
                  "Live NVD applicability for the smoke asset; NVD applicability is a clearly labeled synthetic local exact-CPE fixture",
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
