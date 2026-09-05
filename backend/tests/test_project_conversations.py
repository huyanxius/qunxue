import json
from uuid import uuid4


def register(client):
    response = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": f"{uuid4()}@example.com", "password": "project-passphrase"},
    )
    assert response.status_code == 201


def project(client, title="社区研究"):
    response = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "entry_type": "material_input",
            "entry_mode": "existing_research",
            "project_title": title,
            "project_stage": "资料整理",
        },
    )
    assert response.status_code == 201
    return response.json()["task_id"]


def turn(client, task_id=None, conversation_id=None):
    response = client.post(
        "/api/agent/turns",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "message": "讨论社区互助",
            "workspace": "research" if task_id else "agent",
            "task_id": task_id,
            "conversation_id": conversation_id,
        },
    )
    return [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]


def test_project_supports_multiple_conversations_and_unassigned_history(client):
    register(client)
    task_id = project(client)
    saved = []
    for _ in range(2):
        events = turn(client, task_id)
        completed = [event["conversation"] for event in events if "conversation" in event]
        assert completed, events
        saved.append(completed[0])
        assert completed[0]["task_id"] == task_id
    independent = next(event["conversation"] for event in turn(client) if "conversation" in event)
    assert independent["task_id"] is None
    assert saved[0]["conversation_id"] != saved[1]["conversation_id"]
    items = client.get("/api/agent/conversations").json()["items"]
    assert {item["conversation_id"] for item in items if item["task_id"] == task_id} == {
        item["conversation_id"] for item in saved
    }
    restored = client.get(f"/api/agent/conversations/{saved[1]['conversation_id']}").json()
    assert restored["task_id"] == task_id
    journey = client.get(f"/api/agent/conversations/{saved[1]['conversation_id']}/journey").json()
    assert journey["task_id"] == task_id
    other = project(client, "另一项目")
    events = turn(client, other, saved[1]["conversation_id"])
    assert any(event.get("code") == "research_task_binding_conflict" for event in events)


def test_foreign_project_cannot_adopt_a_conversation(client):
    register(client)
    task_id = project(client)
    client.cookies.clear()
    register(client)
    events = turn(client, task_id)
    assert not any("conversation" in event for event in events)
    assert client.get("/api/agent/conversations").json()["items"] == []


def test_new_project_conversation_receives_shared_project_context(client, monkeypatch):
    from qunxue_api.adapters.research_agent.pydantic_runner import DeterministicKnowledgeRunner

    contexts = []
    original = DeterministicKnowledgeRunner.run

    def capture(self, **kwargs):
        contexts.append(kwargs["tools"].document_prompt_context)
        return original(self, **kwargs)

    monkeypatch.setattr(DeterministicKnowledgeRunner, "run", capture)
    register(client)
    task_id = project(client)
    for _ in range(2):
        events = turn(client, task_id)
        assert any("conversation" in event for event in events)
    assert len(contexts) == 2
    for context in contexts:
        assert context["project"]["task_id"] == task_id
        assert context["project"]["project_title"] == "社区研究"
        assert context["project"]["project_stage"] == "资料整理"
