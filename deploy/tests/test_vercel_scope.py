"""Execute Vercel's real ignore command against source history, not a mock."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMAND = json.loads((ROOT / 'frontend/vercel.json').read_text())['ignoreCommand']


class VercelScope(unittest.TestCase):
    def test_build_only_changed_frontend_and_fail_open_without_base(self):
        self.assertLessEqual(len(COMMAND), 256)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            front = root / 'frontend'
            front.mkdir()
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.DEVNULL, text=True).strip()
            git('init', '-q')
            git('config', 'user.name', 'Delivery test')
            git('config', 'user.email', 'delivery@example.invalid')
            (front / 'index.html').write_text('first')
            git('add', '.')
            git('commit', '-qm', 'first')
            base = git('rev-parse', 'HEAD')
            (root / 'README.md').write_text('docs only')
            (front / 'README.md').write_text('frontend docs only')
            git('add', '.')
            git('commit', '-qm', 'docs')
            def status(previous):
                return subprocess.run(['sh', '-c', COMMAND], cwd=front,
                    env={**os.environ, 'VERCEL_GIT_PREVIOUS_SHA': previous},
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
            self.assertEqual(status(base), 0)
            self.assertEqual(status(''), 0)
            self.assertEqual(status('f' * 40), 1)
            (front / 'index.html').write_text('changed')
            git('add', '.')
            git('commit', '-qm', 'frontend')
            self.assertEqual(status(base), 1)
