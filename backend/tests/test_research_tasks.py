import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier
from uuid import uuid4

from fastapi.testclient import TestClient


def test_create_and_restore_research_task(client: TestClient) -> None:
    idempotency_key = str(uuid4())
    payload = {
        'phenomenon': 'Some teams stop speaking up after a reorg.',
        'research_intent': 'Understand silence after structural change.',
        'context': 'Observed in two product squads during Q3.',
    }
    created = client.post(
        '/api/research-tasks',
        headers={'Idempotency-Key': idempotency_key},
        json=payload,
    )

    assert created.status_code == 201
    created_body = created.json()
    assert created_body['entry_type'] == 'direct_input'
    assert created_body['status'] == 'draft'
    assert created_body['version'] == 1
    assert created_body['allowed_actions'] == ['submit_phenomenon']
    assert created_body['phenomenon'] == payload['phenomenon']
    assert created_body['research_intent'] == payload['research_intent']
    assert created_body['context'] == payload['context']
    assert created_body['source'] == 'user_input'

    restored = client.get(f"/api/research-tasks/{created_body['task_id']}")

    assert restored.status_code == 200
    assert restored.json() == created_body


def test_create_research_task_rejects_whitespace_only_phenomenon(
    client: TestClient,
) -> None:
    response = client.post(
        '/api/research-tasks',
        headers={'Idempotency-Key': 'whitespace-key'},
        json={
            'phenomenon': '   ',
            'research_intent': 'keep optional fields untouched',
            'context': 'still should fail',
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        'error': {
            'code': 'invalid_research_intake',
            'message': '研究现象不能为空或纯空白。',
            'trace_id': response.json()['error']['trace_id'],
        }
    }


def test_create_requires_idempotency_key(client: TestClient) -> None:
    response = client.post(
        '/api/research-tasks',
        json={'phenomenon': 'A valid observation without a request key.'},
    )

    assert response.status_code == 422


def test_create_is_idempotent(client: TestClient) -> None:
    headers = {'Idempotency-Key': str(uuid4())}
    payload = {
        'phenomenon': 'Hybrid meetings mute junior disagreement.',
        'research_intent': 'Follow disagreement cues.',
        'context': 'Observed in weekly planning.',
    }

    first = client.post('/api/research-tasks', headers=headers, json=payload)
    second = client.post('/api/research-tasks', headers=headers, json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()['task_id'] == first.json()['task_id']
    assert second.json()['version'] == 1


def test_concurrent_create_is_idempotent(client: TestClient) -> None:
    worker_count = 4
    barrier = Barrier(worker_count)
    headers = {'Idempotency-Key': str(uuid4())}
    payload = {
        'phenomenon': 'Shared dashboards flatten local uncertainty.',
        'research_intent': 'Observe reporting behavior.',
        'context': 'Observed across four project teams.',
    }

    def create_task() -> tuple[int, str]:
        barrier.wait()
        response = client.post('/api/research-tasks', headers=headers, json=payload)
        return response.status_code, response.json()['task_id']

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = list(executor.map(lambda _index: create_task(), range(worker_count)))

    assert {status_code for status_code, _task_id in results} == {201}
    assert len({task_id for _status_code, task_id in results}) == 1


def test_create_research_task_persists_to_sqlite(client: TestClient) -> None:
    payload = {
        'phenomenon': 'Remote onboarding leaves informal norms invisible.',
        'research_intent': 'Capture early adaptation friction.',
        'context': 'A distributed team added six new members this month.',
    }
    response = client.post(
        '/api/research-tasks',
        headers={'Idempotency-Key': str(uuid4())},
        json=payload,
    )

    assert response.status_code == 201
    created = response.json()
    database_path = client.app.state.settings.database_url.removeprefix('sqlite:///')
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            '''
            SELECT task_id, phenomenon, research_intent, context, source
            FROM research_tasks
            WHERE task_id = ?
            ''',
            (created['task_id'],),
        ).fetchone()

    assert row == (
        created['task_id'],
        payload['phenomenon'],
        payload['research_intent'],
        payload['context'],
        'user_input',
    )


def test_missing_research_task_returns_stable_error(client: TestClient) -> None:
    task_id = uuid4()
    response = client.get(f'/api/research-tasks/{task_id}')

    assert response.status_code == 404
    assert response.json() == {
        'error': {
            'code': 'research_task_not_found',
            'message': f"研究任务 '{task_id}' 不存在。",
            'trace_id': response.json()['error']['trace_id'],
        }
    }


def test_internal_service_failure_returns_stable_500(client: TestClient) -> None:
    class BrokenService:
        def create(self, **_kwargs: object) -> None:
            raise RuntimeError('sqlite unavailable')

        def get(self, _task_id: object) -> None:
            raise RuntimeError('sqlite unavailable')

    @contextmanager
    def broken_scope():
        yield BrokenService()

    with TestClient(client.app, raise_server_exceptions=False) as failing_client:
        failing_client.app.state.research_task_service_scope = broken_scope
        response = failing_client.post(
            '/api/research-tasks',
            headers={'Idempotency-Key': str(uuid4())},
            json={'phenomenon': 'A valid user observation.'},
        )

    assert response.status_code == 500
    assert response.json() == {
        'error': {
            'code': 'internal_server_error',
            'message': '系统暂时无法处理请求。',
            'trace_id': response.json()['error']['trace_id'],
        }
    }