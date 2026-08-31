from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from fastapi.testclient import TestClient


def authenticate(client: TestClient) -> None:
    response = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": f"{uuid4()}@example.com", "password": "research-passphrase"},
    )
    assert response.status_code == 201


def test_create_and_restore_research_task(client: TestClient) -> None:
    authenticate(client)
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


def test_create_existing_research_persists_one_project_identity_and_resume_target(
    client: TestClient,
) -> None:
    authenticate(client)
    created = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": "existing-study-entry"},
        json={
            "entry_type": "material_input",
            "entry_mode": "existing_research",
            "project_title": "社区照护田野研究",
            "project_stage": "材料整理",
            "method_orientation": "质性访谈与参与式观察",
        },
    )

    assert created.status_code == 201
    task = created.json()
    assert task["entry_mode"] == "existing_research"
    assert task["lifecycle_status"] == "in_progress"
    assert task["project_title"] == "社区照护田野研究"
    assert task["project_stage"] == "材料整理"
    assert task["method_orientation"] == "质性访谈与参与式观察"
    assert task["last_central_tool"] == "materials"

    navigation = client.get(f"/api/research-tasks/{task['task_id']}/navigation")

    assert navigation.status_code == 200
    assert navigation.json()["task_id"] == task["task_id"]
    assert navigation.json()["status"] == "in_progress"
    assert navigation.json()["resume_path"] == (
        f"/research/materials?task_id={task['task_id']}"
    )


def test_project_metadata_update_archives_without_changing_task_identity(
    client: TestClient,
) -> None:
    authenticate(client)
    created = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": "archive-project"},
        json={
            "entry_mode": "existing_research",
            "project_title": "已完成的田野研究",
        },
    ).json()

    archived = client.patch(
        f"/api/research-tasks/{created['task_id']}",
        headers={"Idempotency-Key": "archive-project-once"},
        json={
            "expected_version": created["version"],
            "lifecycle_status": "archived",
            "last_central_tool": "materials",
        },
    )

    assert archived.status_code == 200
    assert archived.json()["task_id"] == created["task_id"]
    assert archived.json()["lifecycle_status"] == "archived"
    assert archived.json()["version"] == created["version"] + 1
    navigation = client.get(f"/api/research-tasks/{created['task_id']}/navigation")
    assert navigation.status_code == 200
    assert navigation.json()["status"] == "archived"
    assert navigation.json()["resume_path"] == (
        f"/research/materials?task_id={created['task_id']}"
    )


def test_create_is_idempotent(client: TestClient) -> None:
    authenticate(client)
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


def test_concurrent_create_is_idempotent(client: TestClient) -> None:
    authenticate(client)
    worker_count = 4
    barrier = Barrier(worker_count)
    headers = {"Idempotency-Key": str(uuid4())}

    def create_task() -> tuple[int, str]:
        barrier.wait()
        response = client.post(
            "/api/research-tasks",
            headers=headers,
            json={"entry_type": "direct_input"},
        )
        return response.status_code, response.json()["task_id"]

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = list(executor.map(lambda _index: create_task(), range(worker_count)))

    assert {status_code for status_code, _task_id in results} == {201}
    assert len({task_id for _status_code, task_id in results}) == 1


def test_missing_research_task_returns_stable_error(client: TestClient) -> None:
    authenticate(client)
    task_id = uuid4()
    response = client.get(f"/api/research-tasks/{task_id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "research_task_not_found"
    assert response.json()["error"]["trace_id"]
