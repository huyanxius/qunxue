from uuid import uuid4

from fastapi.testclient import TestClient


def _authenticate(client: TestClient) -> None:
    response = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": f"{uuid4()}@example.com", "password": "research-passphrase"},
    )
    assert response.status_code == 201


def _task(client: TestClient) -> str:
    response = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "direct_input"},
    )
    assert response.status_code == 201
    return response.json()["task_id"]


def _upload(client: TestClient, task_id: str, filename: str, content: str) -> dict[str, object]:
    response = client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "field_note"},
        files={"file": (filename, content.encode(), "text/plain")},
    )
    assert response.status_code == 201
    return response.json()


def test_task_search_finds_cross_file_text_with_exact_source_coordinates(
    client: TestClient,
) -> None:
    _authenticate(client)
    task_id = _task(client)
    matched = _upload(client, task_id, "社区访谈.txt", "迁移后的照护安排发生变化。")
    _upload(client, task_id, "观察记录.txt", "广场上的交往频率下降。")

    response = client.get(
        f"/api/research-tasks/{task_id}/materials/search",
        params={"q": "照护", "limit": 20, "offset": 0},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    hit = payload["items"][0]
    assert hit["material_id"] == matched["material_id"]
    assert hit["parse_id"] == matched["parse_id"]
    assert hit["segment_id"]
    assert hit["title"] == "社区访谈.txt"
    assert "照护" in hit["excerpt"]
    assert hit["locator"]["paragraph"] == 1

    fts_response = client.get(
        f"/api/research-tasks/{task_id}/materials/search",
        params={"q": "照护安排"},
    )
    assert fts_response.status_code == 200
    assert fts_response.json()["items"][0]["material_id"] == matched["material_id"]


def test_deleted_material_disappears_from_task_search(client: TestClient) -> None:
    _authenticate(client)
    task_id = _task(client)
    material = _upload(client, task_id, "待删除.txt", "照护网络正在变化。")
    deleted = client.delete(
        f"/api/research-tasks/{task_id}/materials/{material['material_id']}",
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert deleted.status_code == 204

    response = client.get(
        f"/api/research-tasks/{task_id}/materials/search",
        params={"q": "照护"},
    )

    assert response.status_code == 200
    assert response.json() == {"task_id": task_id, "query": "照护", "total": 0, "items": []}
