from uuid import uuid4


def register(client):
    response = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": f"{uuid4()}@example.com", "password": "memory-passphrase"},
    )
    assert response.status_code == 201
    return response.json()["user"]["user_id"]


def project(client):
    response = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "material_input", "project_title": "社区研究"},
    )
    assert response.status_code == 201
    return response.json()["task_id"]


def save(client, key="answer_style", content="优先用中文简洁回答", task_id=None, **extra):
    return client.post(
        "/api/memories",
        headers={"Idempotency-Key": str(uuid4())},
        json={"key": key, "content": content, "task_id": task_id, **extra},
    )


def test_memory_crud_versions_and_tombstone(plain_client):
    client = plain_client
    register(client)
    response = save(client)
    assert response.status_code == 201, response.text
    entry = response.json()
    assert entry["origin"] == "manual"
    assert client.get("/api/memories").json()["items"][0]["content"] == "优先用中文简洁回答"
    path = f"/api/memories/{entry['memory_id']}"
    patch = {"content": "先给结论，再解释", "expected_version": entry["version"]}
    response = client.patch(path, headers={"Idempotency-Key": str(uuid4())}, json=patch)
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["version"] == entry["version"] + 1
    assert (
        client.patch(path, headers={"Idempotency-Key": str(uuid4())}, json=patch).status_code == 409
    )
    revisions = client.get(f"{path}/revisions").json()["items"]
    assert [item["content"] for item in revisions] == ["先给结论，再解释", "优先用中文简洁回答"]
    response = client.delete(
        path,
        params={"expected_version": updated["version"]},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 204, response.text
    assert client.get("/api/memories").json()["items"] == []
    assert client.get(path).status_code == 404


def test_memory_scope_isolation_and_no_unauthenticated_access(plain_client):
    client = plain_client
    assert client.get("/api/memories").status_code == 401
    register(client)
    task_id = project(client)
    other_task = project(client)
    response = save(client, "field_scope", "仅研究成年受访者", task_id)
    assert response.status_code == 201, response.text
    memory_id = response.json()["memory_id"]
    assert client.get("/api/memories").json()["items"] == []
    assert len(client.get("/api/memories", params={"task_id": task_id}).json()["items"]) == 1
    assert client.get("/api/memories", params={"task_id": other_task}).json()["items"] == []
    client.cookies.clear()
    register(client)
    assert client.get(f"/api/memories/{memory_id}").status_code == 404
    assert client.get(f"/api/memories/{memory_id}/revisions").status_code == 404
    assert client.get("/api/memories", params={"task_id": task_id}).status_code == 404
    assert save(client, task_id=task_id).status_code == 404


def test_memory_manual_budget_and_idempotency(plain_client):
    client = plain_client
    register(client)
    headers = {"Idempotency-Key": str(uuid4())}
    payload = {"key": "style", "content": "中文简洁回答"}
    first = client.post("/api/memories", headers=headers, json=payload)
    assert first.status_code == 201, first.text
    repeated = client.post("/api/memories", headers=headers, json=payload)
    assert repeated.status_code == 201
    assert repeated.json()["memory_id"] == first.json()["memory_id"]
    changed = client.post("/api/memories", headers=headers, json={**payload, "content": "长篇回答"})
    assert changed.status_code == 409
    assert save(client, "too_long", "长" * 1500).status_code == 422
    assert len(client.get("/api/memories").json()["items"]) == 1


def seed_learning_source(client, user_id, task_id=None, content="以后请用中文简洁回答"):
    from datetime import UTC, datetime, timedelta

    from qunxue_api.adapters.sqlite.agent_conversation_model import (
        AgentConversationRow,
        AgentMessageRow,
    )

    now = datetime.now(UTC) - timedelta(hours=1)
    conversation_id, message_id = uuid4(), uuid4()
    with client.app.state.database.session() as session:
        session.add(
            AgentConversationRow(
                conversation_id=str(conversation_id),
                user_id=user_id,
                title="记忆测试",
                current_research_task_id=task_id,
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        session.add(
            AgentMessageRow(
                message_id=str(message_id),
                conversation_id=str(conversation_id),
                turn_id=str(uuid4()),
                role="user",
                content=content,
                sequence=0,
                created_at=now,
            )
        )
    return conversation_id, message_id


def test_background_learning_is_incremental_and_protects_manual_edits(plain_client):
    client = plain_client
    user_id = register(client)
    conversation_id, message_id = seed_learning_source(client, user_id)
    assert getattr(client.app.state, "memory_worker", None) is not None
    from qunxue_api.modules.agent_memory import MemoryCandidate

    worker = client.app.state.memory_worker
    calls = []

    def extract(batch):
        calls.append(batch.conversation_id)
        return (
            (MemoryCandidate("user", "style", "中文简洁回答", message_id, "以后请用中文简洁回答"),),
            80,
            20,
        )

    assert worker.run_once(extractor=extract)
    entries = client.get("/api/memories").json()["items"]
    assert entries[0]["origin"] == "learned"
    assert entries[0]["source_message_id"] == str(message_id)
    assert not worker.run_once(extractor=extract)
    assert calls == [conversation_id]

    # The model runs outside the transaction. A human edit in that interval wins.
    next_conversation, next_message = seed_learning_source(client, user_id, content="回答详细一些")

    def concurrent_edit(batch):
        response = client.patch(
            f"/api/memories/{entries[0]['memory_id']}",
            headers={"Idempotency-Key": str(uuid4())},
            json={"content": "由我决定回答详略", "expected_version": 1},
        )
        assert response.status_code == 200
        return (
            (MemoryCandidate("user", "style", "总是长篇回答", next_message, "回答详细一些"),),
            80,
            20,
        )

    assert worker.run_once(extractor=concurrent_edit)
    assert client.get("/api/memories").json()["items"][0]["content"] == "由我决定回答详略"


def test_forgetting_fences_unprocessed_old_sources_and_projects(plain_client):
    client = plain_client
    user_id = register(client)
    task_id = project(client)
    _, source_id = seed_learning_source(client, user_id, task_id, "仅研究成年受访者")
    entry = save(client, "field_scope", "仅研究成年受访者", task_id).json()
    assert (
        client.delete(
            f"/api/memories/{entry['memory_id']}",
            params={"expected_version": 1},
            headers={"Idempotency-Key": str(uuid4())},
        ).status_code
        == 204
    )
    assert getattr(client.app.state, "memory_worker", None) is not None
    from qunxue_api.modules.agent_memory import MemoryCandidate

    def stale_source(batch):
        # A different key must not bypass the deletion fence.
        return (
            (
                MemoryCandidate(
                    "project", "another_key", "仅研究成年受访者", source_id, "仅研究成年受访者"
                ),
            ),
            1,
            1,
        )

    client.app.state.memory_worker.run_once(extractor=stale_source)
    assert client.get("/api/memories", params={"task_id": task_id}).json()["items"] == []


def test_memory_context_is_bounded_and_settings_disable_reads(plain_client):
    from uuid import UUID

    from qunxue_api.modules.agent_memory import CONTEXT_BUDGET, context_cost

    client = plain_client
    user_id = UUID(register(client))
    assert save(client).status_code == 201
    with client.app.state.memory_service_scope() as memory:
        context = memory.context(user_id, None)
        assert "优先用中文简洁回答" in context
        assert context_cost(context) <= CONTEXT_BUDGET
    settings = client.get("/api/memories/settings").json()
    response = client.patch(
        "/api/memories/settings",
        headers={"Idempotency-Key": str(uuid4())},
        json={"expected_version": settings["version"], "use_memory": False, "learn_memory": False},
    )
    assert response.status_code == 200
    with client.app.state.memory_service_scope() as memory:
        assert memory.context(user_id, None) == ""


def test_background_rejects_fabricated_sources_and_keeps_project_scope(plain_client):
    client = plain_client
    user_id = register(client)
    task_id = project(client)
    _, source_id = seed_learning_source(client, user_id, task_id, "本项目采用半结构访谈")
    from qunxue_api.modules.agent_memory import MemoryCandidate

    def extract(batch):
        return (
            (
                MemoryCandidate(
                    "project", "method", "采用半结构访谈", source_id, "本项目采用半结构访谈"
                ),
                MemoryCandidate("user", "invented", "用户是教授", uuid4(), "用户是教授"),
                MemoryCandidate("user", "unquoted", "偏好定量方法", source_id, "偏好定量方法"),
            ),
            10,
            10,
        )

    assert client.app.state.memory_worker.run_once(extractor=extract)
    assert client.get("/api/memories").json()["items"] == []
    entries = client.get("/api/memories", params={"task_id": task_id}).json()["items"]
    assert [(e["key"], e["content"]) for e in entries] == [("method", "采用半结构访谈")]


def test_memory_rejects_credentials(plain_client):
    client = plain_client
    register(client)
    assert save(client, "credential", "api_key=sk-example000000000000000000").status_code == 422


def test_deleting_project_removes_its_memories_and_preserves_user_memory(plain_client):
    client = plain_client
    register(client)
    task_id = project(client)
    personal = save(client).json()
    scoped = save(client, "method", "使用访谈", task_id).json()
    response = client.delete(
        f"/api/research-tasks/{task_id}", headers={"Idempotency-Key": str(uuid4())}
    )
    assert response.status_code == 200
    assert client.get(f"/api/memories/{scoped['memory_id']}").status_code == 404
    assert client.get(f"/api/memories/{personal['memory_id']}").status_code == 200


def test_agent_memory_binding_requires_explicit_request_and_limits_searches(plain_client):
    from uuid import UUID

    client = plain_client
    user_id = UUID(register(client))
    assert save(client).status_code == 201
    from qunxue_api.adapters.research_agent.memory_tools import AgentMemoryTools

    tools = AgentMemoryTools(
        client.app.state.memory_service_scope,
        user_id=user_id,
        task_id=None,
        conversation_id=uuid4(),
        prompt="解释社会资本",
        run_id=uuid4(),
    )
    assert "优先用中文简洁回答" in tools.context
    assert (
        tools.change(action="remember", scope="user", key="other", content="长篇回答")["error"]
        == "explicit_request_required"
    )
    assert tools.search("中文")["items"]
    assert tools.search("中文")["error"] == "memory_read_budget_exhausted"
    explicit = AgentMemoryTools(
        client.app.state.memory_service_scope,
        user_id=user_id,
        task_id=None,
        conversation_id=uuid4(),
        prompt="记住：先给结论",
        run_id=uuid4(),
    )
    result = explicit.change(action="remember", scope="user", key="conclusion", content="先给结论")
    assert result["saved"] is True
    entries = client.get("/api/memories").json()["items"]
    assert any(e["content"] == "先给结论" and e["origin"] == "explicit" for e in entries)
