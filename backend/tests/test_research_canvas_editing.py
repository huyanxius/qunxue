from uuid import UUID, uuid4

from qunxue_api.adapters.sqlite.agent_conversation_repository import SqliteConversationRepository
from qunxue_api.modules.agent_conversation import ConversationService


def seed(client):
    registered = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": f"{uuid4()}@example.com", "password": "canvas-passphrase"},
    )
    owner = UUID(registered.json()["user"]["user_id"])
    with client.app.state.database.session() as session:
        service = ConversationService(SqliteConversationRepository(session))
        conversation = service.create_conversation(user_id=owner, title="青年留城")
        run = service.start_run(
            user_id=owner,
            conversation_id=conversation.conversation_id,
            idempotency_key="seed-canvas",
            knowledge_release_id="preview",
        )
        turn = service.append_turn(
            user_id=owner,
            conversation_id=conversation.conversation_id,
            idempotency_key="seed-canvas",
            user_content="研究关系支持",
            assistant_content="形成待验证主张",
            citations=(),
        )
        node = {
            "id": "claim-1",
            "kind": "claim",
            "title": "关系支持影响留城",
            "summary": "需要对照离开者的经历",
            "status": "grounded",
            "citation_ids": [],
        }
        patch = {
            "schema_version": 1,
            "nodes": [node, {**node, "id": "question-1", "kind": "question"}],
            "relations": [
                {
                    "id": "q-claim",
                    "source": "question-1",
                    "target": "claim-1",
                    "relation": "derives",
                }
            ],
            "remove_node_ids": [],
            "remove_relation_ids": [],
        }
        service.finish_run(
            run_id=run.run_id,
            status="completed",
            turn_id=turn.turn_id,
            tool_summary=(
                {
                    "tool": "update_research_map",
                    "phase": "finished",
                    "call_id": "map-seed",
                    "output": patch,
                },
            ),
        )
        service.commit()
    return str(conversation.conversation_id), node


def edit(client, conversation_id, node, **extra):
    return client.patch(
        f"/api/agent/conversations/{conversation_id}/research-map/nodes/{node['id']}",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "title": "关系支持是否影响留城？",
            "summary": "比较留城者与离开者",
            "expected_title": node["title"],
            "expected_summary": node["summary"],
            "expected_version": 0,
            **extra,
        },
    )


def test_canvas_edit_persists_and_rejects_stale_writes(plain_client):
    conversation_id, node = seed(plain_client)
    response = edit(plain_client, conversation_id, node)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["canvas_edit_version"] == 1
    assert saved["turns"][0]["knowledge_release_id"] == "preview"
    edited = saved["research_map"]["nodes"][0]
    assert edited["id"] == node["id"]
    assert edited["title"] == "关系支持是否影响留城？"
    assert edited["status"] == "developing"
    assert edited["user_edited"] is True
    assert edited["citation_ids"] == node["citation_ids"]
    restored = plain_client.get(f"/api/agent/conversations/{conversation_id}").json()
    assert restored["research_map"]["nodes"][0] == edited
    assert edit(plain_client, conversation_id, node).status_code == 409
    assert (
        edit(
            plain_client, conversation_id, {**node, "id": "unknown"}, expected_version=1
        ).status_code
        == 404
    )


def test_canvas_edit_does_not_grant_source_or_status_control(plain_client):
    conversation_id, node = seed(plain_client)
    response = edit(
        plain_client, conversation_id, node, citation_ids=["invented"], status="verified"
    )
    assert response.status_code == 422


def test_canvas_edit_rejects_another_owner(plain_client):
    conversation_id, node = seed(plain_client)
    plain_client.post("/api/session/logout")
    plain_client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": f"{uuid4()}@example.com", "password": "another-passphrase"},
    )
    assert edit(plain_client, conversation_id, node).status_code == 404


def test_inflight_removal_cannot_disconnect_a_saved_card():
    from qunxue_api.modules.agent_conversation import apply_canvas_edits, prepare_canvas_edit
    from qunxue_api.modules.agent_conversation.research_map import aggregate_research_map

    claim = {
        "id": "claim",
        "kind": "claim",
        "title": "旧主张",
        "summary": "旧说明",
        "status": "grounded",
        "citation_ids": ["real-source"],
    }
    question = {**claim, "id": "question", "kind": "question"}
    relation = {"id": "relation", "source": "question", "target": "claim", "relation": "derives"}
    first = {"nodes": [question, claim], "relations": [relation]}
    edit = prepare_canvas_edit(
        aggregate_research_map([first]),
        node_id="claim",
        title="用户主张",
        summary="用户说明",
        expected_title="旧主张",
        expected_summary="旧说明",
    )
    old_run = {"remove_node_ids": ["claim"], "nodes": [claim]}
    restored = apply_canvas_edits(
        aggregate_research_map([first, old_run], protected_since={"claim": edit["_patch_count"]}),
        {"claim": edit},
    )
    assert restored["relations"] == [relation]
    assert restored["nodes"][1]["title"] == "用户主张"
    assert restored["nodes"][1]["status"] == "developing"
    reviewed = {
        **claim,
        "reviewed_user_title": "用户主张",
        "reviewed_user_summary": "用户说明",
        "citation_ids": ["new-real-source"],
        "status": "grounded",
    }
    verified = apply_canvas_edits({"nodes": [reviewed], "relations": []}, {"claim": edit})
    assert verified["nodes"][0]["status"] == "grounded"
    assert verified["nodes"][0]["citation_ids"] == ["new-real-source"]
    assert verified["nodes"][0]["title"] == "用户主张"
    stale = {**reviewed, "reviewed_user_title": "另一版主张"}
    assert (
        apply_canvas_edits({"nodes": [stale]}, {"claim": edit})["nodes"][0]["status"]
        == "developing"
    )


def test_repeated_user_saves_keep_the_first_protection_boundary(plain_client):
    conversation_id, node = seed(plain_client)
    first = edit(plain_client, conversation_id, node).json()
    owner = UUID(plain_client.get("/api/session").json()["user"]["user_id"])
    with plain_client.app.state.database.session() as session:
        service = ConversationService(SqliteConversationRepository(session))
        run = service.start_run(
            user_id=owner,
            conversation_id=UUID(conversation_id),
            idempotency_key="inflight-old-map",
            knowledge_release_id="preview",
        )
        turn = service.append_turn(
            user_id=owner,
            conversation_id=UUID(conversation_id),
            idempotency_key="inflight-old-map",
            user_content="旧任务",
            assistant_content="旧任务结束",
            citations=(),
        )
        patch = {
            "schema_version": 1,
            "nodes": [node],
            "relations": [],
            "remove_node_ids": [node["id"]],
            "remove_relation_ids": [],
        }
        service.finish_run(
            run_id=run.run_id,
            status="completed",
            turn_id=turn.turn_id,
            tool_summary=(
                {
                    "tool": "update_research_map",
                    "phase": "finished",
                    "call_id": "old-map",
                    "output": patch,
                },
            ),
        )
        service.commit()
    restored = plain_client.get(f"/api/agent/conversations/{conversation_id}").json()
    assert restored["research_map"]["relations"] == first["research_map"]["relations"]
    saved_node = restored["research_map"]["nodes"][0]
    second = edit(
        plain_client, conversation_id, saved_node, expected_version=1, title="第二次人工修订"
    ).json()
    assert second["research_map"]["relations"] == first["research_map"]["relations"]
    assert second["research_map"]["nodes"][0]["title"] == "第二次人工修订"
