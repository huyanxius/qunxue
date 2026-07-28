from uuid import uuid4

from fastapi.testclient import TestClient


def test_create_and_restore_research_task(client: TestClient) -> None:
    idempotency_key = str(uuid4())
    created = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": idempotency_key},
        json={"entry_type": "direct_input"},
    )

    assert created.status_code == 201
    created_body = created.json()
    assert created_body["status"] == "draft"
    assert created_body["allowed_actions"] == ["submit_phenomenon"]

    restored = client.get(f"/api/research-tasks/{created_body['task_id']}")

    assert restored.status_code == 200
    assert restored.json() == created_body


def test_create_is_idempotent(client: TestClient) -> None:
    headers = {"Idempotency-Key": str(uuid4())}
    first = client.post(
        "/api/research-tasks",
        headers=headers,
        json={"entry_type": "direct_input"},
    )
    second = client.post(
        "/api/research-tasks",
        headers=headers,
        json={"entry_type": "direct_input"},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["task_id"] == first.json()["task_id"]


def test_missing_research_task_returns_stable_error(client: TestClient) -> None:
    task_id = uuid4()
    response = client.get(f"/api/research-tasks/{task_id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "research_task_not_found"
    assert response.json()["error"]["trace_id"]
