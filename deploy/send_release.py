#!/usr/bin/env python3
"""Send bytes to the preinstalled forced-command receiver, never a remote shell script."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile


def send():
    keys = ('PRODUCTION_CONFIGURED', 'DEPLOY_HOST', 'DEPLOY_USER', 'DEPLOY_KNOWN_HOSTS',
            'DEPLOY_SSH_KEY', 'RELEASE_REVISION', 'RELEASE_SHA256')
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
    if not re.fullmatch(r'[0-9a-f]{64}', env['RELEASE_SHA256']):
        raise ValueError('Invalid digest')
    artifact = Path('artifact/qunxue-release.tar.gz')
    checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
    if checksum != env['RELEASE_SHA256']:
        raise ValueError('Downloaded artifact digest mismatch')
    with tempfile.TemporaryDirectory(prefix='qunxue-deploy-') as directory:
        key, hosts = Path(directory) / 'key', Path(directory) / 'known_hosts'
        key.write_text(env['DEPLOY_SSH_KEY'].rstrip() + '\n')
        hosts.write_text(env['DEPLOY_KNOWN_HOSTS'].rstrip() + '\n')
        key.chmod(0o600)
        hosts.chmod(0o600)
        command = ['ssh', '-T', '-i', str(key), '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
                   '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + str(hosts),
                   '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15',
                   '-o', 'ServerAliveCountMax=60',
                   env['DEPLOY_USER'] + '@' + env['DEPLOY_HOST'],
                   'deploy', env['RELEASE_REVISION'], checksum]
        with artifact.open('rb') as stream:
            subprocess.run(command, stdin=stream, check=True, timeout=1800)


if __name__ == '__main__':
    send()
