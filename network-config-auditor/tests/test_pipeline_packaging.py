"""Verify the redistribution includes the actual intelligence and attribution."""

import importlib.util
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_windows_pipeline", PROJECT / "tools" / "build_windows.py")
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class PipelinePackagingTests(unittest.TestCase):
    def test_builder_brand_import_does_not_pollute_locked_environment_metadata(self):
        # Editable source tests leave egg-info beside the app. Importing the
        # brand must not make it appear installed in the separate build venv.
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "tools").mkdir()
            shutil.copy2(PROJECT / "tools" / "build_windows.py", project / "tools" / "build_windows.py")
            shutil.copytree(PROJECT / "netaudit", project / "netaudit",
                            ignore=shutil.ignore_patterns("__pycache__", "web", "data"))
            egg = project / "source_fixture.egg-info"
            egg.mkdir()
            (egg / "PKG-INFO").write_text("Metadata-Version: 2.1\nName: netconfig-source-metadata-fixture\nVersion: 1.1.1\n", encoding="utf-8")
            script = """
import importlib.metadata as metadata
import runpy
import sys
before = {(d.metadata['Name'], d.version) for d in metadata.distributions()}
builder = runpy.run_path(sys.argv[1])
after = {(d.metadata['Name'], d.version) for d in metadata.distributions()}
assert builder['APPLICATION_NAME'] == 'NetConfig Auditor'
assert after == before, 'Source metadata leaked into the locked build environment: ' + repr(after - before)
"""
            result = subprocess.run([sys.executable, "-I", "-c", script, str(project / "tools" / "build_windows.py")],
                                    cwd=project, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_new_distribution_keeps_canonical_and_compatible_launchers(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            BUILD.add_user_files(destination)
            for launcher in ("Start-NetConfig-Auditor.bat", "Start-NetAudit.bat"):
                self.assertEqual((destination / launcher).read_bytes(), (PROJECT / launcher).read_bytes())
            self.assertFalse((destination / "NetAudit.exe").exists())

    def test_builder_passes_new_executable_name_and_product_metadata_to_pyinstaller(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            executable = work / "dist-onefile" / "NetConfig-Auditor.exe"
            executable.parent.mkdir()
            executable.write_bytes(b"MZ fixture executable")
            with patch.object(BUILD, "run") as command, patch.object(BUILD, "add_user_files"):
                self.assertEqual(BUILD.build_executable("onefile", work), executable)
            args = command.call_args.args[0]
            self.assertEqual(args[args.index("--name") + 1], "NetConfig-Auditor")
            metadata = Path(args[args.index("--version-file") + 1]).read_text(encoding="utf-8")
            self.assertIn("StringStruct('ProductName', 'NetConfig Auditor')", metadata)
            self.assertIn("StringStruct('FileDescription', 'NetConfig Auditor')", metadata)
            self.assertIn("StringStruct('OriginalFilename', 'NetConfig-Auditor.exe')", metadata)

    def test_windows_newline_checkout_preserves_official_snapshot_and_hash(self):
        # A Windows Git checkout may have core.autocrlf=true. Intelligence is
        # verified against the upstream raw bytes, so converting LF to CRLF
        # would make a genuine official snapshot fail its integrity check.
        with tempfile.TemporaryDirectory(prefix="Git 换行 验收 ") as directory:
            repository = Path(directory) / "源 仓库"
            repository.mkdir()
            data = repository / "netaudit" / "data"
            data.mkdir(parents=True)
            attributes = (PROJECT / ".gitattributes").read_bytes()
            (repository / ".gitattributes").write_bytes(attributes)
            snapshot = b'{\n  "catalogVersion": "fixture",\n  "vulnerabilities": []\n}\n'
            resources = {
                "kev.json": snapshot,
                "kev-source.json": (json.dumps({"sha256": hashlib.sha256(snapshot).hexdigest()}, indent=2) + "\n").encode(),
                "KEV-LICENSE.txt": b"CC0-1.0 fixture attribution\nRaw upstream bytes must be retained.\n",
                "KEV-NOTICE.txt": b"Synthetic checkout regression fixture.\nNot an actual intelligence catalog.\n",
            }
            for name, content in resources.items():
                (data / name).write_bytes(content)
            (repository / "normal-text.txt").write_bytes(b"normal text control\nsecond line\n")

            def git(*args):
                return subprocess.run(["git", *args], cwd=repository, check=True,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout

            git("init", "--quiet")
            git("-c", "core.autocrlf=false", "add", ".")
            names = ["netaudit/data/" + name for name in resources]
            actual_attributes = git("check-attr", "text", "--", *names).decode().splitlines()
            self.assertEqual(actual_attributes, [name + ": text: unset" for name in names])
            checkout = Path(directory) / "Windows 检出"
            checkout.mkdir()
            git("-c", "core.autocrlf=true", "checkout-index", "--all", "--force",
                "--prefix=" + checkout.as_posix() + "/")
            # Prove this checkout really enabled CRLF conversion for ordinary
            # text, rather than merely comparing another unchanged LF copy.
            self.assertEqual((checkout / "normal-text.txt").read_bytes(),
                             b"normal text control\r\nsecond line\r\n")
            for name, expected in resources.items():
                actual = (checkout / "netaudit" / "data" / name).read_bytes()
                self.assertEqual(actual, expected)
                self.assertEqual(hashlib.sha256(actual).digest(), hashlib.sha256(expected).digest())
            manifest = json.loads((checkout / "netaudit" / "data" / "kev-source.json").read_bytes())
            self.assertEqual(manifest["sha256"], hashlib.sha256((checkout / "netaudit" / "data" / "kev.json").read_bytes()).hexdigest())
            # The release source uses git archive. The same tracked attributes
            # and unchanged intelligence bytes must also reach that archive.
            tree = git("write-tree").decode().strip()
            # Keep archive byte expectations independent of system/global
            # autocrlf; the checkout control above still explicitly tests true.
            with zipfile.ZipFile(io.BytesIO(git("-c", "core.autocrlf=false", "archive", "--format=zip", tree))) as archive:
                self.assertEqual(archive.read(".gitattributes"), attributes)
                for name, expected in resources.items():
                    self.assertEqual(archive.read("netaudit/data/" + name), expected)

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
