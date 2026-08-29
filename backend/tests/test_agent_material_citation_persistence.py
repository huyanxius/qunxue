from uuid import UUID, uuid4

import pytest

from qunxue_api.adapters.sqlite.agent_conversation_repository import (
    SqliteConversationRepository,
    _citation,
    _citation_dict,
    _redact_deleted_material_citation,
)
from qunxue_api.api.routes.agent import _citation as stream_citation
from qunxue_api.application.disciplinary_agent import (
    _agent_citation,
    _evidence_from_citation,
)
from qunxue_api.modules.agent_conversation import (
    AgentCitation,
    AgentEvidence,
    ConversationService,
    ResearchMaterialCitationUnavailable,
)


def _material_citation() -> AgentCitation:
    return AgentCitation(
        citation_id="material:material-1:segment-1",
        label="社区访谈",
        kind="research_material",
        excerpt="受访者描述了迁移后的照护变化。",
        source_id="material-segment:segment-1",
        source_kind="personal_material",
        material_id="material-1",
        parse_id="parse-1",
        segment_id="segment-1",
        locator={"page": 2, "section_path": ["照护"], "paragraph": 3},
        deleted=False,
    )


def test_material_citation_round_trips_all_source_coordinates() -> None:
    original = _material_citation()

    restored = _citation(_citation_dict(original))

    assert restored == original


def test_agent_evidence_and_citation_conversion_preserve_material_coordinates() -> None:
    evidence = AgentEvidence(
        citation_id="material:material-1:segment-1",
        label="社区访谈",
        kind="research_material",
        excerpt="受访者描述了迁移后的照护变化。",
        source_id="material-segment:segment-1",
        source_kind="personal_material",
        material_id="material-1",
        parse_id="parse-1",
        segment_id="segment-1",
        locator={"page": 2, "section_path": ["照护"], "paragraph": 3},
    )

    citation = _agent_citation(evidence)
    restored = _evidence_from_citation(citation)

    assert restored == evidence


def test_deleted_material_citation_keeps_identity_but_redacts_source_text() -> None:
    citation = _material_citation()

    tombstone = _redact_deleted_material_citation(citation)

    assert tombstone.citation_id == citation.citation_id
    assert tombstone.material_id == citation.material_id
    assert tombstone.segment_id == citation.segment_id
    assert tombstone.locator == citation.locator
    assert tombstone.deleted is True
    assert tombstone.excerpt is None


def test_stream_citation_serializes_personal_material_coordinates() -> None:
    evidence = AgentEvidence(
        citation_id="material:material-1:segment-1",
        label="社区访谈",
        kind="research_material",
        excerpt="原文片段",
        source_id="material-segment:segment-1",
        source_kind="personal_material",
        material_id="material-1",
        parse_id="parse-1",
        segment_id="segment-1",
        locator={"page": 2, "paragraph": 3},
        deleted=True,
    )

    assert stream_citation(evidence) == {
        "citation_id": "material:material-1:segment-1",
        "label": "社区访谈",
        "kind": "research_material",
        "excerpt": "原文片段",
        "knowledge_id": None,
        "source_id": "material-segment:segment-1",
        "source_kind": "personal_material",
        "material_id": "material-1",
        "parse_id": "parse-1",
        "segment_id": "segment-1",
        "locator": {"page": 2, "paragraph": 3},
        "deleted": True,
    }


def test_agent_conversation_api_returns_deleted_material_tombstone(client) -> None:
    source_text = "一段不应在删除后继续出现的现场记录。"
    registered = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": f"tombstone-{uuid4()}@example.com", "password": "research-passphrase"},
    )
    assert registered.status_code == 201
    task = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "direct_input"},
    )
    assert task.status_code == 201
    task_id = task.json()["task_id"]
    uploaded = client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "field_note"},
        files={"file": ("notes.txt", source_text.encode(), "text/plain")},
    )
    assert uploaded.status_code == 201
    material = uploaded.json()
    segment = client.get(
        f"/api/research-tasks/{task_id}/materials/{material['material_id']}"
    ).json()["segments"][0]

    user_id = registered.json()["user"]["user_id"]
    with client.app.state.database.session() as session:
        repository = SqliteConversationRepository(session)
        service = ConversationService(repository)
        conversation = service.create_conversation(user_id=UUID(user_id), title="材料引用")
        repository.link_research_task(
            user_id=UUID(user_id),
            conversation_id=conversation.conversation_id,
            task_id=UUID(task_id),
        )
        run = service.start_run(
            user_id=UUID(user_id),
            conversation_id=conversation.conversation_id,
            idempotency_key="tombstone-turn",
            knowledge_release_id="release-tombstone",
        )
        turn = service.append_turn(
            user_id=UUID(user_id),
            conversation_id=conversation.conversation_id,
            idempotency_key="tombstone-turn",
            user_content="记录了什么？",
            assistant_content=f"材料原文写道：{source_text}",
            citations=(
                AgentCitation(
                    citation_id=f"material:{material['material_id']}:{segment['segment_id']}",
                    label="notes.txt",
                    kind="research_material",
                    excerpt=segment["text"],
                    source_kind="personal_material",
                    material_id=material["material_id"],
                    parse_id=segment["parse_id"],
                    segment_id=segment["segment_id"],
                    locator=segment["locator"],
                ),
            ),
        )
        service.finish_run(
            run_id=run.run_id,
            status="completed",
            turn_id=turn.turn_id,
            tool_summary=(
                {
                    "tool": "search_research_materials",
                    "phase": "started",
                    "call_id": "material-search",
                    "input": {"query": "现场记录"},
                    "detail": "正在检索个人研究材料",
                },
                {
                    "tool": "search_research_materials",
                    "phase": "finished",
                    "call_id": "material-search",
                    "input": {"query": "现场记录"},
                    "output": {
                        "result_count": 1,
                        "items": [
                            {
                                "material_id": material["material_id"],
                                "segment_id": segment["segment_id"],
                                "excerpt": source_text,
                            }
                        ],
                    },
                    "detail": f"找到个人材料：{source_text}",
                },
            ),
        )
        service.commit()
        conversation_id = str(conversation.conversation_id)

    deleted = client.delete(
        f"/api/research-tasks/{task_id}/materials/{material['material_id']}",
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert deleted.status_code == 204
    detail = client.get(f"/api/agent/conversations/{conversation_id}")
    assert detail.status_code == 200
    turn = detail.json()["turns"][0]
    citation = turn["assistant"]["citations"][0]
    assert citation["deleted"] is True
    assert citation["excerpt"] is None
    assert citation["material_id"] == material["material_id"]
    assert citation["segment_id"] == segment["segment_id"]
    assert turn["assistant"]["content"] == "该回答引用的个人研究材料已删除，原回答内容已隐藏。"
    assert turn["tool_traces"][1]["output"] == {"deleted": True}
    assert turn["tool_traces"][1]["detail"] == "个人研究材料已删除，历史工具结果已隐藏。"
    assert source_text not in detail.text

    replay = client.post(
        "/api/agent/turns",
        headers={"Idempotency-Key": "tombstone-turn"},
        json={
            "conversation_id": conversation_id,
            "message": "记录了什么？",
            "workspace": "research",
            "task_id": task_id,
        },
    )
    assert replay.status_code == 200
    assert "event: turn_completed" in replay.text
    assert source_text not in replay.text


def test_agent_conversation_does_not_restore_material_from_another_task(client) -> None:
    registered = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": f"task-bound-{uuid4()}@example.com", "password": "research-passphrase"},
    )
    assert registered.status_code == 201
    first_task = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "direct_input"},
    )
    second_task = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "direct_input"},
    )
    assert first_task.status_code == second_task.status_code == 201
    first_task_id = first_task.json()["task_id"]
    second_task_id = second_task.json()["task_id"]
    uploaded = client.post(
        f"/api/research-tasks/{first_task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "field_note"},
        files={"file": ("notes.txt", "第一任务的现场记录。".encode(), "text/plain")},
    )
    assert uploaded.status_code == 201
    material = uploaded.json()
    segment = client.get(
        f"/api/research-tasks/{first_task_id}/materials/{material['material_id']}"
    ).json()["segments"][0]

    user_id = UUID(registered.json()["user"]["user_id"])
    with client.app.state.database.session() as session:
        repository = SqliteConversationRepository(session)
        service = ConversationService(repository)
        conversation = service.create_conversation(user_id=user_id, title="跨任务材料引用")
        repository.link_research_task(
            user_id=user_id,
            conversation_id=conversation.conversation_id,
            task_id=UUID(second_task_id),
        )
        with pytest.raises(ResearchMaterialCitationUnavailable):
            service.append_turn(
                user_id=user_id,
                conversation_id=conversation.conversation_id,
                idempotency_key="cross-task-turn",
                user_content="记录了什么？",
                assistant_content="见引用。",
                citations=(
                    AgentCitation(
                        citation_id=f"material:{material['material_id']}:{segment['segment_id']}",
                        label="notes.txt",
                        kind="research_material",
                        excerpt=segment["text"],
                        source_kind="personal_material",
                        material_id=material["material_id"],
                        parse_id=segment["parse_id"],
                        segment_id=segment["segment_id"],
                        locator=segment["locator"],
                    ),
                ),
            )
        conversation_id = str(conversation.conversation_id)

    detail = client.get(f"/api/agent/conversations/{conversation_id}")
    assert detail.status_code == 200
    assert detail.json()["turns"] == []


def test_deleted_material_cannot_be_persisted_as_a_new_agent_citation(client) -> None:
    registered = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "email": f"citation-race-{uuid4()}@example.com",
            "password": "research-passphrase",
        },
    )
    task = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "direct_input"},
    )
    assert registered.status_code == task.status_code == 201
    task_id = task.json()["task_id"]
    material = client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "field_note"},
        files={"file": ("notes.txt", "一段现场记录。".encode(), "text/plain")},
    ).json()
    segment = client.get(
        f"/api/research-tasks/{task_id}/materials/{material['material_id']}"
    ).json()["segments"][0]
    user_id = UUID(registered.json()["user"]["user_id"])
    with client.app.state.database.session() as session:
        service = ConversationService(SqliteConversationRepository(session))
        conversation = service.create_conversation(user_id=user_id, title="材料引用")
        service.link_research_task(
            user_id=user_id,
            conversation_id=conversation.conversation_id,
            task_id=UUID(task_id),
        )
        service.commit()
        conversation_id = conversation.conversation_id

    deleted = client.delete(
        f"/api/research-tasks/{task_id}/materials/{material['material_id']}",
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert deleted.status_code == 204

    with client.app.state.database.session() as session:
        service = ConversationService(SqliteConversationRepository(session))
        with pytest.raises(ResearchMaterialCitationUnavailable):
            service.append_turn(
                user_id=user_id,
                conversation_id=conversation_id,
                idempotency_key="deleted-source-turn",
                user_content="记录了什么？",
                assistant_content="见引用。",
                citations=(
                    AgentCitation(
                        citation_id=(
                            f"material:{material['material_id']}:{segment['segment_id']}"
                        ),
                        label="notes.txt",
                        kind="research_material",
                        excerpt=segment["text"],
                        source_kind="personal_material",
                        material_id=material["material_id"],
                        parse_id=segment["parse_id"],
                        segment_id=segment["segment_id"],
                        locator=segment["locator"],
                    ),
                ),
            )

    detail = client.get(f"/api/agent/conversations/{conversation_id}")
    assert detail.status_code == 200
    assert detail.json()["turns"] == []
