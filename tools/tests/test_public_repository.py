"""Publishing is bound to the explicitly authorized public migration target."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('public_publisher', Path(__file__).parents[1] / 'publish_release.py')
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)

class RepositoryAPI:
    def __init__(self, name='klwb360/NetConfig-Auditor', private=False):
        self.repository = name
        self.private = private
    def repo(self, path):
        if path:
            raise AssertionError('Repository validation must not mutate or inspect releases')
        return {'full_name': self.repository, 'private': self.private}

class PublicRepositoryTests(unittest.TestCase):
    def validator(self):
        validator = getattr(publisher, 'validate_public_repository', None)
        self.assertTrue(callable(validator), 'Public target validation is not implemented')
        return validator
    def test_expected_public_repository_is_accepted(self):
        self.validator()(RepositoryAPI())
    def test_private_repository_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'public'):
            self.validator()(RepositoryAPI(private=True))
    def test_unrelated_repository_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'NetConfig-Auditor'):
            self.validator()(RepositoryAPI(name='other/project'))
    def test_legacy_repository_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'NetConfig-Auditor'):
            self.validator()(RepositoryAPI(name='klwb360/NetAudit', private=True))

if __name__ == '__main__':
    unittest.main()
