"""No network, production or model calls: exercise exact degraded-readiness rules."""
from contextlib import redirect_stderr
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import receiver
import legacy_receiver as legacy
import test_legacy_delivery as fixtures

OLD, NEW = 'b' * 40, 'a' * 40


def contract(revision=OLD, model_status='unavailable'):
    return {'status': 'ok', 'service': 'qunxue', 'runtime_mode': 'base',
            'provider': 'synthetic', 'model_version': 'fixture', 'persistence': 'sqlite',
            'contract_version': 'fixture', 'capability': 'base', 'knowledge_release_id': 'fixture-release',
            'model_status': model_status, 'model_checked_at': None, 'release_revision': revision}


class Response(io.BytesIO):
    def __init__(self, url, body, status=200):
        super().__init__(body)
        self.url, self.status = url, status

    def geturl(self):
        return self.url


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.fixture = fixtures.LegacyDelivery()
        self.config, self.baseline, self.source, self.front, self.state = self.fixture.fixture(self.root)
        self.config.update(local_origin='http://127.0.0.1:8096', public_origin='https://qunxue.example',
                           expected_runtime_mode='base')
        for name in ('app.js', 'app.css'):
            (self.front / name).write_bytes(name.encode())
            self.baseline['files']['frontend/' + name] = receiver.sha256(self.front / name)
        receiver.write_json(Path(self.config['root']) / 'active.json', self.baseline)

    def transport(self, *, bad_health=None, corrupt_candidate=False, model_status='unavailable'):
        def open_url(request, timeout):
            url = request.full_url
            current = Path(self.config['source_pointer']).resolve()
            revision = OLD if current == self.source else NEW
            if urlsplit(url).path == '/api/health':
                data = bad_health if bad_health is not None else contract(revision, model_status)
                raw = json.dumps(data).encode()
                if model_status == 'unavailable' or bad_health is not None:
                    raise HTTPError(url, 503, 'synthetic model unavailable', {}, io.BytesIO(raw))
                return Response(url, raw)
            name = urlsplit(url).path.lstrip('/') or 'index.html'
            body = (Path(self.config['frontend_pointer']).resolve() / name).read_bytes()
            if corrupt_candidate and current != self.source:
                body = b'wrong asset'
            return Response(url, body)
        return open_url

    def check(self, **kwargs):
        with patch.object(receiver, 'urlopen', side_effect=self.transport(**kwargs)), \
             legacy.view(self.config, self.baseline) as release:
            return receiver.health(self.config, release, OLD)

    def assert_old_untouched(self):
        self.assertEqual(Path(self.config['source_pointer']).resolve(), self.source)
        self.assertEqual(Path(self.config['frontend_pointer']).resolve(), self.front)
        self.assertEqual((self.state / 'db.sqlite3').read_bytes(), b'database-untouched')
        self.assertEqual(json.loads((Path(self.config['root']) / 'active.json').read_text()), self.baseline)

    def test_normal_and_exact_model_only_degradation(self):
        self.assertFalse(self.check(model_status='healthy'))
        output = io.StringIO()
        with redirect_stderr(output):
            self.assertTrue(self.check())
        self.assertIn('READINESS DEGRADED', output.getvalue())
        self.assertIn('external model remains unavailable', output.getvalue())
        self.assert_old_untouched()

    def test_missing_active_baseline_still_requires_audited_initialization(self):
        active = Path(self.config['root']) / 'active.json'
        active.unlink()
        with patch.object(receiver, 'urlopen', side_effect=self.transport()):
            with self.assertRaises(HTTPError):
                legacy.baseline(self.config)
        self.assertFalse(active.exists())
        self.assertEqual(Path(self.config['source_pointer']).resolve(), self.source)
        self.assertEqual(Path(self.config['frontend_pointer']).resolve(), self.front)
        self.assertEqual((self.state / 'db.sqlite3').read_bytes(), b'database-untouched')

    def test_other_503s_wrong_identity_and_malformed_contract_fail(self):
        invalid = [
            {'error': {'code': 'retrieval_unavailable'}},
            {**contract(), 'error': {'code': 'database_unavailable'}},
            {key: value for key, value in contract().items() if key != 'knowledge_release_id'},
            {**contract(), 'release_revision': NEW},
            {**contract(), 'runtime_mode': 'sft'},
            {**contract(), 'model_status': 'unknown'},
            {**contract(), 'status': 'failed'},
            {**contract(), 'persistence': 'unavailable'},
            {**contract(), 'capability': 'unavailable'},
            {**contract(), 'knowledge_release_id': None},
            {**contract(), 'model_checked_at': 'invalid timestamp'},
            {**contract(), 'extra': 'not-the-frozen-contract'},
        ]
        archive = self.fixture.archive(self.root, self.baseline, {'backend/src/app.py': b'new'})
        for data in invalid:
            with self.subTest(data=data), patch.object(receiver, 'urlopen', side_effect=self.transport(bad_health=data)), \
                 patch.object(legacy, 'stop_process') as stop, patch.object(legacy, 'prepare_backend') as prepare:
                with self.assertRaises(RuntimeError):
                    legacy.deploy(self.config, archive, NEW, receiver.sha256(archive))
                stop.assert_not_called()
                prepare.assert_not_called()
                self.assert_old_untouched()

    def test_health_transport_rejects_bad_status_json_size_redirect_and_network(self):
        url = 'https://qunxue.example/api/health?release=' + OLD
        for body in (b'not json', b'[]', b'{"status":"failed","status":"ok"}',
                     b'x' * (receiver.MAX_HEALTH_RESPONSE + 1)):
            with self.subTest(body=body[:10]), patch.object(receiver, 'urlopen', return_value=Response(url, body, 503)):
                with self.assertRaises((ValueError, RuntimeError)):
                    receiver.fetch_health(url)
        with patch.object(receiver, 'urlopen', return_value=Response(url + 'redirected', json.dumps(contract()).encode(), 503)):
            with self.assertRaisesRegex(RuntimeError, 'redirect'):
                receiver.fetch_health(url)
        for error in (HTTPError(url, 500, 'synthetic failure', {}, io.BytesIO(b'{}')),
                      URLError('synthetic unreachable')):
            with self.subTest(error=type(error).__name__), patch.object(receiver, 'urlopen', side_effect=error):
                with self.assertRaises((HTTPError, URLError)):
                    receiver.fetch_health(url)

    def test_assets_still_require_200_and_exact_digest_while_model_is_degraded(self):
        for asset in ('index.html', 'app.js', 'app.css'):
            original = (self.front / asset).read_bytes()
            (self.front / asset).write_bytes(b'corrupted')
            with self.subTest(asset=asset), self.assertRaisesRegex(RuntimeError, 'asset mismatch'):
                self.check()
            (self.front / asset).write_bytes(original)
        url = 'https://qunxue.example/app.js'
        with patch.object(receiver, 'urlopen', side_effect=HTTPError(url, 503, 'bad asset', {}, io.BytesIO(b'app.js'))):
            with self.assertRaises(HTTPError):
                receiver.fetch(url)

    def test_real_legacy_deploy_keeps_degraded_model_visible_without_false_rollback(self):
        archive = self.fixture.archive(self.root, self.baseline, {'backend/src/app.py': b'new'})
        output = io.StringIO()
        with patch.object(receiver, 'urlopen', side_effect=self.transport()), \
             patch.object(receiver, 'check_process'), patch.object(receiver, 'app_command'), \
             patch.object(legacy, 'process_definition', return_value={'name': 'qunxue-api', 'env': {}}), \
             patch.object(legacy, 'prepare_backend'), patch.object(legacy, 'start_process') as start, \
             patch.object(legacy, 'stop_process') as stop, redirect_stderr(output):
            legacy.deploy(self.config, archive, NEW, receiver.sha256(archive))
        self.assertEqual(stop.call_count, 1)
        self.assertEqual(start.call_count, 1)
        self.assertEqual(json.loads((Path(self.config['root']) / 'active.json').read_text())['revision'], NEW)
        self.assertEqual(json.loads((Path(self.config['root']) / 'deployment-state.json').read_text())['phase'], 'healthy')
        self.assertIn('READINESS DEGRADED', output.getvalue())
        self.assertEqual((self.state / 'db.sqlite3').read_bytes(), b'database-untouched')

    def test_real_legacy_failure_rolls_back_even_when_old_model_is_unavailable(self):
        archive = self.fixture.archive(self.root, self.baseline, {'backend/src/app.py': b'new'})
        with patch.object(receiver, 'urlopen', side_effect=self.transport(corrupt_candidate=True)), \
             patch.object(receiver, 'check_process'), patch.object(receiver, 'app_command'), \
             patch.object(legacy, 'process_definition', return_value={'name': 'qunxue-api', 'env': {}}), \
             patch.object(legacy, 'prepare_backend'), patch.object(legacy, 'start_process') as start, \
             patch.object(legacy, 'stop_process') as stop, redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'asset mismatch'):
                legacy.deploy(self.config, archive, NEW, receiver.sha256(archive))
        self.assertEqual(stop.call_count, 2)
        self.assertEqual(start.call_count, 2)
        self.assert_old_untouched()
        self.assertEqual(json.loads((Path(self.config['root']) / 'deployment-state.json').read_text())['phase'], 'rolled-back')


if __name__ == '__main__':
    unittest.main()
