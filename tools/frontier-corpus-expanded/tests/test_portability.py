#!/usr/bin/env python3
"""Move the package, forbid network, and verify frozen outputs and fail-closed inputs."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

BLOCK_NETWORK = """
import runpy, socket, sys, urllib.request
def blocked(*args, **kwargs):
    raise AssertionError('Offline reconstruction attempted network access')
socket.socket = blocked
socket.create_connection = blocked
socket.getaddrinfo = blocked
urllib.request.urlopen = blocked
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name='__main__')
"""


def run(script, *args, cwd):
    return subprocess.run(
        [sys.executable, '-c', BLOCK_NETWORK, str(script), *map(str, args)],
        cwd=cwd, text=True, capture_output=True, timeout=30,
    )


def main():
    with tempfile.TemporaryDirectory(prefix='qunxue-expanded-portable-') as name:
        base = Path(name)
        package = base / 'relocated' / 'corpus tools'
        shutil.copytree(ROOT, package, ignore=shutil.ignore_patterns('build', '__pycache__', '*.pyc'))
        cwd = base / 'unrelated cwd'
        cwd.mkdir()
        output = cwd / 'output corpus'
        assemble = package / 'tools' / 'assemble_expanded.py'
        validate = package / 'tools' / 'validate_expanded.py'
        result = run(assemble, '--output', 'output corpus', cwd=cwd)
        assert result.returncode == 0, result.stderr
        snapshot = json.loads((package / 'snapshot.json').read_text(encoding='utf-8'))
        for filename, expected in snapshot['expected_output_sha256'].items():
            assert hashlib.sha256((output / filename).read_bytes()).hexdigest() == expected, filename
        result = run(validate, '--output', output, cwd=cwd)
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)
        assert (report['display_records'], report['research_index_with_reviewed_supplements'],
                report['awaiting_assistant_synthesis']) == (276, 517, 244)

        source = package / 'ruc' / 'reviewed-records.json'
        original = source.read_bytes()
        source.unlink()
        missing_output = cwd / 'missing-input-output'
        result = run(assemble, '--output', missing_output, cwd=cwd)
        assert result.returncode != 0 and 'Missing or changed frozen input' in result.stderr
        assert not missing_output.exists()
        source.write_bytes(original + b'\n')
        changed_output = cwd / 'changed-input-output'
        result = run(assemble, '--output', changed_output, cwd=cwd)
        assert result.returncode != 0 and 'Missing or changed frozen input' in result.stderr
        assert not changed_output.exists()
        source.write_bytes(original)

        manifest = json.loads(source.read_text(encoding='utf-8'))
        shard = source.parent / manifest['parts'][0]['path']
        shard_original = shard.read_bytes()
        shard.write_bytes(shard_original + b'\n')
        result = run(assemble, '--output', cwd / 'changed-shard', cwd=cwd)
        assert result.returncode != 0 and 'Missing or changed frozen input' in result.stderr
        shard.unlink()
        result = run(assemble, '--output', cwd / 'missing-shard', cwd=cwd)
        assert result.returncode != 0 and 'Missing or changed frozen input' in result.stderr
        shard.write_bytes(shard_original)

        print(json.dumps({'passed': True, 'network_forbidden': True,
                          'relocated_package_and_unrelated_cwd': True,
                          'all_frozen_output_hashes_match': True,
                          'missing_and_changed_inputs_rejected': True,
                          'display_records': 276, 'research_index': 517,
                          'not_displayed_pending_synthesis': 244}))


if __name__ == '__main__':
    main()
