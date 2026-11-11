"""Select CI checks and scope production builds against the live baseline."""
import argparse
import hashlib
import json
import os
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


def classify_ci(paths):
    """Select checks for pull requests and pushes, including non-runtime inputs."""
    scope = {'backend': False, 'frontend': False, 'dependencies': False}
    for path in paths:
        release = classify([path])
        scope['dependencies'] |= release['dependencies']
        if (
            path in {'backend/openapi.json', 'backend/scripts/export_openapi.py'}
            or path.startswith('frontend/src/api/generated/')
        ):
            scope['backend'] = scope['frontend'] = True
        elif (
            release['backend'] or path == 'backend/.python-version'
            or path.startswith(('backend/tests/', 'backend/scripts/', 'backend/evals/'))
        ):
            scope['backend'] = True
        elif path in {
            'AGENTS.md', 'CHANGELOG.md', 'CONTRIBUTING.md', 'LICENSE', 'NOTICE',
            'README.md', 'RUN_STATE.md', 'SUPPORT.md', 'backend/README.md', 'deploy/README.md',
        } or path.startswith(('docs/', 'backend/docs/')):
            continue
        elif path.startswith('frontend/') and not release['frontend']:
            # Reuse the release exclusions for frontend docs, Vercel config and build outputs.
            continue
        elif path.startswith(('frontend/src/', 'frontend/public/', 'frontend/previews/')) or path in {
            'frontend/index.html', 'frontend/vite.config.ts', 'frontend/tsconfig.json',
            'frontend/tsconfig.app.json', 'frontend/tsconfig.node.json',
        }:
            scope['frontend'] = True
        else:
            # CI rules, generator tooling and paths without a known check owner can affect both jobs.
            scope['backend'] = scope['frontend'] = True
    return scope


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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--baseline', type=Path)
    mode.add_argument('--ci', action='store_true')
    args = parser.parse_args()
    if args.baseline:
        scope = live_scope(args.base, args.target, json.loads(args.baseline.read_text()))
    else:
        subprocess.run(['git', 'merge-base', '--is-ancestor', args.base, args.target], check=True)
        if args.ci:
            # Check both sides of a rename and read Git paths without quoting or line splitting.
            changes = subprocess.check_output(
                ['git', 'diff', '--name-only', '--no-renames', '-z', args.base, args.target]
            )
            scope = classify_ci(os.fsdecode(changes).split('\0')[:-1])
        else:
            paths = subprocess.check_output(['git', 'diff', '--name-only', args.base, args.target], text=True).splitlines()
            scope = classify(paths)
    print(json.dumps(scope))
