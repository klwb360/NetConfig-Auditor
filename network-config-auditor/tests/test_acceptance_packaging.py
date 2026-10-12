"""Gold configurations must travel with the tracked source, not local secrets."""
from pathlib import Path
import subprocess
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
FIXTURES = sorted((PROJECT / 'benchmarks' / 'configs').glob('*.cfg'))

class AcceptancePackagingTests(unittest.TestCase):
    def test_windows_git_checkout_preserves_frozen_gold_bytes(self):
        with tempfile.TemporaryDirectory(prefix='gold-crlf-') as temporary:
            root=Path(temporary)/'repo';root.mkdir()
            (root/'.gitattributes').write_bytes((PROJECT.parent/'.gitattributes').read_bytes())
            fixture=FIXTURES[0]
            relative=Path('network-config-auditor')/fixture.relative_to(PROJECT)
            destination=root/relative;destination.parent.mkdir(parents=True)
            destination.write_bytes(fixture.read_bytes())
            def git(*args):
                return subprocess.run(['git',*args],cwd=root,capture_output=True,check=True)
            git('init','--quiet')
            git('-c','core.autocrlf=true','add','.')
            checkout=Path(temporary)/'checkout';checkout.mkdir()
            git('-c','core.autocrlf=false','checkout-index','--all','--force','--prefix='+checkout.as_posix()+'/')
            self.assertEqual((checkout/relative).read_bytes(),fixture.read_bytes(),'Windows Git must preserve frozen gold hashes')
    def test_all_fifty_gold_configs_are_tracked(self):
        self.assertEqual(len(FIXTURES), 50)
        for path in FIXTURES:
            result = subprocess.run(['git', 'ls-files', '--error-unmatch', path.relative_to(PROJECT).as_posix()], cwd=PROJECT, capture_output=True)
            self.assertEqual(result.returncode, 0, f'Gold configuration missing from tracked source: {path.name}')
    def test_real_configs_stay_ignored_but_gold_configs_do_not(self):
        result = subprocess.run(['git', 'check-ignore', 'configs/private-real-device.cfg'], cwd=PROJECT, capture_output=True)
        self.assertEqual(result.returncode, 0)
        result = subprocess.run(['git', 'check-ignore', FIXTURES[0].relative_to(PROJECT).as_posix()], cwd=PROJECT, capture_output=True)
        self.assertEqual(result.returncode, 1, 'Synthetic gold configurations must not be ignored')

if __name__ == '__main__':
    unittest.main()
