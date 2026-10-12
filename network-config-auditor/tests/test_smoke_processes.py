"""Regression checks for Windows smoke-test process identity on any host OS."""
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from tools import smoke_portable as smoke


class FakeWindowsTree(smoke.WindowsProcessTree):
    """Keep the real tree policy while replacing only Windows API boundaries."""

    def __init__(self, entries, created, parent_pid=100):
        self.entries = entries
        self.created = created
        self.opened = []
        self.closed = []
        self.handles_alive = set()
        super().__init__(parent_pid, parent_handle="original-launcher-handle")

    def _configure_api(self):
        pass

    def _snapshot(self):
        return self.entries

    def _open_record(self, pid, entry, existing_handle=None):
        self.opened.append((pid, existing_handle))
        created = self.created[pid]
        if isinstance(created, Exception):
            raise created
        if created is None:
            return None
        handle = f"original-process-{pid}-{created}"
        self.handles_alive.add(handle)
        return {"pid": pid, "parent_pid": entry.get("parent_pid"),
                "image": entry.get("image", "unknown"),
                "created_ticks": created, "handle": handle}

    def _handle_alive(self, handle):
        return handle in self.handles_alive

    def _exit_code(self, handle):
        return 259 if self._handle_alive(handle) else 0

    def _close_handle(self, handle):
        self.closed.append(handle)


def entry(parent_pid, image="NetAudit.exe"):
    return {"parent_pid": parent_pid, "image": image}


class WindowsProcessTreeTests(unittest.TestCase):
    def test_historical_parent_pid_reuse_is_excluded_from_tree(self):
        tree = FakeWindowsTree({100: entry(10, "cmd.exe"),
                                200: entry(100, "unrelated-old-process.exe"),
                                201: entry(100), 202: entry(200)},
                               {100: 1000, 200: 900, 201: 1100, 202: 1200})
        try:
            self.assertEqual(tree.pids, {100, 201})
            self.assertEqual(tree.opened, [(100, "original-launcher-handle"),
                                           (200, None), (201, None)])
            self.assertEqual(tree.closed, ["original-process-200-900"])
            self.assertEqual(tree.excluded[0]["pid"], 200)
            self.assertEqual(tree.excluded[0]["parent_created_ticks"], 1000)
            self.assertIn("historical PID reuse", tree.excluded[0]["reason"])
        finally:
            tree.close()

    def test_creation_order_is_checked_against_each_immediate_parent(self):
        # A grandchild can be newer than the launcher but older than the actual
        # parent process currently using the snapshot's recorded parent PID.
        tree = FakeWindowsTree({203: entry(201), 201: entry(100),
                                100: entry(10), 202: entry(201)},
                               {100: 1000, 201: 1200, 202: 1200, 203: 1100})
        try:
            self.assertEqual(tree.pids, {100, 201, 202})
            self.assertEqual([record["pid"] for record in tree.excluded], [203])
            self.assertEqual(tree.excluded[0]["parent_created_ticks"], 1200)
        finally:
            tree.close()

    def test_original_exited_handle_stays_dead_even_if_pid_is_reused(self):
        tree = FakeWindowsTree({100: entry(10), 201: entry(100)},
                               {100: 1000, 201: 1100})
        try:
            original_handle = tree.records[201]["handle"]
            tree.handles_alive.remove(original_handle)
            # A recycled numeric PID is live now, but it is a different object.
            tree.handles_alive.add("recycled-process-201-9999")
            with patch.object(smoke, "process_alive", return_value=True) as numeric_pid_lookup:
                self.assertFalse(tree.alive(201))
                self.assertTrue(tree.alive(100))
            numeric_pid_lookup.assert_not_called()
            self.assertEqual([pid for pid, _ in tree.opened], [100, 201])
            child = next(record for record in tree.describe() if record["pid"] == 201)
            self.assertFalse(child["alive"])
            self.assertEqual(child["exit_code"], 0)
            self.assertEqual(child["created_ticks"], 1100)
            self.assertNotIn("handle", child)
        finally:
            tree.close()

    def test_exited_snapshot_entry_is_skipped(self):
        tree = FakeWindowsTree({100: entry(10), 201: entry(100)},
                               {100: 1000, 201: None})
        try:
            self.assertEqual(tree.pids, {100})
            self.assertEqual(tree.excluded, [])
        finally:
            tree.close()

    def test_close_releases_included_and_excluded_handles_once(self):
        tree = FakeWindowsTree({100: entry(10), 200: entry(100), 201: entry(100)},
                               {100: 1000, 200: 900, 201: 1100})
        tree.close()
        tree.close()
        self.assertCountEqual(tree.closed, ["original-process-100-1000",
                                            "original-process-200-900",
                                            "original-process-201-1100"])
        self.assertEqual(len(tree.closed), 3)
        self.assertTrue(all(record["handle"] is None for record in tree.records.values()))

    def test_constructor_failure_releases_already_opened_handles(self):
        tree = FakeWindowsTree.__new__(FakeWindowsTree)
        with self.assertRaisesRegex(smoke.SmokeFailure, "query failed"):
            FakeWindowsTree.__init__(tree, {100: entry(10), 201: entry(100)},
                                     {100: 1000, 201: smoke.SmokeFailure("query failed")})
        self.assertEqual(tree.closed, ["original-process-100-1000"])


class SmokeCleanupTests(unittest.TestCase):
    def test_taskkill_does_not_rebuild_an_unfiltered_parent_pid_tree(self):
        result = SimpleNamespace(returncode=5, stdout=b"output", stderr=b"access denied")
        with patch.dict(smoke.os.environ, {"SystemRoot": r"C:\Windows"}), \
                patch.object(smoke.subprocess, "run", return_value=result) as run:
            diagnostic = smoke.taskkill_process(201)
        argv = run.call_args.args[0]
        self.assertNotIn("/T", argv)
        self.assertEqual(argv[1:], ["/PID", "201", "/F"])
        self.assertEqual(diagnostic["returncode"], 5)
        self.assertIn("access denied", diagnostic["stderr"])

    def test_browser_url_waits_for_a_complete_file(self):
        expected = "http://127.0.0.1:12345"
        partial = UnicodeDecodeError("utf-16", b"\xff", 0, 1, "partial write")
        with patch.object(Path, "read_text", side_effect=[FileNotFoundError(), partial, "", expected]) as read, \
                patch.object(smoke.time, "sleep"):
            smoke.wait_for_browser_url(Path("marker.txt"), "utf-16", expected)
        self.assertEqual(read.call_count, 4)

    def test_browser_url_mismatch_fails_with_actual_contents(self):
        with patch.object(Path, "read_text", return_value="wrong-address"), \
                patch.object(smoke.time, "monotonic", side_effect=[0, 0, 11]), \
                patch.object(smoke.time, "sleep"), \
                self.assertRaisesRegex(smoke.SmokeFailure, "wrong-address"):
            smoke.wait_for_browser_url(Path("marker.txt"), "utf-16", "http://127.0.0.1:12345")

    def test_browser_url_does_not_hide_unrelated_read_permission_errors(self):
        with patch.object(Path, "read_text", side_effect=PermissionError("denied")), \
                self.assertRaises(PermissionError):
            smoke.wait_for_browser_url(Path("marker.txt"), "utf-16", "http://127.0.0.1:12345")


if __name__ == "__main__":
    unittest.main()
