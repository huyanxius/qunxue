#!/usr/bin/env python3
"""Build hash-verified locked sdists in CI; emit an offline, wheel-bytes hash lock."""
import argparse
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

from packaging.requirements import Requirement
from packaging.tags import sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def selected_requirements(path):
    selected = {}
    logical = ''
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        logical += ' ' + line.removesuffix('\\').strip()
        if line.endswith('\\'):
            continue
        parts = logical.strip().split(' --hash=')
        requirement = Requirement(parts[0])
        if requirement.url or requirement.extras or len(requirement.specifier) != 1:
            raise ValueError('Expected an exported exact-version dependency')
        pinned = next(iter(requirement.specifier))
        if pinned.operator != '==' or '*' in pinned.version or len(parts) < 2:
            raise ValueError('Every input requires an exact version and source hash')
        if any(not re.fullmatch(r'sha256:[0-9a-f]{64}', item) for item in parts[1:]):
            raise ValueError('Malformed source hash')
        if requirement.marker is None or requirement.marker.evaluate():
            name = canonicalize_name(requirement.name)
            version = str(Version(pinned.version))
            if name in selected and selected[name] != version:
                raise ValueError('Conflicting current-platform versions')
            selected[name] = version
        logical = ''
    if logical.strip() or not selected:
        raise ValueError('Incomplete or empty dependency lock')
    return selected


def wheel_lock(source, wheelhouse, output, provenance):
    expected = selected_requirements(source)
    actual = {}
    accepted_tags = set(sys_tags())
    for path in sorted(wheelhouse.iterdir()):
        if path.is_symlink() or not path.is_file() or path.suffix != '.whl':
            raise ValueError('Wheelhouse contains a non-wheel')
        name, version, _, tags = parse_wheel_filename(path.name)
        name = canonicalize_name(name)
        if name in actual or expected.get(name) != str(version) or not tags & accepted_tags:
            raise ValueError('Duplicate, unexpected, wrong-version or incompatible wheel: ' + path.name)
        with zipfile.ZipFile(path) as wheel:
            metadata = [item for item in wheel.namelist()
                        if item.count('/') == 1 and item.endswith('.dist-info/METADATA')]
            if len(metadata) != 1:
                raise ValueError('Ambiguous wheel metadata')
            info = BytesParser().parsebytes(wheel.read(metadata[0]))
            if canonicalize_name(info['Name']) != name or Version(info['Version']) != version:
                raise ValueError('Wheel filename and metadata identities differ')
        actual[name] = {'version': str(version), 'sha256': digest(path), 'filename': path.name}
    if set(actual) != set(expected):
        raise ValueError('Wheelhouse is incomplete for the locked current-platform dependency set')
    output.write_text('# Offline wheel hashes built from the unchanged source lock.\n' + ''.join(
        name + '==' + record['version'] + ' --hash=sha256:' + record['sha256'] + '\n'
        for name, record in sorted(actual.items())))
    provenance.write_text(json.dumps({'source_requirements_sha256': digest(source),
                                     'python': sys.version.split()[0], 'wheels': actual},
                                    sort_keys=True, indent=2) + '\n')
    return actual


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-requirements', type=Path, required=True)
    parser.add_argument('--wheelhouse', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--provenance', type=Path, required=True)
    args = parser.parse_args()
    selected_requirements(args.source_requirements)
    args.wheelhouse.mkdir(parents=True, exist_ok=True)
    if any(args.wheelhouse.iterdir()):
        raise ValueError('Build into a fresh empty wheelhouse')
    # Build isolation is deliberately off: CI installs hash-pinned build tooling first.
    # All app inputs retain the source lock's hashes. No dependency re-resolution/upgrade.
    subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--disable-pip-version-check',
                    '--require-hashes', '--no-deps', '--no-build-isolation', '--no-cache-dir',
                    '--wheel-dir', str(args.wheelhouse), '-r', str(args.source_requirements)], check=True)
    rows = wheel_lock(args.source_requirements, args.wheelhouse, args.output, args.provenance)
    print('Verified ' + str(len(rows)) + ' offline wheels against locked names/versions')


if __name__ == '__main__':
    main()
