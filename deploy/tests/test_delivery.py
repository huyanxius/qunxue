"""Synthetic safety checks only: no production, secrets, SSH, models or concurrent workers."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import stat
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
spec = importlib.util.spec_from_file_location('receiver', ROOT / 'deploy/receiver.py')
receiver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receiver)
SHA = 'a' * 40
OLD = 'b' * 40
POLICY = {'version': 1, 'strategy': 'expand-only', 'rollback_compatible': True, 'approved_additions': []}


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def archive(self, extras=None, revision=SHA):
        files = {'frontend/index.html': b'<html>hello</html>', 'wheelhouse/fake.whl': b'wheel',
                 'backend/migrations/versions/one.py': b'revision="one"',
                 'deploy/migration-policy.json': json.dumps(POLICY).encode()}
        files.update(extras or {})
        manifest = {'version': 1, 'app': 'qunxue', 'revision': revision,
                    'python': '3.12', 'platform': 'linux-x86_64', 'migration_policy': POLICY,
                    'files': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
        files['release.json'] = json.dumps(manifest).encode()
        path = self.root / 'artifact.tar.gz'
        with tarfile.open(path, 'w:gz') as tar:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        return path

    def test_extract_good_artifact(self):
        manifest = receiver.extract(self.archive(), self.root / 'stage', SHA)
        self.assertEqual(manifest['revision'], SHA)

    def test_reject_path_traversal(self):
        with self.assertRaisesRegex(RuntimeError, 'Unsafe archive'):
            receiver.extract(self.archive({'../escape': b'x'}), self.root / 'stage', SHA)
        self.assertFalse((self.root.parent / 'escape').exists())

    def test_reject_symlink(self):
        path = self.root / 'link.tar.gz'
        with tarfile.open(path, 'w:gz') as tar:
            info = tarfile.TarInfo('backend/link')
            info.type = tarfile.SYMTYPE
            info.linkname = '/etc/passwd'
            tar.addfile(info)
        with self.assertRaisesRegex(RuntimeError, 'Unsafe archive'):
            receiver.extract(path, self.root / 'stage', SHA)

    def test_reject_duplicate_member(self):
        path = self.root / 'duplicate.tar.gz'
        with tarfile.open(path, 'w:gz') as tar:
            for _ in range(2):
                info = tarfile.TarInfo('a')
                tar.addfile(info, io.BytesIO(b''))
        with self.assertRaisesRegex(RuntimeError, 'Duplicate'):
            receiver.extract(path, self.root / 'stage', SHA)

    def test_reject_wrong_commit(self):
        with self.assertRaisesRegex(RuntimeError, 'identity'):
            receiver.extract(self.archive(revision=OLD), self.root / 'stage', SHA)

    def test_reject_runtime_state(self):
        with self.assertRaisesRegex(RuntimeError, 'outside|runtime state'):
            receiver.extract(self.archive({'backend/.env': b'no'}), self.root / 'stage', SHA)

    def test_env_variants_and_state_suffix_are_rejected(self):
        for name in ('backend/src/.env.production', 'frontend/.env.local',
                     'frontend/credentials.pem', 'backend/data/runtime.sqlite3'):
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, 'runtime state'):
                receiver.extract(self.archive({name: b'not-a-real-secret'}), self.root / 'stage', SHA)

    def test_database_driver_denies_network_and_secret_file_reads(self):
        # Test only the audit guard in a disposable interpreter, no app/dependency imports.
        import subprocess
        guard = receiver.DB_ONLY_DRIVER.split('from qunxue_api import settings')[0]
        for action in ('import socket; socket.socket()', 'open(".env.production").read()'):
            result = subprocess.run([sys.executable, '-c', guard + '\n' + action,
                                     '/tmp/fake.db', '/tmp/fake.ini', '/tmp/production.env'],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('forbidden', result.stderr)

    def test_receive_hash_mismatch(self):
        with self.assertRaisesRegex(RuntimeError, 'SHA256'):
            receiver.receive(io.BytesIO(b'bad'), self.root / 'input', 'f' * 64)

    def test_receive_size_limit(self):
        with patch.object(receiver, 'MAX_ARCHIVE', 2), self.assertRaisesRegex(RuntimeError, 'size limit'):
            receiver.receive(io.BytesIO(b'long'), self.root / 'input', 'f' * 64)

    def test_atomic_json_preserves_owner_group_mode(self):
        path = self.root / 'metadata.json'
        path.write_text('{}')
        path.chmod(0o640)
        before = path.stat()
        receiver.write_json(path, {'new': True})
        after = path.stat()
        self.assertEqual((before.st_uid, before.st_gid, stat.S_IMODE(before.st_mode)),
                         (after.st_uid, after.st_gid, stat.S_IMODE(after.st_mode)))
        self.assertEqual(json.loads(path.read_text()), {'new': True})

    def test_atomic_pointer_preserves_ownership(self):
        old, new = self.root / 'old', self.root / 'new'
        old.mkdir()
        new.mkdir()
        current = self.root / 'current'
        current.symlink_to(old)
        info = current.lstat()
        receiver.atomic_pointer(current, new)
        self.assertEqual(current.resolve(), new)
        self.assertEqual((info.st_uid, info.st_gid), (current.lstat().st_uid, current.lstat().st_gid))

    def migration_roots(self):
        old, new = self.root / 'old', self.root / 'new'
        for root in (old, new):
            (root / 'backend/migrations/versions').mkdir(parents=True)
            (root / 'backend/migrations/versions/one.py').write_text('revision="one"\n')
        return old, new

    def test_unchanged_migrations_allowed(self):
        old, new = self.migration_roots()
        self.assertEqual(receiver.migration_changes(old, new, POLICY), set())

    def test_edited_existing_migration_blocked(self):
        old, new = self.migration_roots()
        (new / 'backend/migrations/versions/one.py').write_text('changed')
        with self.assertRaisesRegex(RuntimeError, 'modified/deleted'):
            receiver.migration_changes(old, new, POLICY)

    def test_new_migration_needs_exact_reviewed_declaration(self):
        old, new = self.migration_roots()
        (new / 'backend/migrations/versions/two.py').write_text('def upgrade():\n    pass\n')
        with self.assertRaisesRegex(RuntimeError, 'exact reviewed'):
            receiver.migration_changes(old, new, POLICY)
        declared = dict(POLICY, approved_additions=['versions/two.py'])
        self.assertEqual(receiver.migration_changes(old, new, declared), {'versions/two.py'})

    def test_destructive_upgrade_blocked_even_when_declared(self):
        old, new = self.migration_roots()
        (new / 'backend/migrations/versions/two.py').write_text('def upgrade():\n    op.drop_column("t","x")\n')
        with self.assertRaisesRegex(RuntimeError, 'Destructive/opaque'):
            receiver.migration_changes(old, new, dict(POLICY, approved_additions=['versions/two.py']))

    def test_migration_helpers_aliases_and_dynamic_sql_are_rejected(self):
        bodies = [
            'def helper():\n    op.execute("DROP TABLE t")\ndef upgrade():\n    helper()\n',
            'from alembic.op import drop_table\ndef upgrade():\n    drop_table("t")\n',
            'def upgrade():\n    getattr(op, "drop_column")("t", "x")\n',
            'def helper():\n    op.get_bind().exec_driver_sql("UPDATE t SET x=1")\ndef upgrade():\n    helper()\n',
        ]
        for source in bodies:
            with self.subTest(source=source), self.assertRaises(RuntimeError):
                receiver.validate_expand_migration(source)

    def test_required_column_is_not_backward_compatible(self):
        with self.assertRaisesRegex(RuntimeError, 'nullable'):
            receiver.validate_expand_migration(
                'from alembic import op\nimport sqlalchemy as sa\n'
                'def upgrade():\n    op.add_column("t", sa.Column("x", sa.Text(), nullable=False))\n')

    def test_nullable_add_column_is_supported(self):
        receiver.validate_expand_migration(
            'from alembic import op\nimport sqlalchemy as sa\nrevision="two"\ndown_revision="one"\n'
            'def upgrade():\n    op.add_column("t", sa.Column("x", sa.Text(), nullable=True))\n')

    def test_migration_module_side_effect_is_rejected(self):
        with self.assertRaises(RuntimeError):
            receiver.validate_expand_migration('open("/etc/passwd").read()\ndef upgrade():\n    pass\n')

    def databases(self):
        dbs = []
        for name in ('primary', 'secondary', 'tertiary'):
            path = self.root / (name + '.db')
            with sqlite3.connect(path) as connection:
                connection.execute('CREATE TABLE evidence(id INTEGER PRIMARY KEY, value TEXT)')
                connection.execute('INSERT INTO evidence(value) VALUES (?)', ('preserve',))
            path.chmod(0o640)
            dbs.append({'name': name, 'path': str(path), 'migrate': name == 'primary'})
        return {'databases': dbs}

    def test_three_sqlite_backups_preserve_original_data_and_metadata(self):
        config = self.databases()
        inventory = receiver.snapshot_databases(config, self.root / 'backups')
        self.assertEqual(len(inventory), 3)
        self.assertTrue(all(row['table_counts']['evidence'] == 1 for row in inventory))
        receiver.validate_database_metadata(inventory)
        receiver.validate_database_contents(inventory)
        for row in inventory:
            self.assertEqual(stat.S_IMODE((self.root / 'backups' / row['backup']).stat().st_mode), 0o600)

    def test_wal_content_is_in_backup(self):
        path = self.root / 'wal.db'
        with sqlite3.connect(path) as connection:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('CREATE TABLE evidence (id INTEGER)')
            connection.execute('INSERT INTO evidence VALUES (42)')
            connection.commit()
            inventory = receiver.snapshot_databases({'databases': [{'name': 'wal', 'path': str(path)}]},
                                                    self.root / 'backup')
            self.assertEqual(inventory[0]['table_counts']['evidence'], 1)
            with sqlite3.connect(self.root / 'backup/wal.sqlite3') as backup:
                self.assertEqual(backup.execute('SELECT id FROM evidence').fetchone(), (42,))

    def test_data_loss_fails_row_count_validation(self):
        config = self.databases()
        inventory = receiver.snapshot_databases(config, self.root / 'backup')
        with sqlite3.connect(config['databases'][0]['path']) as connection:
            connection.execute('DELETE FROM evidence')
        with self.assertRaisesRegex(RuntimeError, 'row counts'):
            receiver.validate_database_contents(inventory)

    def test_changed_database_mode_detected(self):
        config = self.databases()
        inventory = receiver.snapshot_databases(config, self.root / 'backup')
        Path(config['databases'][0]['path']).chmod(0o600)
        with self.assertRaisesRegex(RuntimeError, 'metadata'):
            receiver.validate_database_metadata(inventory)

    def test_health_rejects_wrong_revision_and_public_asset(self):
        release = self.root / 'release'
        release.mkdir()
        good = b'index'
        (release / 'release.json').write_text(json.dumps({'files': {'frontend/index.html':
                                                                  hashlib.sha256(good).hexdigest()}}))
        config = {'local_origin': 'http://127.0.0.1:8096', 'public_origin': 'https://qunxue.example',
                  'expected_runtime_mode': 'base'}
        valid = json.dumps({'status': 'ok', 'release_revision': SHA, 'runtime_mode': 'base'}).encode()
        with patch.object(receiver, 'fetch', side_effect=[valid, good, valid, b'wrong']):
            with self.assertRaisesRegex(RuntimeError, 'asset mismatch'):
                receiver.health(config, release, SHA)
        with patch.object(receiver, 'fetch', return_value=valid):
            with self.assertRaisesRegex(RuntimeError, 'revision/runtime'):
                receiver.health(config, release, OLD)

    def test_public_index_allows_only_one_empty_official_cloudflare_beacon(self):
        good = b'<html><body>business</body></html>'
        digest = hashlib.sha256(good).hexdigest()
        beacon = (b'<script type="module" src="https://static.cloudflareinsights.com/beacon.min.js/v' + b'a' * 40
                  + b'" integrity="sha512-' + b'A' * 86 + b'==' + b'" data-cf-beacon=\'{"version":"2024.11.0","token":"'
                  + b'0' * 32 + b'","r":1,"spa":2}\' crossorigin="anonymous"></script>')
        def page(script): return good.replace(b'</body>', script + b'</body>')
        self.assertTrue(receiver.public_index_matches(good, digest))
        self.assertTrue(receiver.public_index_matches(page(beacon), digest))
        self.assertTrue(receiver.public_index_matches(page(beacon + b'\n'), digest))
        self.assertFalse(receiver.public_index_matches(page(beacon + b'\n\n'), digest))
        for script in (beacon * 2, beacon.replace(b'insights.com', b'insights.invalid'),
                       beacon.replace(b'></script>', b'>alert(1)</script>'),
                       beacon.replace(b' crossorigin=', b' onload="evil()" crossorigin=')):
            self.assertFalse(receiver.public_index_matches(page(script), digest))
        self.assertFalse(receiver.public_index_matches(page(beacon).replace(b'business', b'wrong'), digest))

    def test_failed_deployment_rolls_code_back_without_db_restore(self):
        root = self.root
        (root / 'releases').mkdir()
        (root / 'backups').mkdir()
        previous = root / 'releases' / OLD
        previous.mkdir()
        (root / 'current').symlink_to(previous)
        archive = root / 'archive'
        archive.write_bytes(b'payload')
        config = {'root': str(root), 'minimum_free_bytes': 0, 'pm2': '/test/pm2', 'databases': []}
        (previous / 'release.json').write_text(json.dumps({'files': {}, 'revision': OLD}))
        policy = {'migration_policy': POLICY, 'files': {'backend/src/new.py': 'a' * 64}}
        with patch.object(receiver, 'active_release', return_value=(previous, OLD)), \
             patch.object(receiver, 'check_process'), patch.object(receiver, 'extract', return_value=policy), \
             patch.object(receiver, 'migration_changes'), patch.object(receiver, 'prepare_runtime'), \
             patch.object(receiver, 'health'), patch.object(receiver, 'pm2') as process, \
             patch.object(receiver, 'snapshot_databases', return_value=[]), \
             patch.object(receiver, 'rehearse_migration'), patch.object(receiver, 'migrate') as migration, \
             patch.object(receiver, 'validate_database_contents'), \
             patch.object(receiver, 'validate_database_metadata'), patch.object(receiver, 'app_command'), \
             patch.object(receiver, 'wait_healthy', side_effect=[RuntimeError('new API bad'), None]):
            with self.assertRaisesRegex(RuntimeError, 'new API bad'):
                receiver.deploy(config, archive, SHA, receiver.sha256(archive))
            self.assertEqual((root / 'current').resolve(), previous)
            self.assertEqual(json.loads((root / 'deployment-state.json').read_text())['phase'], 'rolled-back')
            self.assertEqual(migration.call_count, 1)  # Never a downgrade/restore call.
            self.assertEqual(process.call_args_list[-1].args, (config, 'start', OLD))

    def test_interrupted_manual_rollback_recovers_current_release(self):
        root = self.root
        current = root / 'releases' / SHA
        target = root / 'releases' / OLD
        current.mkdir(parents=True)
        target.mkdir()
        (root / 'current').symlink_to(current)
        (current / 'release.json').write_text(json.dumps({'migration_policy': POLICY}))
        (target / 'release.json').write_text(json.dumps({'migration_policy': POLICY}))
        (root / 'deployment-state.json').write_text(json.dumps(
            {'revision': SHA, 'previous_revision': OLD, 'phase': 'healthy'}))
        config = {'root': str(root), 'pm2': '/test/pm2'}
        with patch.object(receiver, 'active_release', return_value=(current, SHA)), \
             patch.object(receiver, 'migration_changes'), patch.object(receiver, 'pm2'), \
             patch.object(receiver, 'check_process'), patch.object(receiver, 'app_command'), \
             patch.object(receiver, 'wait_healthy', side_effect=[InterruptedError('SSH disconnected'), None]):
            with self.assertRaises(InterruptedError):
                receiver.rollback(config, SHA, OLD)
        self.assertEqual((root / 'current').resolve(), current)
        self.assertEqual(json.loads((root / 'deployment-state.json').read_text())['phase'], 'healthy')

    def test_recovery_temporarily_ignores_second_signal(self):
        previous = signal.getsignal(signal.SIGTERM)
        with receiver.recovery_signals():
            self.assertEqual(signal.getsignal(signal.SIGTERM), signal.SIG_IGN)
            self.assertEqual(signal.getsignal(signal.SIGHUP), signal.SIG_IGN)
        self.assertEqual(signal.getsignal(signal.SIGTERM), previous)

    def test_capacity_accounts_for_actual_dbs_before_stopping(self):
        config = self.databases()
        config.update({'root': str(self.root), 'minimum_free_bytes': 1024})
        previous = self.root / 'previous'
        previous.mkdir()
        archive = self.root / 'archive'
        archive.write_bytes(b'payload')
        with patch.object(receiver, 'active_release', return_value=(previous, OLD)), \
             patch.object(receiver.shutil, 'disk_usage') as usage, \
             patch.object(receiver, 'pm2') as process:
            usage.return_value.free = receiver.MAX_EXPANDED + 2048
            with self.assertRaisesRegex(RuntimeError, 'actual databases'):
                receiver.deploy(config, archive, SHA, receiver.sha256(archive))
            process.assert_not_called()

    def test_workflow_has_separate_privileged_main_only_gate(self):
        workflow = (ROOT / '.github/workflows/delivery.yml').read_text()
        self.assertNotIn('pull_request_target', workflow)
        checks, deployment = workflow.split('\n  deploy:\n')
        self.assertNotIn('secrets.', checks)
        self.assertIn('needs: checks', deployment)
        self.assertIn("github.event_name == 'push' && github.ref == 'refs/heads/main'", deployment)
        self.assertIn('environment: production', deployment)
        self.assertIn('cancel-in-progress: false', deployment)
        self.assertNotIn('contents: write', workflow)
        for line in workflow.splitlines():
            if 'uses:' in line:
                self.assertRegex(line, r'@[0-9a-f]{40}( |$)')

    def test_wheel_build_and_packaging_are_scoped_to_live_main_baseline(self):
        workflow = (ROOT / '.github/workflows/delivery.yml').read_text()
        checks, deployment = workflow.split('\n  deploy:\n')
        self.assertNotIn('deploy/build_wheelhouse.py', checks)
        self.assertIn('deploy/send_release.py --status baseline.json', deployment)
        self.assertIn('--baseline baseline.json', deployment)
        self.assertIn("env.dependencies == 'true'", deployment)
        self.assertIn('deploy/build_wheelhouse.py', deployment)
        self.assertIn('deploy/build_release.py', deployment)
        self.assertIn("github.event_name == 'push' && github.ref == 'refs/heads/main'", deployment)
        self.assertNotIn('qunxue-delivery-${{ github.ref }}', workflow)

    def test_builder_packages_only_clean_checked_commit_and_verifies_roundtrip(self):
        spec = importlib.util.spec_from_file_location('builder', ROOT / 'deploy/build_release.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        repo = self.root / 'repo'
        repo.mkdir()
        (repo / 'backend/migrations/versions').mkdir(parents=True)
        (repo / 'backend/migrations/versions/one.py').write_text('revision="one"')
        (repo / 'backend/uv.lock').write_text('# synthetic lock')
        (repo / 'frontend/dist').mkdir(parents=True)
        (repo / 'frontend/dist/index.html').write_text('<html>fixture</html>')
        (repo / 'deploy').mkdir()
        (repo / 'deploy/migration-policy.json').write_text(json.dumps(POLICY))
        for command in (['git', 'init', '-q'], ['git', 'add', 'backend', 'deploy'],
                        ['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                         'commit', '-qm', 'Synthetic fixture']):
            subprocess.run(command, cwd=repo, check=True, capture_output=True)
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
        wheels = self.root / 'wheels'
        wheels.mkdir()
        (wheels / 'synthetic.whl').write_bytes(b'synthetic packaging fixture, not an installable dependency')
        requirements = self.root / 'requirements.lock'
        requirements.write_text('# fixture only')
        output = self.root / 'release.tar.gz'
        with patch.dict(os.environ, {}, clear=True):
            builder.package(repo, wheels, requirements, output, revision)
        manifest = receiver.extract(output, self.root / 'unpacked', revision)
        self.assertEqual(manifest['revision'], revision)
        self.assertEqual((self.root / 'unpacked/frontend/index.html').read_text(), '<html>fixture</html>')
        (repo / 'backend/migrations/versions/one.py').write_text('uncommitted change')
        with self.assertRaises(subprocess.CalledProcessError):
            builder.package(repo, wheels, requirements, output, revision)

    def test_missing_production_setup_fails_before_ssh(self):
        spec = importlib.util.spec_from_file_location('sender', ROOT / 'deploy/send_release.py')
        sender = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sender)
        with patch.dict(os.environ, {}, clear=True), patch.object(sender.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'setup incomplete'):
                sender.send()
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
