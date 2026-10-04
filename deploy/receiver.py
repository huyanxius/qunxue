#!/usr/bin/env python3
"""Preinstalled, root-owned qunxue receiver. Never replace this file from a release.

The dedicated SSH key must use this as its forced command with forwarding, PTY,
agent forwarding, X11 and user rc disabled. Application code runs as runtime_uid.
"""
import ast
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import pwd
import re
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

# The root-owned receiver is launched with Python -I; import only its audited sibling.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from payload_rules import backend_changed as changed_backend, forbidden_payload

CONFIG = Path('/etc/qunxue/deploy.json')
MAX_ARCHIVE = 1024 * 1024 * 1024
MAX_EXPANDED = 3 * MAX_ARCHIVE
SHA = re.compile(r'[0-9a-f]{40}')
HASH = re.compile(r'[0-9a-f]{64}')


@contextmanager
def recovery_signals():
    """Do not let repeated SSH HUP/termination abort bounded recovery commands."""
    signals = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)
    previous = {number: signal.getsignal(number) for number in signals}
    try:
        for number in signals:
            signal.signal(number, signal.SIG_IGN)
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def trusted(path):
    """Protect host configuration and every directory leading to it."""
    for part in (path, *path.parents):
        info = part.lstat()
        require(not stat.S_ISLNK(info.st_mode), 'Trusted host path cannot be a symlink')
        require(info.st_uid == 0 and not info.st_mode & 0o022,
                'Host configuration must be root-owned and not group/world writable')


def load_config():
    trusted(CONFIG)
    config = json.loads(CONFIG.read_text())
    require(config.get('configured') is True, 'Production adapter has not been approved/configured')
    require(config.get('version') == 1 and config.get('app') == 'qunxue', 'Wrong host adapter')
    require(config.get('all_writers_are_qunxue_pm2') is True,
            'All database writers must be inventoried and quiesced by qunxue PM2 stop')
    require(type(config.get('runtime_uid')) is int and config['runtime_uid'] > 0,
            'A dedicated non-root qunxue runtime identity is required')
    require(type(config.get('runtime_gid')) is int and config['runtime_gid'] > 0,
            'A dedicated runtime group is required')
    require(os.geteuid() == 0, 'Fixed receiver must manage metadata as root; app commands drop privileges')
    require(config['root'] == '/srv/qunxue', 'Release controller is scoped only to /srv/qunxue')
    require(config['ecosystem'] == '/etc/qunxue/ecosystem.config.cjs', 'Unexpected PM2 adapter path')
    require(config['release_mode'] == '0755', 'Release mode must be explicitly 0755')
    for key in ('python', 'pm2', 'pm2_home', 'environment_file', 'state_directory'):
        require(Path(config[key]).is_absolute() and 'REQUIRED' not in config[key], 'Unconfigured ' + key)
    trusted(Path(config['ecosystem']))
    require(platform.system() == 'Linux' and platform.machine() == 'x86_64', 'Unsupported host platform')
    require(config['expected_runtime_mode'] in ('base', 'sft'), 'Production must not use mock mode')
    require(1 <= config['health_attempts'] <= 30, 'Invalid bounded health attempts')
    for key in ('public_origin', 'local_origin'):
        url = urlsplit(config[key])
        require(url.scheme in ('https', 'http') and url.netloc and not url.username
                and not url.password and url.path in ('', '/') and not url.query and not url.fragment,
                'Invalid ' + key)
    require(config['public_origin'].startswith('https://') and '.invalid' not in config['public_origin'],
            'A verified public HTTPS origin is required')
    require(config['local_origin'] == 'http://127.0.0.1:8096', 'Expected verified Nginx upstream 8096')
    dbs = config['databases']
    require(len(dbs) == 3 and len({x['name'] for x in dbs}) == 3
            and len({x['path'] for x in dbs}) == 3, 'All three distinct verified SQLite files are required')
    require(sum(x['migrate'] is True for x in dbs) == 1, 'Exactly one explicitly identified primary DB')
    for db in dbs:
        require(re.fullmatch(r'[a-z][a-z0-9_-]{0,31}', db['name']), 'Invalid database label')
        path = Path(db['path'])
        require(path.is_absolute() and path.is_file() and not path.is_symlink(), 'Missing explicit DB path')
        require(path.resolve().is_relative_to(Path(config['state_directory']).resolve()),
                'All databases must be under the approved shared-state directory')
    environment = Path(config['environment_file'])
    require(environment.is_file() and not environment.is_symlink(), 'Missing explicit environment file')
    info = environment.stat()
    require(not info.st_mode & 0o007, 'Environment file cannot be world-readable/writable')
    require(Path(config['state_directory']).is_dir(), 'Missing verified state directory')
    require(Path(config['pm2_home']).is_dir(), 'Existing PM2 home must be verified, never invented')
    return config


def write_json(path, value, mode=0o600):
    """Atomic metadata replacement keeps the old owner's uid, gid and permissions."""
    require(not path.is_symlink(), 'Controller metadata must not be a symlink')
    previous = path.stat() if path.exists() else None
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            os.fchmod(handle.fileno(), stat.S_IMODE(previous.st_mode) if previous else mode)
            if previous:
                os.fchown(handle.fileno(), previous.st_uid, previous.st_gid)
            json.dump(value, handle, sort_keys=True)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_pointer(current, target):
    require(current.is_symlink(), 'Bootstrap must establish the single current release symlink')
    info = current.lstat()
    temporary = current.parent / ('.current-' + str(os.getpid()))
    require(not temporary.exists() and not temporary.is_symlink(), 'Unexpected temporary pointer')
    try:
        temporary.symlink_to(target)
        os.lchown(temporary, info.st_uid, info.st_gid)
        os.replace(temporary, current)
        directory = os.open(current.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.is_symlink():
            temporary.unlink()


def receive(stream, path, expected):
    total = 0
    with path.open('xb') as output:
        os.chmod(path, 0o600)
        while block := stream.read(1024 * 1024):
            total += len(block)
            require(total <= MAX_ARCHIVE, 'Archive exceeds size limit')
            output.write(block)
        output.flush()
        os.fsync(output.fileno())
    require(sha256(path) == expected, 'Artifact SHA256 mismatch')


def extract(archive, stage, revision, previous=None):
    """No links, devices, absolute paths, traversal, duplicates or unmanifested bytes."""
    with tarfile.open(archive, 'r:gz') as handle:
        members = handle.getmembers()
        names = set()
        total = 0
        for member in members:
            path = PurePosixPath(member.name)
            require(member.isfile() and not path.is_absolute() and '..' not in path.parts
                    and str(path) == member.name and '\\' not in member.name,
                    'Unsafe archive member')
            require(member.name not in names, 'Duplicate archive member')
            names.add(member.name)
            total += member.size
            require(total <= MAX_EXPANDED and len(names) <= 50000, 'Expanded archive exceeds limit')
        require('release.json' in names, 'Missing release manifest')
        manifest = json.load(handle.extractfile('release.json'))
        require(manifest['version'] in (1, 2) and manifest['app'] == 'qunxue'
                and manifest['revision'] == revision, 'Release identity mismatch')
        require(manifest['python'] == '3.12' and manifest['platform'] == 'linux-x86_64',
                'Artifact runtime mismatch')
        delta = manifest['version'] == 2
        payload = set(manifest.get('payload', manifest['files']))
        require(payload | {'release.json'} == names and payload <= set(manifest['files']),
                'Manifest membership mismatch')
        if delta:
            require(previous is not None, 'Delta needs an existing verified baseline')
            old = json.loads((previous / 'release.json').read_text())
            require(old['revision'] == manifest['base_revision'], 'Stale delta baseline')
        else:
            old = None
        for name, digest in manifest['files'].items():
            path = PurePosixPath(name)
            require(not path.is_absolute() and '..' not in path.parts and str(path) == name
                    and '\\' not in name, 'Unsafe manifest path')
            require(HASH.fullmatch(digest), 'Invalid file digest')
            require(name.startswith(('backend/src/', 'backend/migrations/', 'backend/data/',
                                     'knowledge/', 'frontend/', 'wheelhouse/'))
                    or name in ('backend/alembic.ini', 'requirements.lock', 'deploy/migration-policy.json'),
                    'File is outside the application payload')
            require(not forbidden_payload(name), 'Credential/runtime state in artifact')
        stage.mkdir(mode=0o755)
        for member in members:
            target = stage / member.name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            with handle.extractfile(member) as source, target.open('xb') as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o644)
            if member.name != 'release.json':
                require(sha256(target) == manifest['files'][member.name], 'File integrity mismatch')
        if delta:
            for name in set(manifest['files']) - payload:
                require(old['files'].get(name) == manifest['files'][name], 'Unverified reused baseline content')
                source = previous / name
                require(source.is_file() and not source.is_symlink()
                        and sha256(source) == manifest['files'][name], 'Reused baseline digest mismatch')
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                # Independent files: runtime preparation must not chmod/chown the prior release.
                shutil.copyfile(source, target)
                target.chmod(0o644)
        require((stage / 'frontend/index.html').is_file(), 'Frontend index missing')
        if not delta:
            require(any((stage / 'wheelhouse').glob('*.whl')), 'Offline wheelhouse missing')
            require(json.loads((stage / 'deploy/migration-policy.json').read_text())
                    == manifest['migration_policy'], 'Migration policy mismatch')
        return manifest


def migration_changes(previous, release, policy):
    old_root, new_root = previous / 'backend/migrations', release / 'backend/migrations'
    old = {str(p.relative_to(old_root)): sha256(p) for p in old_root.rglob('*.py')}
    new = {str(p.relative_to(new_root)): sha256(p) for p in new_root.rglob('*.py')}
    require(old and new, 'Migration inventories must be present')
    require(all(new.get(name) == digest for name, digest in old.items()),
            'Existing migration modified/deleted; use an audited expand-only migration')
    additions = set(new) - set(old)
    require(policy.get('version') == 1 and policy.get('strategy') == 'expand-only'
            and policy.get('rollback_compatible') is True, 'Explicit compatible migration policy required')
    require(set(policy.get('approved_additions', [])) == additions,
            'Changed migration set requires an exact reviewed rollback-compatible declaration')
    require(all(name.startswith('versions/') for name in additions), 'Only new revisions are allowed')
    for name in additions:
        validate_expand_migration((new_root / name).read_text())
    return additions


def validate_expand_migration(source):
    """Deliberately narrow, fail-closed subset; other migrations need maintenance review.

    No arbitrary helpers, aliases, module execution, SQL, backfills, constraints on
    existing tables, or required columns. Only ordinary SQLAlchemy constructors.
    """
    tree = ast.parse(source)
    upgrade = None
    constructors = {'String', 'Text', 'Integer', 'BigInteger', 'SmallInteger', 'Boolean',
                    'Float', 'Numeric', 'Date', 'DateTime', 'Time', 'LargeBinary', 'JSON',
                    'Column', 'PrimaryKeyConstraint', 'ForeignKeyConstraint', 'UniqueConstraint'}

    def literal(node):
        return isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool, type(None)))

    def value(node):
        if literal(node):
            return True
        if isinstance(node, (ast.Tuple, ast.List)):
            return all(literal(item) for item in node.elts)
        if isinstance(node, ast.Attribute):
            return isinstance(node.value, ast.Name) and node.value.id == 'sa' and node.attr in constructors
        if isinstance(node, ast.Call):
            return (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == 'sa' and node.func.attr in constructors
                    and all(value(arg) for arg in node.args)
                    and all(keyword.arg in {'nullable', 'primary_key', 'unique', 'index', 'name',
                                            'length', 'precision', 'scale', 'timezone', 'autoincrement',
                                            'ondelete', 'onupdate', 'server_default'}
                            and literal(keyword.value) for keyword in node.keywords))
        return False

    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, ast.Import):
            require(len(node.names) == 1 and node.names[0].name == 'sqlalchemy'
                    and node.names[0].asname == 'sa', 'Only import sqlalchemy as sa is allowed')
        elif isinstance(node, ast.ImportFrom):
            require(node.module == 'alembic' and node.level == 0 and len(node.names) == 1
                    and node.names[0].name == 'op' and node.names[0].asname is None,
                    'Opaque migration imports are not allowed')
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            require(all(isinstance(target, ast.Name) and target.id in
                        {'revision', 'down_revision', 'branch_labels', 'depends_on'} for target in targets)
                    and (literal(node.value) or isinstance(node.value, (ast.Tuple, ast.List))
                         and all(literal(item) for item in node.value.elts)),
                    'Only literal revision metadata is allowed')
            if isinstance(node, ast.AnnAssign):
                require(isinstance(node.annotation, ast.Name) and node.annotation.id in ('str', 'tuple'),
                        'Opaque annotation is not allowed')
        elif isinstance(node, ast.FunctionDef):
            require(node.name in ('upgrade', 'downgrade') and not node.decorator_list
                    and not node.args.args and not node.args.posonlyargs and not node.args.defaults and not node.args.kwonlyargs
                    and not getattr(node, 'type_params', [])
                    and node.args.vararg is None and node.args.kwarg is None
                    and (node.returns is None or isinstance(node.returns, ast.Constant)
                         and node.returns.value is None), 'Opaque migration functions are not allowed')
            if node.name == 'upgrade':
                require(upgrade is None, 'Duplicate upgrade function')
                upgrade = node
        else:
            raise RuntimeError('Opaque/destructive module execution requires maintenance review')
    require(upgrade is not None, 'Migration upgrade function missing')
    for statement in upgrade.body:
        if isinstance(statement, ast.Pass):
            continue
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str):
            continue
        require(isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call),
                'Opaque migration statements require maintenance review')
        call = statement.value
        require(isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)
                and call.func.value.id == 'op' and call.func.attr in ('create_table', 'create_index', 'add_column'),
                'Destructive/opaque migration operation requires maintenance review')
        require(call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str)
                and all(value(arg) for arg in call.args) and all(keyword.arg is not None
                    and literal(keyword.value) for keyword in call.keywords),
                'Opaque migration arguments require maintenance review')
        if call.func.attr == 'add_column':
            require(len(call.args) == 2 and not call.keywords, 'add_column only accepts table and column')
            column = call.args[1]
            require(isinstance(column, ast.Call) and isinstance(column.func, ast.Attribute)
                    and column.func.attr == 'Column' and len(column.args) == 2
                    and any(keyword.arg == 'nullable' and isinstance(keyword.value, ast.Constant)
                            and keyword.value.value is True for keyword in column.keywords)
                    and all(keyword.arg in ('nullable', 'server_default') for keyword in column.keywords),
                    'Existing tables may only receive explicitly nullable unconstrained columns')
        elif call.func.attr == 'create_index':
            require(len(call.args) == 3 and all(keyword.arg == 'unique' and keyword.value.value is False
                                              for keyword in call.keywords),
                    'Only non-unique indexes are automatically deployable')
        else:
            require(not call.keywords and len(call.args) >= 2,
                    'create_table must use literal columns/constraints without special options')


def app_command(config, argv, cwd=None, revision=None, extra_env=None, timeout=300):
    """No shell=True; retain only the explicitly configured application identity."""
    account = pwd.getpwuid(config['runtime_uid'])
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': account.pw_dir,
           'LANG': 'C.UTF-8', 'PM2_HOME': config['pm2_home'], 'PYTHONDONTWRITEBYTECODE': '1'}
    if revision:
        env['QUNXUE_RELEASE_REVISION'] = revision
    env.update(extra_env or {})
    return subprocess.run(argv, cwd=cwd, env=env, user=config['runtime_uid'],
                          group=config['runtime_gid'], extra_groups=[], check=True,
                          capture_output=True, text=True, timeout=timeout)


def pm2(config, operation, revision=None):
    require(operation in ('stop', 'start'), 'Unsupported process operation')
    args = ([config['pm2'], 'stop', 'qunxue-api'] if operation == 'stop' else
            [config['pm2'], 'startOrRestart', config['ecosystem'], '--only', 'qunxue-api', '--update-env'])
    app_command(config, args, revision=revision, timeout=360)


def check_process(config, stopped=False):
    result = app_command(config, [config['pm2'], 'jlist'])
    processes = [p for p in json.loads(result.stdout) if p['name'] == 'qunxue-api']
    require(len(processes) == 1 and processes[0]['pm2_env']['exec_mode'] == 'fork_mode'
            and processes[0]['pm2_env']['status'] == ('stopped' if stopped else 'online'),
            'Unexpected qunxue-api process state')
    if stopped:
        require(not processes[0].get('pid'), 'Old database writer is still running')
    return processes[0].get('pid', 0)


def prepare_runtime(config, release, revision, previous=None):
    result = app_command(config, [config['python'], '-c',
                                 'import sys; print(".".join(map(str,sys.version_info[:2])))'])
    require(result.stdout.strip() == '3.12', 'Python 3.12 must be preinstalled')
    for directory, dirs, files in os.walk(release):
        os.chown(directory, config['runtime_uid'], config['runtime_gid'])
        for name in files:
            os.chown(Path(directory) / name, config['runtime_uid'], config['runtime_gid'])
    backend = release / 'backend'
    python = backend / '.venv/bin/python'
    manifest = json.loads((release / 'release.json').read_text())
    old = json.loads((previous / 'release.json').read_text()) if previous else {}
    reuse = (previous is not None and manifest['dependency_lock_sha256'] == old.get('dependency_lock_sha256')
             and (previous / 'backend/.venv/bin/python').is_file())
    if reuse:
        (backend / '.venv').symlink_to((previous / 'backend/.venv').resolve())
    else:
        app_command(config, [config['python'], '-m', 'venv', str(backend / '.venv')], timeout=120)
        app_command(config, [str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
                            '--no-index', '--find-links', str(release / 'wheelhouse'), '--require-hashes',
                            '-r', str(release / 'requirements.lock')], timeout=600)
    (backend / '.env').symlink_to(config['environment_file'])
    (backend / 'var').symlink_to(config['state_directory'])
    primary = next(db for db in config['databases'] if db['migrate'])
    app_command(config, [str(python), '-m', 'pip', 'check'], cwd=backend)
    code = ('import qunxue_api.bootstrap; from pathlib import Path; from sqlalchemy.engine import make_url; '
            'from qunxue_api.settings import Settings; s=Settings(); '
            'print(Path(make_url(s.database_url).database).resolve()); print(s.runtime_mode)')
    result = app_command(config, [str(python), '-c', code], cwd=backend, revision=revision,
                         extra_env={'PYTHONPATH': str(backend / 'src')})
    require(result.stdout.strip().splitlines() == [str(Path(primary['path']).resolve()),
                                                  config['expected_runtime_mode']],
            'Runtime settings do not match inventoried primary database/mode')
    # Freeze release files after installation. Shared state/env symlinks are untouched.
    for directory, dirs, files in os.walk(release, followlinks=False):
        os.chown(directory, 0, config['runtime_gid'])
        os.chmod(directory, 0o755)
        for name in files:
            target = Path(directory) / name
            if target.is_symlink():
                continue
            mode = target.stat().st_mode
            os.chown(target, 0, config['runtime_gid'])
            os.chmod(target, 0o755 if mode & 0o111 else 0o644)


def snapshot_databases(config, destination):
    """Called only after all writers stop; SQLite Online Backup includes WAL content."""
    destination.mkdir(mode=0o700)
    inventory = []
    for database in config['databases']:
        source = Path(database['path'])
        info = source.stat()
        target = destination / (database['name'] + '.sqlite3')
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=30) as src:
            require(src.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'Source DB corrupt')
            require(not src.execute('PRAGMA foreign_key_check').fetchall(), 'Source FK violation')
            with sqlite3.connect(target) as dst:
                src.backup(dst)
                require(dst.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'Backup corrupt')
                tables = [row[0] for row in dst.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
                counts = {name: dst.execute('SELECT count(*) FROM "' + name.replace('"', '""') + '"')
                          .fetchone()[0] for name in tables}
        target.chmod(0o600)
        inventory.append({'name': database['name'], 'source': str(source), 'backup': target.name,
                          'sha256': sha256(target), 'uid': info.st_uid, 'gid': info.st_gid,
                          'mode': stat.S_IMODE(info.st_mode), 'table_counts': counts})
    write_json(destination / 'inventory.json', inventory)
    return inventory


def validate_database_metadata(inventory):
    for database in inventory:
        info = Path(database['source']).stat()
        require((info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) ==
                (database['uid'], database['gid'], database['mode']), 'Database metadata changed')


DB_ONLY_DRIVER = r"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

def db_only(event, args):
    if event.startswith(('socket.', 'subprocess.', 'os.exec', 'os.spawn')) or event == 'os.system':
        raise RuntimeError('Network/process creation is forbidden during database-only migration')
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0]))
        if path.name == '.env' or path.name.startswith('.env.') or str(path.resolve()) == sys.argv[3]:
            raise RuntimeError('Production secret file access is forbidden during migration')

sys.addaudithook(db_only)
from qunxue_api import settings
# The existing Alembic env reads only Settings().database_url. Do not load .env.
settings.Settings = lambda: SimpleNamespace(database_url='sqlite:///' + sys.argv[1])
from alembic import command
from alembic.config import Config
command.upgrade(Config(sys.argv[2]), 'head')
"""


def migrate(config, release, revision, database_override=None):
    backend = release / 'backend'
    primary = next(db for db in config['databases'] if db['migrate'])
    database = database_override or Path(primary['path'])
    app_command(config, [str(backend / '.venv/bin/python'), '-c', DB_ONLY_DRIVER, str(database),
                        str(backend / 'alembic.ini'), str(Path(config['environment_file']).resolve())],
                cwd=backend, revision=revision,
                extra_env={'PYTHONPATH': str(backend / 'src')}, timeout=600)


def validate_database_contents(inventory, overrides=None):
    for database in inventory:
        path = (overrides or {}).get(database['name'], Path(database['source']))
        with sqlite3.connect(Path(path).as_uri() + '?mode=ro', uri=True) as connection:
            require(connection.execute('PRAGMA integrity_check').fetchall() == [('ok',)],
                    'Migrated database failed integrity validation')
            require(not connection.execute('PRAGMA foreign_key_check').fetchall(),
                    'Migrated database has foreign key violations')
            for table, expected in database['table_counts'].items():
                if table == 'alembic_version' or table.startswith('sqlite_'):
                    continue
                quoted = '"' + table.replace('"', '""') + '"'
                count = connection.execute('SELECT count(*) FROM ' + quoted).fetchone()[0]
                require(count == expected, 'Existing table row counts changed during migration')


def rehearse_migration(config, release, revision, inventory, backup):
    # Rehearse on an isolated copy of the final consistent primary snapshot.
    # No application server/model workers start. A failed rehearsal leaves live DBs unchanged.
    primary = next(db for db in config['databases'] if db['migrate'])
    directory = release / 'migration-rehearsal'
    directory.mkdir(mode=0o700)
    os.chown(directory, config['runtime_uid'], config['runtime_gid'])
    snapshot = next(db for db in inventory if db['name'] == primary['name'])
    target = directory / 'primary.sqlite3'
    shutil.copyfile(backup / snapshot['backup'], target)
    os.chown(target, config['runtime_uid'], config['runtime_gid'])
    target.chmod(0o600)
    try:
        migrate(config, release, revision, target)
        validate_database_contents([snapshot], {snapshot['name']: target})
    finally:
        # Only this synthetic copy is removed; retained recovery snapshots are untouched.
        shutil.rmtree(directory)


def fetch(url):
    request = Request(url, headers={'Cache-Control': 'no-cache', 'Pragma': 'no-cache'})
    with urlopen(request, timeout=15) as response:
        require(response.status == 200, 'Health/asset HTTP status is not 200')
        require(response.geturl().split('?', 1)[0] == url.split('?', 1)[0], 'Unexpected redirect')
        return response.read(32 * 1024 * 1024 + 1)


def health(config, release, revision):
    manifest = json.loads((release / 'release.json').read_text())
    frontend_files = {name.removeprefix('frontend/'): digest for name, digest in manifest['files'].items()
                      if name.startswith('frontend/')}
    require('index.html' in frontend_files, 'No frontend identity')
    # Validate the served index plus every built public JS/CSS asset against the artifact.
    selected = {name: digest for name, digest in frontend_files.items()
                if name == 'index.html' or name.endswith(('.js', '.css'))}
    for origin in (config['local_origin'], config['public_origin']):
        data = json.loads(fetch(origin.rstrip('/') + '/api/health?release=' + revision))
        require(data.get('status') == 'ok' and data.get('release_revision') == manifest.get('backend_revision', revision)
                and data.get('runtime_mode') == config['expected_runtime_mode'],
                'API health/revision/runtime mismatch')
        for name, digest in selected.items():
            require(re.fullmatch(r'[A-Za-z0-9_./-]+', name) and '..' not in PurePosixPath(name).parts,
                    'Unsafe public asset path')
            endpoint = '' if name == 'index.html' else name
            content = fetch(origin.rstrip('/') + '/' + endpoint + '?release=' + revision)
            require(hashlib.sha256(content).hexdigest() == digest, 'Public asset mismatch: ' + name)


def wait_healthy(config, release, revision):
    for attempt in range(config['health_attempts']):
        try:
            health(config, release, revision)
            check_process(config)
            return
        except Exception:
            if attempt + 1 == config['health_attempts']:
                raise
            time.sleep(5)


def active_release(config):
    root = Path(config['root'])
    current = root / 'current'
    require(current.is_symlink(), 'Initial release-pointer bootstrap is required')
    release = current.resolve(strict=True)
    require(release.parent == root / 'releases', 'Current pointer must target an app-scoped release')
    manifest = json.loads((release / 'release.json').read_text())
    revision = manifest['revision']
    require(SHA.fullmatch(revision) and release.name == revision and manifest['app'] == 'qunxue',
            'Current release baseline needs an audited full-SHA manifest')
    return release, revision


def capacity_preflight(config, root, archive_size):
    # Budget actual DB + WAL footprints, every backup, and the primary rehearsal.
    # The extra 2x margin covers SQLite rewrite/journal growth while readers are stopped.
    footprints = []
    primary = 0
    for database in config['databases']:
        path = Path(database['path'])
        size = path.stat().st_size
        for suffix in ('-wal', '-shm'):
            sidecar = Path(str(path) + suffix)
            if sidecar.exists():
                size += sidecar.stat().st_size
        footprints.append(size)
        if database['migrate']:
            primary = size
    required = (config['minimum_free_bytes'] + MAX_EXPANDED + archive_size
                + 2 * (sum(footprints) + primary))
    require(shutil.disk_usage(root).free >= required,
            'Insufficient free space for actual databases, WAL, rehearsal and recovery reserve')
    # Live DBs may occupy another mount. Check its write/migration reserve separately.
    for database, footprint in zip(config['databases'], footprints):
        require(shutil.disk_usage(Path(database['path']).parent).free >=
                config['minimum_free_bytes'] + 2 * footprint,
                'Insufficient free space on a live database filesystem')
    return required


def deploy(config, archive, revision, checksum):
    root = Path(config['root'])
    previous, previous_revision = active_release(config)
    require(revision != previous_revision, 'Revision already active; no changes made')
    release = root / 'releases' / revision
    require(not release.exists(), 'Immutable release already exists; inspect failed attempt before retry')
    capacity_preflight(config, root, archive.stat().st_size)
    require(sha256(archive) == checksum, 'Incoming archive changed')
    previous_pid = check_process(config)
    manifest = extract(archive, release, revision, previous=previous)
    additions = migration_changes(previous, release, manifest['migration_policy'])
    old_manifest = json.loads((previous / 'release.json').read_text())
    backend_changed = changed_backend(old_manifest, manifest)
    backend_revision = revision if backend_changed else old_manifest.get('backend_revision', previous_revision)
    require(manifest.get('backend_revision', revision) == backend_revision, 'Backend source identity mismatch')
    if backend_changed:
        prepare_runtime(config, release, backend_revision, previous=previous)
    else:
        # Frontend/metadata changes reuse an already verified runtime without importing app code.
        (release / 'backend/.venv').symlink_to((previous / 'backend/.venv').resolve())
        (release / 'backend/.env').symlink_to(config['environment_file'])
        (release / 'backend/var').symlink_to(config['state_directory'])
    # Preflight previous release identity before any interruption or migration.
    health(config, previous, previous_revision)
    capacity_preflight(config, root, archive.stat().st_size)
    journal = root / 'deployment-state.json'
    state = {'phase': 'prepared', 'revision': revision, 'previous_revision': previous_revision,
             'artifact_sha256': checksum, 'backup': str(root / 'backups' / revision)}
    write_json(journal, state)
    inventory = []
    stopped = False
    try:
        # Mark stopped before invoking PM2: timeout can mean the stop partially completed.
        if backend_changed:
            stopped = True
            pm2(config, 'stop')
            check_process(config, stopped=True)
            require(not Path('/proc/' + str(previous_pid)).exists(), 'Previous writer PID still exists')
            state['phase'] = 'stopped'
            write_json(journal, state)
        if additions:
            # Only an actual reviewed schema expansion requires quiescing and snapshots.
            inventory = snapshot_databases(config, root / 'backups' / revision)
            state['phase'] = 'backed-up'
            write_json(journal, state)
            rehearse_migration(config, release, revision, inventory, root / 'backups' / revision)
            migrate(config, release, revision)
            validate_database_contents(inventory)
            validate_database_metadata(inventory)
            state['phase'] = 'migrated'
            write_json(journal, state)
        atomic_pointer(root / 'current', release)
        state['phase'] = 'switched'
        write_json(journal, state)
        if backend_changed:
            pm2(config, 'start', backend_revision)
        wait_healthy(config, release, revision)
        if inventory:
            validate_database_metadata(inventory)
        if backend_changed:
            app_command(config, [config['pm2'], 'save'])
        state['phase'] = 'healthy'
        write_json(journal, state)
    except BaseException:
        if stopped or (root / 'current').resolve() == release:
            # Forward schema changes remain. Never downgrade, restore, or overwrite a live DB.
            with recovery_signals():
                try:
                    if stopped:
                        pm2(config, 'stop')
                    atomic_pointer(root / 'current', previous)
                    if stopped:
                        pm2(config, 'start', old_manifest.get('backend_revision', previous_revision))
                    wait_healthy(config, previous, previous_revision)
                    if inventory:
                        validate_database_metadata(inventory)
                    app_command(config, [config['pm2'], 'save'])
                    state['phase'] = 'rolled-back'
                    write_json(journal, state)
                except BaseException:
                    state['phase'] = 'rollback-failed-needs-operator'
                    write_json(journal, state)
                    print('ROLLBACK FAILED: operator intervention required; retained DBs and releases untouched',
                          file=sys.stderr)
        raise
    print('DEPLOYED qunxue ' + revision + ' artifact=' + checksum
          + ' restarted=' + ('qunxue-api' if backend_changed else '[]')
          + ' migration_backups=' + str(len(inventory)))


def rollback(config, current_revision, target_revision):
    root = Path(config['root'])
    current, actual = active_release(config)
    require(actual == current_revision, 'Stale rollback request')
    state = json.loads((root / 'deployment-state.json').read_text())
    require(state['revision'] == current_revision and state['previous_revision'] == target_revision
            and state['phase'] == 'healthy', 'Rollback is limited to the last verified predecessor')
    target = root / 'releases' / target_revision
    current_manifest = json.loads((current / 'release.json').read_text())
    target_manifest = json.loads((target / 'release.json').read_text())
    policy = current_manifest['migration_policy']
    current_backend = current_manifest.get('backend_revision', current_revision)
    target_backend = target_manifest.get('backend_revision', target_revision)
    restart = current_backend != target_backend
    migration_changes(target, current, policy)
    state['phase'] = 'rolling-back'
    write_json(root / 'deployment-state.json', state)
    try:
        if restart:
            pm2(config, 'stop')
            check_process(config, stopped=True)
        atomic_pointer(root / 'current', target)
        if restart:
            pm2(config, 'start', target_backend)
        wait_healthy(config, target, target_revision)
        app_command(config, [config['pm2'], 'save'])
        state['phase'] = 'rolled-back'
        write_json(root / 'deployment-state.json', state)
    except BaseException:
        with recovery_signals():
            try:
                if restart:
                    pm2(config, 'stop')
                atomic_pointer(root / 'current', current)
                if restart:
                    pm2(config, 'start', current_backend)
                wait_healthy(config, current, current_revision)
                app_command(config, [config['pm2'], 'save'])
                state['phase'] = 'healthy'
                write_json(root / 'deployment-state.json', state)
            except BaseException:
                state['phase'] = 'rollback-failed-needs-operator'
                write_json(root / 'deployment-state.json', state)
        raise
    print('ROLLED BACK qunxue code to ' + target_revision + '; database schema retained')


def main():
    os.umask(0o077)
    # Do not read arbitrary CLI/config paths supplied by SSH. The forced command is fixed.
    command = os.environ.get('SSH_ORIGINAL_COMMAND') or ' '.join(sys.argv[1:])
    prefix = 'sudo -n /usr/bin/python3.12 -I /usr/local/libexec/qunxue/receiver.py '
    if command.startswith(prefix):
        command = command[len(prefix):]
    trusted(CONFIG)
    value = json.loads(CONFIG.read_text())
    if value.get('layout') == 'legacy-root-pm2':
        from legacy_receiver import main as legacy_main
        legacy_main(value, command)
        return
    if command == 'status':
        config = load_config()
        release, revision = active_release(config)
        print((release / 'release.json').read_text())
        return
    match = re.fullmatch(r'(deploy|rollback) ([0-9a-f]{40}) ([0-9a-f]{40}|[0-9a-f]{64})', command)
    require(match is not None, 'Only exact deploy/rollback protocol commands are allowed')
    operation, revision, digest = match.groups()
    require((operation == 'deploy' and HASH.fullmatch(digest))
            or (operation == 'rollback' and SHA.fullmatch(digest)), 'Invalid protocol digest')
    config = load_config()
    root = Path(config['root'])
    trusted(root)
    for directory in ('releases', 'backups', 'incoming'):
        trusted(root / directory)
    with (root / 'deploy.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        journal = root / 'deployment-state.json'
        if journal.exists():
            state = json.loads(journal.read_text())
            require(state['phase'] in ('healthy', 'rolled-back', 'prepared'),
                    'Interrupted deployment requires operator review before another release')
        def interrupted(signum, frame):
            raise InterruptedError('Release interrupted')
        for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            signal.signal(signum, interrupted)
        if operation == 'rollback':
            rollback(config, revision, digest)
            return
        with tempfile.TemporaryDirectory(prefix='release-', dir=root / 'incoming') as temporary:
            archive = Path(temporary) / 'release.tar.gz'
            receive(sys.stdin.buffer, archive, digest)
            deploy(config, archive, revision, digest)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Avoid printing application subprocess output, environment values, or DB contents.
        print('Deployment failed: ' + type(error).__name__ + ': ' + str(error), file=sys.stderr)
        sys.exit(1)
