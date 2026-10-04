"""Exercise actual delta payload reconstruction, including omitted files."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
import subprocess
import shutil
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import receiver


class IncrementalTests(unittest.TestCase):
    def test_real_package_sends_only_changed_service_files(self):
        from build_release import package
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / 'repo'
            repo.mkdir()
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=repo, text=True).strip()
            git('init', '-q')
            git('config', 'user.email', 'fixture@example.invalid')
            git('config', 'user.name', 'Fixture')
            files = {'backend/src/app.py': 'initial', 'backend/uv.lock': 'locked',
                     'backend/migrations/versions/one.py': 'revision="one"',
                     'deploy/migration-policy.json': json.dumps({'version': 1, 'strategy': 'expand-only', 'rollback_compatible': True, 'approved_additions': []}),
                     'frontend/src/main.js': 'initial'}
            for name, data in files.items():
                target = repo / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(data)
            git('add', '.')
            git('commit', '-qm', 'Initial fixture')
            first = git('rev-parse', 'HEAD')
            dist = repo / 'frontend/dist'
            dist.mkdir()
            (dist / 'index.html').write_text('initial frontend')
            wheels = root / 'wheels'
            wheels.mkdir()
            (wheels / 'fake.whl').write_bytes(b'locked-wheel')
            requirements = root / 'requirements.lock'
            requirements.write_text('locked')
            package(repo, wheels, requirements, root / 'full.tar.gz', first)
            previous = root / 'first'
            receiver.extract(root / 'full.tar.gz', previous, first)
            (repo / 'frontend/src/main.js').write_text('frontend change')
            git('commit', '-qam', 'Frontend fixture')
            front_sha = git('rev-parse', 'HEAD')
            (dist / 'index.html').write_text('changed frontend')
            package(repo, root / 'missing-wheels', root / 'missing-lock', root / 'front.tar.gz', front_sha, previous / 'release.json')
            with tarfile.open(root / 'front.tar.gz') as archive:
                self.assertEqual(set(archive.getnames()), {'release.json', 'frontend/index.html'})
            second = root / 'second'
            manifest = receiver.extract(root / 'front.tar.gz', second, front_sha, previous=previous)
            self.assertEqual(manifest['backend_revision'], first)
            (repo / 'backend/src/app.py').write_text('backend change')
            git('commit', '-qam', 'Backend fixture')
            backend_sha = git('rev-parse', 'HEAD')
            shutil.rmtree(dist)
            package(repo, root / 'missing-wheels', root / 'missing-lock', root / 'back.tar.gz', backend_sha, second / 'release.json')
            with tarfile.open(root / 'back.tar.gz') as archive:
                self.assertEqual(set(archive.getnames()), {'release.json', 'backend/src/app.py'})
            third = root / 'third'
            manifest = receiver.extract(root / 'back.tar.gz', third, backend_sha, previous=second)
            self.assertEqual(manifest['frontend_revision'], front_sha)
            (repo / 'README.md').write_text('Documentation change')
            git('add', 'README.md')
            git('commit', '-qm', 'Docs fixture')
            docs_sha = git('rev-parse', 'HEAD')
            package(repo, root / 'missing-wheels', root / 'missing-lock', root / 'docs.tar.gz', docs_sha, third / 'release.json')
            with tarfile.open(root / 'docs.tar.gz') as archive:
                self.assertEqual(archive.getnames(), ['release.json'])
            # Project metadata has no changed runtime bytes or dependency closure.
            (repo / 'backend/pyproject.toml').write_text('description="metadata only"')
            git('add', 'backend/pyproject.toml')
            git('commit', '-qm', 'Metadata fixture')
            metadata_sha = git('rev-parse', 'HEAD')
            package(repo, root / 'missing-wheels', root / 'missing-lock', root / 'metadata.tar.gz', metadata_sha, third / 'release.json')
            with tarfile.open(root / 'metadata.tar.gz') as archive:
                self.assertEqual(archive.getnames(), ['release.json'])
                self.assertEqual(json.load(archive.extractfile('release.json'))['backend_revision'], backend_sha)
            # A lock fingerprint change is a backend dependency release even if wheel bytes match.
            (repo / 'backend/uv.lock').write_text('new-lock-provenance')
            git('commit', '-qam', 'Lock fixture')
            lock_sha = git('rev-parse', 'HEAD')
            package(repo, wheels, requirements, root / 'lock.tar.gz', lock_sha, third / 'release.json')
            from payload_rules import backend_changed
            with tarfile.open(root / 'lock.tar.gz') as archive:
                locked = json.load(archive.extractfile('release.json'))
            baseline = json.loads((third / 'release.json').read_text())
            self.assertEqual(locked['files'], baseline['files'])
            self.assertTrue(backend_changed(baseline, locked))
            self.assertEqual(locked['backend_revision'], lock_sha)


    def test_scope_keeps_frontend_backend_and_operations_independent(self):
        from release_scope import classify
        self.assertEqual(classify(['frontend/src/App.tsx']), {'backend': False, 'frontend': True, 'dependencies': False})
        self.assertEqual(classify(['backend/src/qunxue_api/main.py']), {'backend': True, 'frontend': False, 'dependencies': False})
        self.assertEqual(classify(['docs/README.md', '.github/workflows/delivery.yml', 'frontend/vercel.json', 'frontend/README.md', 'frontend/docs/guide.md']), {'backend': False, 'frontend': False, 'dependencies': False})
        self.assertTrue(classify(['backend/uv.lock'])['dependencies'])
        self.assertTrue(classify(['backend/src/qunxue_api/adapters/research_agent/prompts/memory_extraction.md'])['backend'])

    def delta(self, root, digest=None):
        old = root / 'old'
        (old / 'frontend').mkdir(parents=True)
        (old / 'frontend/index.html').write_bytes(b'unchanged')
        baseline = {'app': 'qunxue', 'revision': 'b' * 40, 'files': {'frontend/index.html': hashlib.sha256(b'unchanged').hexdigest()}}
        (old / 'release.json').write_text(json.dumps(baseline))
        manifest = {'version': 2, 'app': 'qunxue', 'revision': 'a' * 40, 'base_revision': 'b' * 40,
                    'python': '3.12', 'platform': 'linux-x86_64', 'files': {'frontend/index.html': digest or hashlib.sha256(b'unchanged').hexdigest()},
                    'payload': [], 'migration_policy': {}}
        archive = root / 'delta.tar.gz'
        raw = json.dumps(manifest).encode()
        with tarfile.open(archive, 'w:gz') as handle:
            info = tarfile.TarInfo('release.json')
            info.size = len(raw)
            handle.addfile(info, io.BytesIO(raw))
        return old, archive

    def test_delta_reuses_verified_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, archive = self.delta(root)
            receiver.extract(archive, root / 'new', 'a' * 40, previous=old)
            self.assertEqual((root / 'new/frontend/index.html').read_bytes(), b'unchanged')

    def test_delta_cannot_claim_different_omitted_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, archive = self.delta(root, 'f' * 64)
            with self.assertRaisesRegex(RuntimeError, 'reused|baseline'):
                receiver.extract(archive, root / 'new', 'a' * 40, previous=old)

    def test_frontend_switch_never_stops_api_or_snapshots_databases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            releases = root / 'releases'
            previous = releases / ('b' * 40)
            previous.mkdir(parents=True)
            (previous / 'backend/.venv/bin').mkdir(parents=True)
            (root / 'current').symlink_to(previous)
            old = {'revision': 'b' * 40, 'files': {'frontend/index.html': 'b' * 64}}
            (previous / 'release.json').write_text(json.dumps(old))
            candidate = releases / ('a' * 40)
            candidate.mkdir()
            (candidate / 'backend').mkdir()
            manifest = {'revision': 'a' * 40, 'backend_revision': 'b' * 40,
                        'files': {'frontend/index.html': 'a' * 64}, 'migration_policy': {}}
            (candidate / 'release.json').write_text(json.dumps(manifest))
            # extract creates the candidate after the immutable destination check.
            def extract(*args, **kwargs):
                candidate.mkdir()
                (candidate / 'backend').mkdir()
                return manifest
            shutil.rmtree(candidate)
            archive = root / 'archive'
            archive.write_bytes(b'fixture')
            config = {'root': str(root), 'environment_file': str(root / 'env'),
                      'state_directory': str(root / 'state'), 'pm2': '/test/pm2'}
            with patch.object(receiver, 'active_release', return_value=(previous, 'b' * 40)), \
                 patch.object(receiver, 'capacity_preflight'), patch.object(receiver, 'check_process'), \
                 patch.object(receiver, 'extract', side_effect=extract), \
                 patch.object(receiver, 'migration_changes', return_value=set()), \
                 patch.object(receiver, 'prepare_runtime') as prepare, \
                 patch.object(receiver, 'health'), patch.object(receiver, 'wait_healthy'), \
                 patch.object(receiver, 'pm2') as process, \
                 patch.object(receiver, 'snapshot_databases') as snapshot:
                receiver.deploy(config, archive, 'a' * 40, receiver.sha256(archive))
            self.assertEqual((root / 'current').resolve(), candidate)
            process.assert_not_called()
            snapshot.assert_not_called()
            prepare.assert_not_called()


if __name__ == '__main__':
    unittest.main()
