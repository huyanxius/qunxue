"""Bind a published Release to its exact, checked commit on main (no secrets)."""
import json
import os
from pathlib import Path
import re
import subprocess


def validate(repo, event, revision, ref, event_name):
    if event_name != 'release' or event.get('action') != 'published':
        raise ValueError('Production requires a published GitHub Release')
    release = event.get('release', {})
    if release.get('draft') is not False:
        raise ValueError('Draft releases cannot deploy')
    tag = release.get('tag_name')
    if not isinstance(tag, str) or ref != 'refs/tags/' + tag:
        raise ValueError('Release tag does not match the event ref')
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Release requires an exact commit SHA')
    subprocess.run(['git', 'check-ref-format', ref], cwd=repo, check=True)
    def resolve(value):
        return subprocess.check_output(['git', 'rev-parse', '--verify', value], cwd=repo, text=True).strip()
    if resolve(ref + '^{commit}') != revision or resolve('HEAD') != revision:
        raise ValueError('Release tag, event SHA and checked-out commit must agree')
    subprocess.run(['git', 'merge-base', '--is-ancestor', revision, 'refs/remotes/origin/main'],
                   cwd=repo, check=True)
    return revision


if __name__ == '__main__':
    print(validate(Path.cwd(), json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text()),
                   os.environ['GITHUB_SHA'], os.environ['GITHUB_REF'], os.environ['GITHUB_EVENT_NAME']))
