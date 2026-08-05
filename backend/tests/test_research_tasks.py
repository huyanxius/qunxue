import sqlite3
from contextlib import contextmanager
from uuid import uuid4

from fastapi.testclient import TestClient


def test_create_and_restore_research_task(client: TestClient) -> None:
    payload = {
        "phenomenon": "Some teams stop speaking up after a reorg.",
        "research_intent": "Understand silence after structural change.",
        "context": "Observed in two product squads during Q3.",
    }
    created = client.post("/api/research-tasks", json=payload)

    assert created.status_code == 201
    created_body = created.json()
    assert created_body["phenomenon"] == payload["phenomenon"]
    assert created_body["research_intent"] == payload["research_intent"]
    assert created_body["context"] == payload["context"]
    assert created_body["source"] == "user_input"

    restored = client.get(f"/api/research-tasks/{created_body['task_id']}")

    assert restored.status_code == 200
    assert restored.json() == created_body


def test_create_research_task_rejects_whitespace_only_phenomenon(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/research-tasks",
        json={
            "phenomenon": "   ",
            "research_intent": "keep optional fields untouched",
            "context": "still should fail",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_research_intake",
            "message": "phenomenon must not be empty or whitespace-only",
            "trace_id": response.json()["error"]["trace_id"],
        }
    }


def test_create_research_task_persists_to_sqlite(client: TestClient) -> None:
    payload = {
        "phenomenon": "Remote onboarding leaves informal norms invisible.",
        "research_intent": "Capture early adaptation friction.",
        "context": "A distributed team added six new members this month.",
    }
    response = client.post("/api/research-tasks", json=payload)

    assert response.status_code == 201
    created = response.json()
    database_path = client.app.state.settings.database_url.removeprefix("sqlite:///")
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT task_id, phenomenon, research_intent, context, source
            FROM research_tasks
            WHERE task_id = ?
            """,
            (created["task_id"],),
        ).fetchone()

    assert row == (
        created["task_id"],
        payload["phenomenon"],
        payload["research_intent"],
        payload["context"],
        "user_input",
    )


def test_missing_research_task_returns_stable_error(client: TestClient) -> None:
    task_id = uuid4()
    response = client.get(f"/api/research-tasks/{task_id}")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "research_task_not_found",
            "message": f"research task '{task_id}' was not found",
            "trace_id": response.json()["error"]["trace_id"],
        }
    }


def test_internal_service_failure_returns_stable_500(client: TestClient) -> None:
    class BrokenService:
        def create(self, **_kwargs: object) -> None:
            raise RuntimeError("sqlite unavailable")

        def get(self, _task_id: object) -> None:
            raise RuntimeError("sqlite unavailable")

    @contextmanager
    def broken_scope():
        yield BrokenService()

    with TestClient(client.app, raise_server_exceptions=False) as failing_client:
        failing_client.app.state.research_task_service_scope = broken_scope
        response = failing_client.post(
            "/api/research-tasks",
            json={"phenomenon": "A valid user observation."},
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_server_error",
            "message": "unexpected service failure",
            "trace_id": response.json()["error"]["trace_id"],
        }
    }
