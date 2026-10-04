"""Run the real archive/pointer adapter with synthetic PM2 and HTTP dependencies."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import receiver


class LegacyDelivery(unittest.TestCase):
    def fixture(self, root):
        source, front, state = root / 'source-old', root / 'front-old', root / 'state'
        for path in (source / 'backend/src', source / 'backend/migrations/versions', source / 'deploy', source / 'backend/.venv/bin', front, state):
            path.mkdir(parents=True, exist_ok=True)
        (source / 'backend/src/app.py').write_bytes(b'base')
        (source / 'backend/migrations/versions/one.py').write_text('revision="one"')
        policy = {'version': 1, 'strategy': 'expand-only', 'rollback_compatible': True, 'approved_additions': []}
        (source / 'deploy/migration-policy.json').write_text(json.dumps(policy))
        (source / 'backend/.venv/bin/python').touch()
        (source / 'backend/.env').write_text('synthetic-private-config')
        (source / 'backend/var').symlink_to(state)
        (state / 'db.sqlite3').write_bytes(b'database-untouched')
        (front / 'index.html').write_bytes(b'old-front')
        source_pointer, front_pointer = root / 'source', root / 'front'
        source_pointer.symlink_to(source)
        front_pointer.symlink_to(front)
        controller = root / 'controller'
        controller.mkdir()
        config = {'root': str(controller), 'source_pointer': str(source_pointer), 'frontend_pointer': str(front_pointer),
                  'source_parent': str(root), 'frontend_parent': str(root), 'environment_file': str(source / 'backend/.env'),
                  'state_directory': str(state), 'pm2': '/test/pm2', 'runtime_uid': 0, 'runtime_gid': 0,
                  'minimum_free_bytes': 0, 'health_attempts': 1}
        files = {str(p.relative_to(source)): receiver.sha256(p) for p in source.rglob('*')
                 if p.is_file() and str(p.relative_to(source)).startswith(('backend/src/', 'backend/migrations/', 'deploy/'))}
        files['frontend/index.html'] = receiver.sha256(front / 'index.html')
        baseline = {'version': 2, 'app': 'qunxue', 'revision': 'b' * 40, 'backend_revision': 'b' * 40,
                    'frontend_revision': 'b' * 40, 'python': '3.12', 'platform': 'linux-x86_64',
                    'dependency_lock_sha256': 'c' * 64, 'files': files, 'migration_policy': policy,
                    '_source_path': str(source), '_frontend_path': str(front)}
        receiver.write_json(controller / 'active.json', baseline)
        return config, baseline, source, front, state

    def archive(self, root, baseline, changes):
        manifest = {k: v for k, v in baseline.items() if not k.startswith('_')}
        manifest.update(revision='a' * 40, base_revision=baseline['revision'], files=dict(baseline['files']), payload=sorted(changes))
        for name, data in changes.items():
            manifest['files'][name] = hashlib.sha256(data).hexdigest()
        if any(p.startswith('backend/') for p in changes): manifest['backend_revision'] = 'a' * 40
        if any(p.startswith('frontend/') for p in changes): manifest['frontend_revision'] = 'a' * 40
        path = root / 'release.tar.gz'
        with tarfile.open(path, 'w:gz') as archive:
            for name, data in {**changes, 'release.json': json.dumps(manifest).encode()}.items():
                member = tarfile.TarInfo(name); member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        return path

    def test_only_affected_pointer_and_process_change_and_state_is_retained(self):
        import legacy_receiver as legacy
        for changes, affected in [({'frontend/index.html': b'new-front'}, 'front'),
                                  ({'backend/src/app.py': b'changed'}, 'api'), ({}, 'none')]:
            with self.subTest(affected=affected), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                config, baseline, source, front, state = self.fixture(root)
                archive = self.archive(root, baseline, changes)
                with patch.object(legacy, 'process_definition', return_value={'name': 'qunxue-api', 'script': 'old', 'env': {}}), \
                     patch.object(legacy, 'start_process') as start, patch.object(legacy, 'prepare_backend') as prepare, \
                     patch.object(legacy, 'stop_process') as stop, patch.object(legacy.core, 'app_command'), \
                     patch.object(legacy, 'verify_served'):
                    legacy.deploy(config, archive, 'a' * 40, receiver.sha256(archive))
                self.assertEqual((state / 'db.sqlite3').read_bytes(), b'database-untouched')
                self.assertEqual(Path(config['source_pointer']).resolve() == source, affected != 'api')
                self.assertEqual(Path(config['frontend_pointer']).resolve() == front, affected != 'front')
                self.assertEqual(stop.call_count, int(affected == 'api'))
                self.assertEqual(start.call_count, int(affected == 'api'))
                self.assertEqual(prepare.call_count, int(affected == 'api'))
                self.assertEqual(json.loads((Path(config['root']) / 'active.json').read_text())['revision'], 'a' * 40)

    def test_failed_frontend_verification_restores_only_front_pointer(self):
        import legacy_receiver as legacy
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve();config, baseline, source, front, state = self.fixture(root)
            archive = self.archive(root, baseline, {'frontend/index.html': b'new-front'})
            with patch.object(legacy, 'process_definition'), patch.object(legacy, 'start_process') as start, \
                 patch.object(legacy, 'stop_process') as stop, \
                 patch.object(legacy, 'verify_served', side_effect=[None, RuntimeError('new assets failed'), None]):
                with self.assertRaisesRegex(RuntimeError, 'new assets failed'):
                    legacy.deploy(config, archive, 'a' * 40, receiver.sha256(archive))
            self.assertEqual(Path(config['frontend_pointer']).resolve(), front)
            self.assertEqual(Path(config['source_pointer']).resolve(), source)
            start.assert_not_called();stop.assert_not_called()
            self.assertEqual(json.loads((Path(config['root']) / 'active.json').read_text())['revision'], 'b' * 40)

    def test_failed_backend_verification_restores_old_definition_and_metadata(self):
        import legacy_receiver as legacy
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve();config, baseline, source, front, state = self.fixture(root)
            archive = self.archive(root, baseline, {'backend/src/app.py': b'changed'})
            old_definition = {'name': 'qunxue-api', 'script': 'old', 'env': {}}
            with patch.object(legacy, 'process_definition', return_value=old_definition), \
                 patch.object(legacy, 'prepare_backend'), patch.object(legacy.core, 'app_command'), \
                 patch.object(legacy, 'start_process') as start, patch.object(legacy, 'stop_process') as stop, \
                 patch.object(legacy, 'verify_served', side_effect=[None, RuntimeError('new backend failed'), None]):
                with self.assertRaisesRegex(RuntimeError, 'new backend failed'):
                    legacy.deploy(config, archive, 'a' * 40, receiver.sha256(archive))
            self.assertEqual(Path(config['source_pointer']).resolve(), source)
            self.assertEqual(Path(config['frontend_pointer']).resolve(), front)
            self.assertEqual(stop.call_count, 2)
            self.assertEqual(start.call_args.args[1], old_definition)
            self.assertEqual(json.loads((Path(config['root']) / 'active.json').read_text()), baseline)
            self.assertEqual((state / 'db.sqlite3').read_bytes(), b'database-untouched')

    def test_insufficient_capacity_and_bad_checksum_never_stop_process(self):
        import legacy_receiver as legacy
        for failure in ('capacity', 'checksum'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve();config, baseline, source, front, state = self.fixture(root)
                archive = self.archive(root, baseline, {'backend/src/app.py': b'changed'})
                if failure == 'capacity': config['minimum_free_bytes'] = 10**30
                with patch.object(legacy, 'verify_served'), patch.object(legacy, 'stop_process') as stop:
                    with self.assertRaisesRegex(RuntimeError, 'headroom|archive changed'):
                        legacy.deploy(config, archive, 'a' * 40,
                                      '0' * 64 if failure == 'checksum' else receiver.sha256(archive))
                stop.assert_not_called()
                self.assertEqual(Path(config['source_pointer']).resolve(), source)
                self.assertEqual(Path(config['frontend_pointer']).resolve(), front)

    def test_new_migrations_are_rejected_before_process_or_pointer_changes(self):
        import legacy_receiver as legacy
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve();config, baseline, source, front, state = self.fixture(root)
            archive = self.archive(root, baseline, {})
            with patch.object(legacy, 'verify_served'), patch.object(legacy, 'stop_process') as stop, \
                 patch.object(legacy.core, 'migration_changes', return_value={'versions/new.py'}):
                with self.assertRaisesRegex(RuntimeError, 'require maintenance'):
                    legacy.deploy(config, archive, 'a' * 40, receiver.sha256(archive))
            stop.assert_not_called()
            self.assertEqual(Path(config['source_pointer']).resolve(), source)
            self.assertEqual(Path(config['frontend_pointer']).resolve(), front)
            self.assertEqual((state / 'db.sqlite3').read_bytes(), b'database-untouched')

    def test_sender_uses_only_fixed_existing_sudo_receiver(self):
        from contextlib import contextmanager
        import subprocess
        import send_release as sender
        @contextmanager
        def connection():
            yield ['ssh', 'synthetic-host']
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'baseline.json'
            result = subprocess.CompletedProcess([], 0, stdout=json.dumps({'app': 'qunxue', 'revision': 'b' * 40}).encode())
            with patch.object(sender, 'connection', connection), patch.object(sender.subprocess, 'run', return_value=result) as run:
                sender.baseline(path)
            self.assertEqual(run.call_args.args[0], ['ssh', 'synthetic-host', 'sudo', '-n', '/usr/bin/python3.12',
                                                     '-I', '/usr/local/libexec/qunxue/receiver.py', 'status'])
