"""Shared, conservative path hygiene for build and fixed receiver (not a secret scanner)."""
from pathlib import PurePosixPath


def forbidden_payload(name):
    path = PurePosixPath(name)
    return (any(part == '.env' or part.startswith('.env.') or part in
                {'var', 'node_modules', '.venv', '__pycache__', '.git', '.aws', '.ssh'}
                for part in path.parts)
            or path.suffix.lower() in {'.db', '.sqlite', '.sqlite3', '.pem', '.key', '.p12', '.pfx'}
            or path.name.endswith(('-wal', '-shm')))
