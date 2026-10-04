#!/usr/bin/env python3
"""Read baseline/send delta through the existing fixed SSH receiver only."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

# Existing authorized ubuntu login retains its current sudo capability.
# A restricted forced key can also dispatch this exact fixed protocol prefix.
RECEIVER = ['sudo', '-n', '/usr/bin/python3.12', '-I', '/usr/local/libexec/qunxue/receiver.py']


@contextmanager
def connection(checksum=False):
    keys = ['PRODUCTION_CONFIGURED', 'DEPLOY_HOST', 'DEPLOY_USER', 'DEPLOY_KNOWN_HOSTS',
            'DEPLOY_SSH_KEY', 'RELEASE_REVISION']
    if checksum:
        keys.append('RELEASE_SHA256')
    missing = [key for key in keys if not os.environ.get(key)]
    if missing or os.environ.get('PRODUCTION_CONFIGURED') != 'true':
        raise ValueError('Production setup incomplete: ' + ', '.join(missing or ['PRODUCTION_CONFIGURED']))
    env = os.environ
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*', env['DEPLOY_HOST']):
        raise ValueError('Invalid deployment host')
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', env['DEPLOY_USER']):
        raise ValueError('Invalid deployment user')
    if not re.fullmatch(r'[0-9a-f]{40}', env['RELEASE_REVISION']):
        raise ValueError('Invalid revision')
    if checksum and not re.fullmatch(r'[0-9a-f]{64}', env['RELEASE_SHA256']):
        raise ValueError('Invalid digest')
    with tempfile.TemporaryDirectory(prefix='qunxue-deploy-') as directory:
        key, hosts = Path(directory) / 'key', Path(directory) / 'known_hosts'
        key.write_text(env['DEPLOY_SSH_KEY'].rstrip() + '\n')
        hosts.write_text(env['DEPLOY_KNOWN_HOSTS'].rstrip() + '\n')
        key.chmod(0o600)
        hosts.chmod(0o600)
        yield ['ssh', '-T', '-i', str(key), '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
               '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + str(hosts),
               '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15',
               '-o', 'ServerAliveCountMax=60', env['DEPLOY_USER'] + '@' + env['DEPLOY_HOST']]


def baseline(path):
    with connection() as command:
        result = subprocess.run(command + RECEIVER + ['status'], check=True, capture_output=True, timeout=60)
    value = json.loads(result.stdout)
    if value.get('app') != 'qunxue' or not re.fullmatch('[0-9a-f]{40}', value.get('revision', '')):
        raise ValueError('Unverified production baseline')
    path.write_text(json.dumps(value) + '\n')


def send():
    with connection(checksum=True) as command:
        artifact = Path('artifact/qunxue-release.tar.gz')
        checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if checksum != os.environ['RELEASE_SHA256']:
            raise ValueError('Downloaded artifact digest mismatch')
        with artifact.open('rb') as stream:
            subprocess.run(command + RECEIVER + ['deploy', os.environ['RELEASE_REVISION'], checksum],
                           stdin=stream, check=True, timeout=1800)
        print('Uploaded artifact bytes=' + str(artifact.stat().st_size))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--status', type=Path)
    args = parser.parse_args()
    baseline(args.status) if args.status else send()
