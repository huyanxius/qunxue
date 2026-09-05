from uuid import uuid4

from test_agent_memory import project, register, save


def overview(client, task_id=None):
    settings = client.get(
        "/api/memories/settings", params={"task_id": task_id} if task_id else {}
    ).json()
    return client.post(
        "/api/memories/overview",
        json={
            "task_id": task_id,
            "expected_version": settings["version"],
        },
    )


def test_overview_empty_does_not_need_model(plain_client):
    register(plain_client)
    response = overview(plain_client)
    assert response.status_code == 200, response.text
    assert response.json()["summary"] == ""
    assert response.json()["memory_count"] == 0


def test_overview_uses_owned_scope_and_does_not_write_memory(plain_client):
    client = plain_client
    register(client)
    task_id = project(client)
    save(client, content="中文回答。")
    save(client, content="先开放编码。", task_id=task_id)
    seen = []

    def summarize(items):
        seen.append(items)
        return "这个项目采用开放编码。"

    client.app.state.memory_overview.generate = summarize
    before = client.get("/api/memories", params={"task_id": task_id}).json()
    result = overview(client, task_id)
    assert result.status_code == 200, result.text
    assert result.json()["summary"] == "这个项目采用开放编码。"
    assert [item.content for item in seen[0]] == ["先开放编码。"]
    assert overview(client, task_id).json() == result.json()
    assert len(seen) == 1
    assert client.get("/api/memories", params={"task_id": task_id}).json() == before
    client.cookies.clear()
    register(client)
    assert (
        client.post(
            "/api/memories/overview", json={"task_id": task_id, "expected_version": 1}
        ).status_code
        == 404
    )
    assert len(seen) == 1


def test_overview_rejects_changed_snapshot(plain_client):
    client = plain_client
    register(client)
    record = save(client, content="中文回答。").json()

    def summarize(items):
        client.patch(
            f"/api/memories/{record['memory_id']}",
            headers={"Idempotency-Key": str(uuid4())},
            json={"content": "保留原文。", "expected_version": 1},
        )
        return "已过期的概览"

    client.app.state.memory_overview.generate = summarize
    assert overview(client).status_code == 409


def test_overview_model_failure_preserves_records(plain_client):
    client = plain_client
    register(client)
    save(client)
    before = client.get("/api/memories").json()
    response = overview(client)
    assert response.status_code == 503
    assert client.get("/api/memories").json() == before
