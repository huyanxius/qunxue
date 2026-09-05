from test_agent_memory import project, register, save


def test_memory_list_advertises_capacity_for_both_scopes(plain_client):
    client = plain_client
    register(client)
    task_id = project(client)
    for params in ({}, {"task_id": task_id}):
        response = client.get("/api/memories", params=params)
        assert response.status_code == 200
        assert response.json()["limits"] == {
            "max_entries": 100,
            "max_content_bytes": 2000,
        }


def test_memory_capacity_counts_utf8_content_without_key_overhead(plain_client):
    client = plain_client
    register(client)
    content = "研" * 666 + "ab"
    response = save(client, key="note.00000000-0000-4000-8000-000000000001", content=content)
    assert response.status_code == 201, response.text
    assert response.json()["content"] == content
    too_long = save(client, key="too_long", content=content + "c")
    assert too_long.status_code == 422
    assert "过长" in too_long.json()["error"]["message"]


def test_memory_rejection_preserves_actionable_reason(plain_client):
    client = plain_client
    register(client)
    response = save(client, content="密码：example-secret-only")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["message"] == "记忆不能保存密码或访问凭据"
    assert "example-secret-only" not in response.text


def test_overview_remains_valid_when_only_settings_change_during_generation(plain_client):
    from uuid import uuid4

    from test_memory_overview import overview

    client = plain_client
    register(client)
    save(client, content="保留原文。")

    def generate(items):
        settings = client.get("/api/memories/settings").json()
        response = client.patch(
            "/api/memories/settings",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "expected_version": settings["version"],
                "use_memory": False,
                "learn_memory": False,
            },
        )
        assert response.status_code == 200
        return "你希望保留原文。"

    client.app.state.memory_overview.generate = generate
    response = overview(client)
    assert response.status_code == 200, response.text
    assert response.json()["summary"] == "你希望保留原文。"
    assert (
        response.json()["scope_version"] == client.get("/api/memories/settings").json()["version"]
    )
