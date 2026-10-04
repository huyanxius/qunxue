"""Use the actual production baseline, never just the previous main commit."""
import argparse
import json
import subprocess


def classify(paths):
    backend = frontend = dependencies = False
    for path in paths:
        if path.startswith(('backend/src/', 'backend/migrations/', 'backend/data/', 'knowledge/')) or path in {'backend/alembic.ini', 'backend/pyproject.toml', 'backend/uv.lock'}:
            backend = True
        if path.startswith('frontend/') and not path.startswith(('frontend/node_modules/', 'frontend/dist/')):
            frontend = True
        if path in {'backend/uv.lock', 'backend/pyproject.toml'}:
            dependencies = True
    return {'backend': backend, 'frontend': frontend, 'dependencies': dependencies}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('base')
    parser.add_argument('target')
    args = parser.parse_args()
    subprocess.run(['git', 'merge-base', '--is-ancestor', args.base, args.target], check=True)
    paths = subprocess.check_output(['git', 'diff', '--name-only', args.base, args.target], text=True).splitlines()
    print(json.dumps(classify(paths)))
