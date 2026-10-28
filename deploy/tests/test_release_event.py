"""Release identity, actual dependency fingerprints and post-deployment evidence."""
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release_scope import frontend_fingerprint, live_scope
import send_release
from validate_release import validate


class ReleaseEventTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Fixture')
        (self.repo / 'backend').mkdir()
        (self.repo / 'backend/uv.lock').write_text('locked')
        self.git('add', '.')
        self.git('commit', '-qm', 'Initial fixture')
        self.sha = self.git('rev-parse', 'HEAD')
        self.git('update-ref', 'refs/remotes/origin/main', self.sha)
        self.git('tag', '-am', 'Published fixture', 'v1')
        self.event = {'action': 'published', 'release': {'draft': False, 'tag_name': 'v1'}}

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.repo, text=True, stderr=subprocess.PIPE).strip()

    def verify(self, **kwargs):
        values = dict(repo=self.repo, event=self.event, revision=self.sha, ref='refs/tags/v1', event_name='release')
        values.update(kwargs)
        return validate(**values)

    def test_published_annotated_tag_resolves_to_exact_main_commit(self):
        self.assertEqual(self.verify(), self.sha)
        self.git('tag', 'v2')
        self.event['release']['tag_name'] = 'v2'
        self.assertEqual(self.verify(ref='refs/tags/v2'), self.sha)

    def test_push_draft_and_other_release_actions_cannot_deploy(self):
        with self.assertRaisesRegex(ValueError, 'published'):
            self.verify(event_name='push')
        for action in ('created', 'edited', 'released', 'deleted'):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, 'published'):
                self.verify(event={**self.event, 'action': action})
        self.event['release']['draft'] = True
        with self.assertRaisesRegex(ValueError, 'Draft'):
            self.verify()

    def test_mismatched_ref_sha_or_checkout_cannot_deploy(self):
        with self.assertRaisesRegex(ValueError, 'ref'):
            self.verify(ref='refs/heads/main')
        with self.assertRaisesRegex(ValueError, 'SHA'):
            self.verify(revision='a' * 40)
        (self.repo / 'README').write_text('later')
        self.git('add', '.')
        self.git('commit', '-qm', 'Later fixture')
        with self.assertRaisesRegex(ValueError, 'agree'):
            self.verify()

    def test_release_commit_outside_main_is_rejected(self):
        (self.repo / 'README').write_text('feature only')
        self.git('add', '.')
        self.git('commit', '-qm', 'Unmerged fixture')
        self.sha = self.git('rev-parse', 'HEAD')
        self.git('tag', '-f', 'v1')
        with self.assertRaises(subprocess.CalledProcessError):
            self.verify()

    def test_dependency_build_uses_actual_live_lock_not_metadata_paths(self):
        baseline = {'revision': self.sha, 'dependency_lock_sha256': hashlib.sha256(b'locked').hexdigest()}
        (self.repo / 'backend/pyproject.toml').write_text('description="metadata only"')
        self.git('add', '.')
        self.git('commit', '-qm', 'Metadata fixture')
        target = self.git('rev-parse', 'HEAD')
        self.assertFalse(live_scope(self.sha, target, baseline, self.repo)['dependencies'])
        # A partial legacy release can have a different lock despite the same Git revision.
        baseline['dependency_lock_sha256'] = 'f' * 64
        self.assertTrue(live_scope(self.sha, target, baseline, self.repo)['dependencies'])
        self.assertTrue(live_scope(self.sha, target, baseline, self.repo)['backend'])
        with self.assertRaisesRegex(ValueError, 'baseline'):
            live_scope(target, target, baseline, self.repo)

    def test_partial_legacy_frontend_is_rebuilt_until_inputs_are_verified(self):
        baseline = {'revision': self.sha, 'dependency_lock_sha256': hashlib.sha256(b'locked').hexdigest()}
        self.assertTrue(live_scope(self.sha, self.sha, baseline, self.repo)['frontend'])
        baseline['frontend_source_sha256'] = frontend_fingerprint(self.repo, self.sha)
        self.assertFalse(live_scope(self.sha, self.sha, baseline, self.repo)['frontend'])
        (self.repo / 'frontend').mkdir()
        (self.repo / 'frontend/README.md').write_text('docs only')
        self.git('add', '.')
        self.git('commit', '-qm', 'Frontend docs fixture')
        docs = self.git('rev-parse', 'HEAD')
        self.assertFalse(live_scope(self.sha, docs, baseline, self.repo)['frontend'])
        (self.repo / 'frontend/app.js').write_text('new frontend')
        self.git('add', '.')
        self.git('commit', '-qm', 'Frontend input fixture')
        self.assertTrue(live_scope(self.sha, self.git('rev-parse', 'HEAD'), baseline, self.repo)['frontend'])

    def test_status_requires_expected_release_revision_before_recording_success(self):
        result = subprocess.CompletedProcess([], 0, stdout=json.dumps({'app': 'qunxue', 'revision': self.sha}))
        destination = self.repo / 'deployed.json'
        with patch.object(send_release, 'connection', return_value=nullcontext(['ssh'])), \
             patch.object(send_release.subprocess, 'run', return_value=result):
            with self.assertRaisesRegex(ValueError, 'published Release'):
                send_release.baseline(destination, 'a' * 40)
            self.assertFalse(destination.exists())
            send_release.baseline(destination, self.sha)
        self.assertEqual(json.loads(destination.read_text())['revision'], self.sha)


if __name__ == '__main__':
    unittest.main()
