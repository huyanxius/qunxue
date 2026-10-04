"""Adapter for the existing root PM2 and two production symlinks.

This is invoked only by the fixed receiver, not a second deployment entrypoint.
App data, private configuration and the existing runtime identity stay in place.
"""
from contextlib import contextmanager
import fcntl
import json
import os
import platform
from pathlib import Path
import re
import shutil
import signal
import sys
import tempfile
import time

import receiver as core
from payload_rules import backend_changed, forbidden_payload


def load_config(value):
    core.require(value.get('configured') is True and value.get('version') == 1
                 and value.get('app') == 'qunxue', 'Legacy adapter is not configured')
    expected = {'root': '/root/.qunxue-deploy', 'source_pointer': '/root/qunxue-src',
                'frontend_pointer': '/var/www/qunxue', 'source_parent': '/root',
                'frontend_parent': '/var/www', 'pm2_home': '/root/.pm2',
                'local_origin': 'http://127.0.0.1:8096', 'public_origin': 'https://qunxue.xyz'}
    core.require(all(value.get(k) == v for k, v in expected.items()), 'Unexpected legacy deployment boundary')
    core.require(os.geteuid() == 0 and value.get('runtime_uid') == 0 and value.get('runtime_gid') == 0,
                 'This adapter preserves the existing root PM2 identity')
    core.require(value.get('expected_runtime_mode') in ('base', 'sft')
                 and 1 <= value.get('health_attempts', 0) <= 12, 'Invalid health configuration')
    for key in ('python', 'pm2', 'environment_file', 'state_directory'):
        path = Path(value[key])
        core.require(path.is_absolute() and path.exists(), 'Missing legacy path: ' + key)
    core.require(platform.system() == 'Linux' and platform.machine() == 'x86_64', 'Unsupported host platform')
    core.require(Path(value['pm2_home']).is_dir() and Path(value['state_directory']).is_dir(), 'Missing existing runtime state')
    databases = value.get('databases', [])
    core.require(len(databases) == 3 and len({d['path'] for d in databases}) == 3
                 and sum(d.get('migrate') is True for d in databases) == 1, 'Three existing databases and one primary required')
    for database in databases:
        path = Path(database['path'])
        core.require(path.is_file() and not path.is_symlink()
                     and path.resolve().is_relative_to(Path(value['state_directory']).resolve()), 'Database escaped existing shared state')
    core.require(type(value.get('minimum_free_bytes')) is int and value['minimum_free_bytes'] >= 0, 'Invalid capacity reserve')
    core.trusted(Path(value['environment_file']))
    core.require(not Path(value['environment_file']).stat().st_mode & 0o007,
                 'Private configuration must remain private')
    for key, parent in (('source_pointer', 'source_parent'), ('frontend_pointer', 'frontend_parent')):
        pointer = Path(value[key])
        core.require(pointer.is_symlink(), 'Existing legacy pointer required')
        target = pointer.resolve(strict=True)
        core.require(target.parent == Path(value[parent])
                     and re.fullmatch(r'qunxue-release(?:[0-9]+)?-[0-9a-f]{7,40}', target.name),
                     'Legacy pointer escaped the application release boundary')
    root = Path(value['root'])
    if not root.exists(): root.mkdir(mode=0o700)
    core.trusted(root)
    return value


def process_definition(config):
    result = core.app_command(config, [config['pm2'], 'jlist'], timeout=20)
    found = [p for p in json.loads(result.stdout) if p.get('name') == 'qunxue-api']
    core.require(len(found) == 1 and found[0]['pm2_env']['exec_mode'] == 'fork_mode'
                 and found[0]['pm2_env']['status'] == 'online', 'Expected existing qunxue-api fork')
    env = found[0]['pm2_env']
    # Keep existing private environment in server memory; it is never returned by status.
    return {'name': 'qunxue-api', 'script': env['pm_exec_path'], 'cwd': env['pm_cwd'],
            'args': env.get('args', []), 'interpreter': env.get('exec_interpreter', 'none'),
            'instances': 1, 'exec_mode': 'fork', 'kill_timeout': env.get('kill_timeout', 300000),
            'env': dict(env.get('env', {}))}


def start_process(config, definition):
    path = Path(config['root']) / 'process.json'
    core.write_json(path, {'apps': [definition]})
    try:
        core.app_command(config, [config['pm2'], 'startOrRestart', str(path), '--only', 'qunxue-api', '--update-env'], timeout=360)
    finally:
        # The copied environment never becomes a retained artifact or a log.
        path.unlink(missing_ok=True)


def stop_process(config):
    core.pm2(config, 'stop')
    core.check_process(config, stopped=True)


@contextmanager
def view(config, manifest):
    with tempfile.TemporaryDirectory(prefix='view-', dir=config['root']) as tmp:
        root = Path(tmp)
        source = Path(manifest['_source_path'])
        for name in ('backend', 'knowledge', 'deploy', 'wheelhouse', 'requirements.lock'):
            if (source / name).exists(): (root / name).symlink_to(source / name)
        (root / 'frontend').symlink_to(manifest['_frontend_path'])
        core.write_json(root / 'release.json', manifest)
        yield root


def verify_served(config, manifest):
    with view(config, manifest) as release:
        for attempt in range(config['health_attempts']):
            try:
                core.health(config, release, manifest['revision'])
                core.check_process(config)
                return
            except Exception:
                if attempt + 1 == config['health_attempts']: raise
                time.sleep(2)


def baseline(config):
    path = Path(config['root']) / 'active.json'
    source = Path(config['source_pointer']).resolve(strict=True)
    front = Path(config['frontend_pointer']).resolve(strict=True)
    if path.exists():
        value = json.loads(path.read_text())
        core.require(value['_source_path'] == str(source) and value['_frontend_path'] == str(front),
                     'Production pointers changed outside the receiver; audited baseline refresh required')
        return value
    data = json.loads(core.fetch(config['local_origin'] + '/api/health'))
    revision = data.get('release_revision', '')
    core.require(core.SHA.fullmatch(revision) and data.get('status') == 'ok', 'Cannot establish actual production revision')
    files = {}
    for prefix in ('backend/src', 'backend/migrations', 'backend/data', 'knowledge'):
        for p in (source / prefix).rglob('*'):
            name = str(p.relative_to(source))
            if p.is_file() and not forbidden_payload(name):
                core.require(not p.is_symlink(), 'Linked source file in baseline')
                files[name] = core.sha256(p)
    for name in ('backend/alembic.ini', 'deploy/migration-policy.json'):
        if (source / name).is_file(): files[name] = core.sha256(source / name)
    for p in front.rglob('*'):
        if p.is_file():
            core.require(not p.is_symlink(), 'Linked frontend file in baseline')
            files['frontend/' + str(p.relative_to(front))] = core.sha256(p)
    policy_path = source / 'deploy/migration-policy.json'
    policy = json.loads(policy_path.read_text()) if policy_path.is_file() else {
        'version': 1, 'strategy': 'expand-only', 'rollback_compatible': True, 'approved_additions': []}
    value = {'version': 2, 'app': 'qunxue', 'revision': revision, 'backend_revision': revision,
             'frontend_revision': revision, 'python': '3.12', 'platform': 'linux-x86_64',
             'dependency_lock_sha256': core.sha256(source / 'backend/uv.lock'),
             'files': files, 'migration_policy': policy, '_source_path': str(source), '_frontend_path': str(front)}
    verify_served(config, value)
    core.write_json(path, value)
    return value


def prepare_backend(config, release, manifest, previous):
    with view(config, previous) as old:
        core.prepare_runtime(config, release, manifest['backend_revision'], previous=old)


def deploy(config, archive, revision, checksum):
    old = baseline(config)
    core.require(revision != old['revision'], 'Revision already evaluated; no changes made')
    core.require(core.sha256(archive) == checksum, 'Incoming archive changed')
    verify_served(config, old)
    # Reconstructing omitted bytes consumes disk, even for a small delta archive.
    with view(config, old) as previous:
        footprint = sum((previous / name).stat().st_size for name in old['files'])
    for parent in (config['root'], config['frontend_parent']):
        core.require(shutil.disk_usage(parent).free >= config['minimum_free_bytes'] + footprint * 2 + archive.stat().st_size * 4,
                     'Insufficient release reconstruction headroom; no process changed')
    journal = Path(config['root']) / 'deployment-state.json'
    with tempfile.TemporaryDirectory(prefix='stage-', dir=config['root']) as tmp:
        stage = Path(tmp) / 'release'
        with view(config, old) as previous:
            manifest = core.extract(archive, stage, revision, previous=previous)
            additions = core.migration_changes(previous, stage, manifest['migration_policy'])
        # Existing schema is preserved. Schema changes require a separate reviewed maintenance release.
        core.require(not additions, 'New migrations require maintenance; no pointer or process changed')
        api = backend_changed(old, manifest)
        web = any(old['files'].get(name) != manifest['files'].get(name)
                  for name in set(old['files']) | set(manifest['files']) if name.startswith('frontend/'))
        expected = revision if api else old.get('backend_revision', old['revision'])
        core.require(manifest.get('backend_revision') == expected, 'Backend content/revision mismatch')
        source = Path(config['source_parent']) / ('qunxue-release-' + revision) if api else Path(old['_source_path'])
        front = Path(config['frontend_parent']) / ('qunxue-release-' + revision) if web else Path(old['_frontend_path'])
        manifest.update(_source_path=str(source), _frontend_path=str(front))
        definition = process_definition(config) if api else None
        state = {'phase': 'prepared', 'revision': revision, 'previous_revision': old['revision'],
                 'previous': old, 'api': api, 'web': web}
        if api:
            core.require(not source.exists(), 'Immutable backend release exists; inspect failed attempt')
            prepare_backend(config, stage, manifest, old)
            os.replace(stage, source)
        if web:
            core.require(not front.exists(), 'Immutable frontend release exists; inspect failed attempt')
            shutil.copytree((source if api else stage) / 'frontend', front)
            for directory, dirs, files in os.walk(front):
                os.chmod(directory, 0o755)
                for name in files: (Path(directory) / name).chmod(0o644)
        core.write_json(journal, state)
        stopped = False
        try:
            if api:
                stopped = True
                stop_process(config)
                core.atomic_pointer(Path(config['source_pointer']), source)
            if web: core.atomic_pointer(Path(config['frontend_pointer']), front)
            state['phase'] = 'switched';core.write_json(journal, state)
            if api:
                new = {**definition, 'script': str(source / 'backend/.venv/bin/python'), 'cwd': str(source / 'backend'),
                       'interpreter': 'none', 'env': {**definition['env'], 'PYTHONPATH': str(source / 'backend/src'),
                                                     'QUNXUE_RELEASE_REVISION': expected}}
                start_process(config, new)
            verify_served(config, manifest)
            if api: core.app_command(config, [config['pm2'], 'save'], timeout=30)
            core.write_json(Path(config['root']) / 'active.json', manifest)
            state['phase'] = 'healthy';core.write_json(journal, state)
        except BaseException:
            with core.recovery_signals():
                try:
                    if stopped: stop_process(config)
                    if api: core.atomic_pointer(Path(config['source_pointer']), Path(old['_source_path']))
                    if web: core.atomic_pointer(Path(config['frontend_pointer']), Path(old['_frontend_path']))
                    if stopped: start_process(config, definition)
                    verify_served(config, old)
                    if stopped: core.app_command(config, [config['pm2'], 'save'], timeout=30)
                    core.write_json(Path(config['root']) / 'active.json', old)
                    state['phase'] = 'rolled-back';core.write_json(journal, state)
                except BaseException:
                    state['phase'] = 'rollback-failed-needs-operator';core.write_json(journal, state)
                    print('Rollback failed: operator required; original app data retained', file=sys.stderr)
            raise
    print('DEPLOYED qunxue ' + revision + ' restarted=' + ('qunxue-api' if api else '[]')
          + ' frontend_switch=' + str(web).lower() + ' database_backup_bytes=0')


def main(value, command):
    core.require(command == 'status' or re.fullmatch(r'deploy [0-9a-f]{40} [0-9a-f]{64}', command),
                 'Legacy receiver accepts only status or exact deploy protocol')
    config = load_config(value)
    root = Path(config['root'])
    with (root / 'deploy.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        journal = root / 'deployment-state.json'
        if journal.exists():
            core.require(json.loads(journal.read_text())['phase'] in ('prepared', 'healthy', 'rolled-back'),
                         'Interrupted update requires operator review')
        if command == 'status':
            print(json.dumps({k: v for k, v in baseline(config).items() if not k.startswith('_')}))
            return
        def interrupted(signum, frame): raise InterruptedError('Release interrupted')
        for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT): signal.signal(signum, interrupted)
        _, revision, digest = command.split()
        with tempfile.TemporaryDirectory(prefix='incoming-', dir=root) as tmp:
            archive = Path(tmp) / 'release.tar.gz'
            core.receive(sys.stdin.buffer, archive, digest)
            deploy(config, archive, revision, digest)
