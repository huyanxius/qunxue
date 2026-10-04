"""Shared payload hygiene and backend-change rules for build and fixed receiver."""
from pathlib import PurePosixPath


def forbidden_payload(name):
    path = PurePosixPath(name)
    return (any(part == '.env' or part.startswith('.env.') or part in
                {'var', 'node_modules', '.venv', '__pycache__', '.git', '.aws', '.ssh'}
                for part in path.parts)
            or path.suffix.lower() in {'.db', '.sqlite', '.sqlite3', '.pem', '.key', '.p12', '.pfx'}
            or path.name.endswith(('-wal', '-shm')))


def backend_changed(previous, current):
    """Build and receiver agree on runtime bytes and the locked dependency closure."""
    if previous.get('dependency_lock_sha256') != current.get('dependency_lock_sha256'):
        return True
    old, new = previous['files'], current['files']
    return any((name.startswith(('backend/', 'knowledge/', 'wheelhouse/')) or name == 'requirements.lock')
               and old.get(name) != new.get(name) for name in set(old) | set(new))
