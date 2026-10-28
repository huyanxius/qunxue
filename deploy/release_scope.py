"""Use the actual production baseline, never just the previous main commit."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def classify(paths):
    backend = frontend = dependencies = False
    for path in paths:
        if path.startswith('frontend/') and (path.rsplit('/', 1)[-1] in {'README.md', 'AGENTS.md'} or path.startswith('frontend/docs/') or path == 'frontend/VERCEL_PREVIEW.md'):
            continue
        if path.startswith(('backend/src/', 'backend/migrations/', 'backend/data/', 'knowledge/')) or path in {'backend/alembic.ini', 'backend/pyproject.toml', 'backend/uv.lock'}:
            backend = True
        if path != 'frontend/vercel.json' and path.startswith('frontend/') and not path.startswith(('frontend/node_modules/', 'frontend/dist/')):
            frontend = True
        if path in {'backend/uv.lock', 'backend/pyproject.toml'}:
            dependencies = True
    return {'backend': backend, 'frontend': frontend, 'dependencies': dependencies}


def live_scope(base, target, baseline, repo=Path('.')):
    """Build dependencies only when the actual deployed lock fingerprint differs."""
    if baseline['revision'] != base:
        raise ValueError('Scope base must match the verified live baseline')
    subprocess.run(['git', 'merge-base', '--is-ancestor', base, target], cwd=repo, check=True)
    paths = subprocess.check_output(['git', 'diff', '--name-only', base, target], cwd=repo, text=True).splitlines()
    scope = classify(paths)
    # Legacy partial releases can report a newer health SHA while retaining old
    # frontend bytes. Only a builder-recorded input fingerprint proves reuse.
    scope['frontend'] = frontend_fingerprint(repo, target) != baseline.get('frontend_source_sha256')
    lock = subprocess.check_output(['git', 'show', target + ':backend/uv.lock'], cwd=repo)
    scope['dependencies'] = hashlib.sha256(lock).hexdigest() != baseline.get('dependency_lock_sha256')
    scope['backend'] |= scope['dependencies']
    return scope


def frontend_fingerprint(repo, revision):
    entries = subprocess.check_output(['git', 'ls-tree', '-r', '-z', revision, '--', 'frontend'], cwd=repo)
    selected = []
    for entry in entries.split(b'\0'):
        if not entry:
            continue
        _, path = entry.split(b'\t', 1)
        if classify([path.decode()])['frontend']:
            selected.append(entry)
    return hashlib.sha256(b'\0'.join(selected)).hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('base')
    parser.add_argument('target')
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    if args.baseline:
        scope = live_scope(args.base, args.target, json.loads(args.baseline.read_text()))
    else:
        subprocess.run(['git', 'merge-base', '--is-ancestor', args.base, args.target], check=True)
        paths = subprocess.check_output(['git', 'diff', '--name-only', args.base, args.target], text=True).splitlines()
        scope = classify(paths)
    print(json.dumps(scope))
