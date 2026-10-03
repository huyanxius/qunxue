import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('wheelhouse', Path(__file__).parents[1] / 'build_wheelhouse.py')
wheelhouse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wheelhouse)


class WheelhouseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'source.lock'
        self.source.write_text('example==1.2.3 --hash=sha256:' + 'a' * 64 + '\n')
        self.wheels = self.root / 'wheelhouse'
        self.wheels.mkdir()
        self.output = self.root / 'offline.lock'
        self.provenance = self.root / 'provenance.json'

    def wheel(self, version='1.2.3'):
        target = self.wheels / ('example-' + version + '-py3-none-any.whl')
        with zipfile.ZipFile(target, 'w') as output:
            output.writestr('example-' + version + '.dist-info/METADATA',
                            'Name: example\nVersion: ' + version + '\n')
        return target

    def test_built_wheel_hash_replaces_source_hash_without_changing_version(self):
        path = self.wheel()
        wheelhouse.wheel_lock(self.source, self.wheels, self.output, self.provenance)
        wheel_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertIn('example==1.2.3 --hash=sha256:' + wheel_hash, self.output.read_text())
        self.assertNotIn('a' * 64, self.output.read_text())
        self.assertEqual(json.loads(self.provenance.read_text())['source_requirements_sha256'],
                         hashlib.sha256(self.source.read_bytes()).hexdigest())

    def test_wrong_version_or_incomplete_wheelhouse_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            wheelhouse.wheel_lock(self.source, self.wheels, self.output, self.provenance)
        self.wheel('9.9.9')
        with self.assertRaisesRegex(ValueError, 'wrong-version'):
            wheelhouse.wheel_lock(self.source, self.wheels, self.output, self.provenance)

    def test_sdist_cannot_enter_server_offline_payload(self):
        (self.wheels / 'example-1.2.3.tar.gz').write_bytes(b'source')
        with self.assertRaisesRegex(ValueError, 'non-wheel'):
            wheelhouse.wheel_lock(self.source, self.wheels, self.output, self.provenance)

    def test_duplicate_or_incompatible_wheel_is_rejected(self):
        self.wheel()
        other = self.wheels / 'example-1.2.3-py2-none-any.whl'
        other.write_bytes(b'not a compatible wheel')
        with self.assertRaisesRegex(ValueError, 'incompatible wheel'):
            wheelhouse.wheel_lock(self.source, self.wheels, self.output, self.provenance)

    def test_metadata_identity_must_match_filename(self):
        path = self.wheel()
        with zipfile.ZipFile(path, 'w') as output:
            output.writestr('example-1.2.3.dist-info/METADATA',
                            'Name: different-package\nVersion: 1.2.3\n')
        with self.assertRaisesRegex(ValueError, 'identities differ'):
            wheelhouse.wheel_lock(self.source, self.wheels, self.output, self.provenance)

    def test_malformed_hash_and_truncated_source_are_rejected(self):
        for requirement in ('example==1.2.3 --hash=sha256:bad',
                            'example==1.2.3 ' + chr(92)):
            self.source.write_text(requirement + '\n')
            with self.assertRaises(ValueError):
                wheelhouse.selected_requirements(self.source)

    def test_unpinned_or_unhashed_source_is_rejected(self):
        for requirement in ('example>=1.2.3 --hash=sha256:' + 'a' * 64, 'example==1.2.3'):
            self.source.write_text(requirement + '\n')
            with self.assertRaises(ValueError):
                wheelhouse.selected_requirements(self.source)

    def test_platform_markers_select_only_the_current_runtime(self):
        self.source.write_text('example==1.2.3 --hash=sha256:' + 'a' * 64 + '\n'
                               'windows-only==7 ; sys_platform == "win32" --hash=sha256:' + 'b' * 64 + '\n')
        self.assertEqual(wheelhouse.selected_requirements(self.source), {'example': '1.2.3'})


if __name__ == '__main__':
    unittest.main()
