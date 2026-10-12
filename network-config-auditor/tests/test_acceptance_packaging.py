"""Gold configurations must travel with the tracked source, not local secrets."""
from pathlib import Path
import subprocess
import unittest

PROJECT = Path(__file__).resolve().parents[1]
FIXTURES = sorted((PROJECT / 'benchmarks' / 'configs').glob('*.cfg'))

class AcceptancePackagingTests(unittest.TestCase):
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
