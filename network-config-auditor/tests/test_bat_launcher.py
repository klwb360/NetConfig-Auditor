import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest

PROJECT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('launcher_smoke',PROJECT/'tools'/'smoke_portable.py')
smoke=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=smoke
spec.loader.exec_module(smoke)

class BatLauncherTests(unittest.TestCase):
    def test_launcher_has_windows_line_endings(self):
        for launcher in ('Start-NetConfig-Auditor.bat', 'Start-NetAudit.bat'):
            with self.subTest(launcher=launcher):
                raw=(PROJECT/launcher).read_bytes()
                self.assertEqual(raw.count(b'\r\n'),raw.count(b'\n'),'cmd.exe cannot reliably parse this UTF-8 launcher with LF-only lines')
    @unittest.skipUnless(os.name=='nt','Actual BAT execution requires Windows')
    def test_real_launcher_runs_cli_from_unicode_path(self):
        env=dict(os.environ,PATH=str(Path(sys.executable).parent)+';'+str(Path(os.environ['SystemRoot'])/'System32'),PYTHONUTF8='1')
        from netaudit import __version__
        for launcher in ('Start-NetConfig-Auditor.bat', 'Start-NetAudit.bat'):
            with self.subTest(launcher=launcher):
                target=smoke.Target('launcher',smoke.bat_command(PROJECT/launcher),env,True)
                result=subprocess.run(target.argv(['--version']),env=env,capture_output=True,timeout=30)
                self.assertEqual(result.returncode,0,result.stderr.decode('utf-8','replace'))
                self.assertEqual(result.stdout.decode('utf-8').strip(),'NetConfig Auditor '+__version__)

    @unittest.skipUnless(os.name=='nt','Actual BAT execution requires Windows')
    def test_compatibility_launcher_preserves_nonzero_cli_exit(self):
        env=dict(os.environ,PATH=str(Path(sys.executable).parent)+';'+str(Path(os.environ['SystemRoot'])/'System32'),PYTHONUTF8='1')
        for launcher in ('Start-NetConfig-Auditor.bat', 'Start-NetAudit.bat'):
            with self.subTest(launcher=launcher):
                target=smoke.Target('launcher',smoke.bat_command(PROJECT/launcher),env,True)
                result=subprocess.run(target.argv(['audit', 'nonexistent-config.cfg']),env=env,capture_output=True,timeout=30)
                self.assertEqual(result.returncode,2)

if __name__=='__main__':
    unittest.main()
