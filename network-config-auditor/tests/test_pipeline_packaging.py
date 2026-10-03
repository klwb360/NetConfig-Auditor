"""Verify the redistribution includes the actual intelligence and attribution."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_windows_pipeline", PROJECT / "tools" / "build_windows.py")
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class PipelinePackagingTests(unittest.TestCase):
    def test_distribution_preserves_real_snapshot_and_its_attribution(self):
        with tempfile.TemporaryDirectory(prefix="发行 资源 ") as directory:
            destination = Path(directory) / "迁移后 程序"
            BUILD.add_user_files(destination)
            original = PROJECT / "netaudit" / "data"
            distributed = destination / "intelligence-data"
            self.assertTrue(distributed.is_dir())
            for resource in original.rglob("*"):
                if resource.is_file():
                    self.assertEqual((distributed / resource.relative_to(original)).read_bytes(), resource.read_bytes())
            catalog = json.loads((distributed / "kev.json").read_text(encoding="utf-8"))
            self.assertGreater(len(catalog["vulnerabilities"]), 1000)
            self.assertEqual((destination / "LICENSE").read_bytes(), (PROJECT / "LICENSE").read_bytes())
            self.assertEqual((destination / "NOTICE").read_bytes(), (PROJECT / "NOTICE").read_bytes())
            self.assertTrue(any("LICENSE" in entry.name for entry in distributed.iterdir()))
            self.assertEqual((destination / "docs" / "WINDOWS.md").read_bytes(), (PROJECT / "docs" / "WINDOWS.md").read_bytes())


if __name__ == "__main__":
    unittest.main()
