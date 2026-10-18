"""Offline tests; all detection samples are deliberately fictitious."""
import unittest
import pathlib
import re
import tempfile
from check_public import ROOT, categories, commits_from_input, load_local_deny


class PublicScanTest(unittest.TestCase):
    def test_categories(self):
        samples = {
            'abs_path': ['/Users/example/', '/home/example/', '/workspace/example/', '/root/example/', '/private/var/example', '/tmp/example-run/', '~/codex-jobs/example', r'C:\example', r'D:\example'],
            'holdout_location': ['holdout-sealed', 'holdout-work', 'holdout job=example', 'holdout job 123', 'holdout directory example', 'holdout at example.local', '留出目录 /example/data', '/example/holdout/data'],
            'word_private': ['private'],
            'word_hpo': ['HpO'],
            'deploy_secrets': ['deploy/secrets', 'secrets/example'],
            'credential': ['AKIA'+'EXAMPLE0'*2, 'sk-'+'EXAMPLE0'*4, 'ghp_'+'EXAMPLE0'*4, 'gho_'+'EXAMPLE0'*4, 'ghs_'+'EXAMPLE0'*4, 'github_pat_'+'EXAMPLE0'*4, 'xoxb-'+'EXAMPLE0'*4, 'AIza'+'EXAMPLE0'*4, 'eyJEXAMPLE.EXAMPLE.EXAMPLE', '-----BEGIN EXAMPLE PRIVATE KEY-----', 'Bearer '+'EXAMPLE0'*4, 'password = EXAMPLE_ONLY', 'secret = EXAMPLE_ONLY', 'api_key = EXAMPLE_ONLY', 'access_token = EXAMPLE_ONLY', 'refresh_token = EXAMPLE_ONLY', 'auth.json'],
            'private_ip': ['10.0.0.1', '192.168.0.1', '172.16.0.1', '172.31.255.254'],
            'hostname': ['example.local'],
        }
        for category, examples in samples.items():
            for example in examples:
                with self.subTest(category=category, example=example):
                    self.assertIn(category, categories(example))

    def test_clean(self):
        self.assertEqual(categories('data/evals/example: public score = 0.75; 172.32.0.1'), set())
        self.assertEqual(categories('DELETE /users/7 is an HTTP example'), set())

    def test_invalid_input_blocks(self):
        with self.assertRaises(ValueError):
            commits_from_input(['invalid'], 'origin/main..HEAD')

    def test_local_deny(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as folder:
            path = pathlib.Path(folder) / 'deny'
            path.write_text(r'\bEXAMPLEHOST01\b' + '\n\n', encoding='utf-8')
            rules = load_local_deny(path)
            self.assertEqual(categories('EXAMPLEHOST01', rules), {'local_deny'})
            self.assertEqual(categories('examplehost01', rules), {'local_deny'})
            self.assertEqual(categories('EXAMPLEHOST02', rules), set())
            self.assertEqual(categories('EXAMPLEHOST01'), set())

    def test_optional_local_deny(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as folder:
            path = pathlib.Path(folder) / 'deny'
            self.assertEqual(load_local_deny(path), ())
            path.write_text('', encoding='utf-8')
            self.assertEqual(load_local_deny(path), ())

    def test_invalid_local_deny_blocks(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as folder:
            path = pathlib.Path(folder) / 'deny'
            path.write_text('[', encoding='utf-8')
            with self.assertRaises(re.error):
                load_local_deny(path)


if __name__ == '__main__':
    unittest.main()
