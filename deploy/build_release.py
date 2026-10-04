#!/usr/bin/env python3
"""Build a content-addressed release from tracked source and checked frontend output."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile

from payload_rules import backend_changed, forbidden_payload
from release_scope import classify

SOURCE_ROOTS = ('backend/src/', 'backend/migrations/', 'backend/data/', 'knowledge/')
SOURCE_FILES = {'backend/alembic.ini', 'deploy/migration-policy.json'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package(repo, wheelhouse, requirements, output, revision, baseline=None):
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('A full commit SHA is required')
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    if actual != revision:
        raise ValueError('Artifact commit must match checked-out commit')
    subprocess.run(['git', 'diff', '--quiet', 'HEAD', '--'], cwd=repo, check=True)
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=repo).decode().split('\0')
    files = {p: repo / p for p in tracked if p in SOURCE_FILES or p.startswith(SOURCE_ROOTS)}
    old = json.loads(baseline.read_text()) if baseline else None
    lock = digest(repo / 'backend/uv.lock')
    scope = {'backend': True, 'frontend': True, 'dependencies': True}
    reused = {}
    if old:
        subprocess.run(['git', 'merge-base', '--is-ancestor', old['revision'], revision], cwd=repo, check=True)
        paths = subprocess.check_output(['git', 'diff', '--name-only', old['revision'], revision], cwd=repo, text=True).splitlines()
        scope = classify(paths)
    if scope['frontend']:
        frontend = repo / 'frontend/dist'
        if not (frontend / 'index.html').is_file():
            raise ValueError('Missing checked frontend build')
        files.update({'frontend/' + str(p.relative_to(frontend)): p for p in frontend.rglob('*') if p.is_file()})
    else:
        reused.update({name: value for name, value in old['files'].items() if name.startswith('frontend/')})
    if old and old.get('dependency_lock_sha256') == lock:
        reused.update({name: value for name, value in old['files'].items() if name.startswith('wheelhouse/') or name == 'requirements.lock'})
    else:
        wheels = sorted(wheelhouse.glob('*.whl'))
        if not wheels or any(not p.name.endswith('.whl') for p in wheelhouse.iterdir()):
            raise ValueError('Wheelhouse must contain binary wheels only')
        files.update({'wheelhouse/' + p.name: p for p in wheels})
        files['requirements.lock'] = requirements
    for name, path in files.items():
        if path.is_symlink() or not path.is_file() or forbidden_payload(name):
            raise ValueError('Unsafe artifact file: ' + name)
    policy = json.loads((repo / 'deploy/migration-policy.json').read_text())
    manifest = {
        'version': 2 if old else 1, 'app': 'qunxue', 'revision': revision,
        'python': '3.12', 'platform': 'linux-x86_64',
        'dependency_lock_sha256': lock,
        'files': {**reused, **{name: digest(path) for name, path in sorted(files.items())}},
        'migration_policy': policy,
    }
    if old:
        manifest.update(base_revision=old['revision'],
                        backend_revision=revision if backend_changed(old, manifest) else old.get('backend_revision', old['revision']),
                        frontend_revision=revision if scope['frontend'] else old.get('frontend_revision', old['revision']))
        manifest['payload'] = sorted(name for name in files if manifest['files'][name] != old['files'].get(name))
        files = {name: path for name, path in files.items() if name in manifest['payload']}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        metadata = Path(temporary) / 'release.json'
        metadata.write_text(json.dumps(manifest, sort_keys=True) + '\n')
        files['release.json'] = metadata
        with tarfile.open(output, 'w:gz') as archive:
            for name, path in sorted(files.items()):
                info = archive.gettarinfo(str(path), name)
                info.uid = info.gid = 0
                info.uname = info.gname = ''
                info.mode = 0o644
                info.mtime = 0
                with path.open('rb') as source:
                    archive.addfile(info, source)
    checksum = digest(output)
    output.with_suffix(output.suffix + '.sha256').write_text(checksum + '  ' + output.name + '\n')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as handle:
            handle.write('sha256=' + checksum + '\n')
    print('Built release ' + revision + ' sha256=' + checksum)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision', required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--wheelhouse', type=Path, required=True)
    parser.add_argument('--requirements', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    package(Path.cwd(), args.wheelhouse, args.requirements, args.output, args.revision, baseline=args.baseline)
