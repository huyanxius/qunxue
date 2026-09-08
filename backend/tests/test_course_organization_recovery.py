from uuid import uuid4

import pytest

from qunxue_api.adapters.model.routing import (
    InMemoryModelAttemptRecorder,
    ModelEndpoint,
    ModelRouteExecutor,
)
from qunxue_api.adapters.research_agent.course_organization import (
    CourseKnowledgeGenerator,
    CourseOrganizationError,
)
from qunxue_api.modules.shared_knowledge import SharedDocument


def document(texts):
    return SharedDocument(
        uuid4(),
        uuid4(),
        "course.txt",
        "text/plain",
        "hash",
        1,
        uuid4(),
        "ready",
        segments=tuple({"segment_id": f"s{i}", "text": t} for i, t in enumerate(texts)),
    )


def knowledge(batch):
    return {
        "summary": "课程摘要",
        "topics": [
            {
                "title": "共同主题",
                "summary": batch[0]["text"][:80],
                "segment_ids": [s["segment_id"] for s in batch],
            }
        ],
        "relations": [],
    }


def generator(invoke, count=2):
    endpoints = tuple(
        ModelEndpoint(f"endpoint-{i}", f"https://provider-{i}.invalid", "model", "private-key", 30)
        for i in range(count)
    )
    recorder = InMemoryModelAttemptRecorder()
    router = ModelRouteExecutor(endpoints=endpoints, recorder=recorder)

    class Controlled(CourseKnowledgeGenerator):
        async def _generate_at_endpoint(self, endpoint, batch):
            return await invoke(endpoint, batch)

    return Controlled(endpoints, route_executor=router), recorder


@pytest.mark.parametrize("invalid_source", [False, True])
def test_shared_route_recovers_timeout_or_invalid_sources(invalid_source):
    calls = []

    async def invoke(endpoint, batch):
        calls.append(endpoint.endpoint_id)
        if endpoint.endpoint_id == "endpoint-0":
            if not invalid_source:
                raise TimeoutError("credential must not escape")
            result = knowledge(batch)
            result["topics"][0]["segment_ids"] = ["invented"]
            return result
        return knowledge(batch)

    gen, recorder = generator(invoke)
    result = gen(document(["有效原文"]))
    assert result["topics"][0]["segment_ids"] == ["s0"]
    assert calls == ["endpoint-0", "endpoint-1"]
    attempts = recorder.list_all()
    assert [a.success for a in attempts] == [False, True]
    assert attempts[0].context.operation == "course_organization"
    assert attempts[0].failure_code in ("model_timeout", "model_invalid_output")


def test_completed_batches_survive_failure_and_new_generator():
    calls = []
    saved = {}
    fail = True

    async def invoke(endpoint, batch):
        calls.append(batch[0]["segment_id"])
        if batch[0]["segment_id"] == "s1" and fail:
            raise TimeoutError("secret")
        return knowledge(batch)

    gen, _ = generator(invoke, 1)
    doc = document(["甲" * 4000, "乙" * 4000, "丙" * 4000])
    with pytest.raises(CourseOrganizationError):
        gen(doc, checkpoints=saved, on_checkpoint=lambda value: saved.update(value))
    assert calls == ["s0", "s1"] and len(saved["batches"]) == 1
    fail = False
    resumed, _ = generator(invoke, 1)
    result = resumed(doc, checkpoints=saved, on_checkpoint=lambda value: saved.update(value))
    assert calls == ["s0", "s1", "s1", "s2"]
    assert set(result["topics"][0]["segment_ids"]) == {"s0", "s1", "s2"}
    assert len(saved["batches"]) == 3


def test_batch_budget_counts_segments_and_preserves_long_source():
    gen, _ = generator(lambda *_: None, 1)
    doc = document(["短句"] * 250 + ["长" * 14000])
    batches = gen.batches(doc)
    assert all(len(b) <= 60 and sum(len(s["text"]) for s in b) <= 5000 for b in batches)
    assert sum(len(s["text"]) for b in batches for s in b) == sum(
        len(s["text"]) for s in doc.segments
    )
    assert {s["segment_id"] for b in batches for s in b} == {s["segment_id"] for s in doc.segments}


def test_worker_persists_checkpoint_and_safe_failed_batch(client):
    from test_research_material_api import _authenticate
    from test_shared_knowledge_api import create_library, mutation, upload

    from qunxue_api.adapters.sqlite.shared_knowledge import SharedDocumentRow

    _authenticate(client)
    kb = create_library(client)
    doc = upload(client, kb["id"])
    with client.app.state.shared_knowledge_scope() as app:
        row = app.repository.session.get(SharedDocumentRow, doc["id"])
        row.segments = [
            {**row.segments[0], "segment_id": f"s{i}", "text": letter * 4000}
            for i, letter in enumerate("甲乙丙")
        ]
        app.repository.commit()
    calls = []
    fail = True

    async def invoke(endpoint, batch):
        calls.append(batch[0]["segment_id"])
        if batch[0]["segment_id"] == "s1" and fail:
            raise TimeoutError("sk-private-credential")
        return knowledge(batch)

    gen, _ = generator(invoke, 1)
    worker = client.app.state.course_organization_worker
    worker.generate = gen
    worker.run_once()
    with client.app.state.shared_knowledge_scope() as app:
        row = app.repository.session.get(SharedDocumentRow, doc["id"])
        assert len(row.knowledge_checkpoints["batches"]) == 1
        assert "2/3" in row.knowledge_error and "超时" in row.knowledge_error
        assert "private" not in row.knowledge_error
    fail = False
    worker.generate = generator(invoke, 1)[0]
    mutation(
        client, "post", f"/api/shared-knowledge-bases/{kb['id']}/documents/{doc['id']}/organize"
    )
    worker.run_once()
    assert calls == ["s0", "s1", "s1", "s2"]
    assert (
        client.get(f"/api/shared-knowledge-bases/{kb['id']}").json()["documents"][0][
            "knowledge_status"
        ]
        == "ready"
    )


def test_final_merge_keeps_all_sources_and_distinct_summaries():
    async def invoke(endpoint, batch):
        return knowledge(batch)

    gen, _ = generator(invoke, 1)
    doc = document([f"第{i}段" + "正文" * 1200 for i in range(40)])
    result = gen(doc)
    assert set(result["topics"][0]["segment_ids"]) == {s["segment_id"] for s in doc.segments}
    assert "第0段" in result["topics"][0]["summary"]
    assert "第2段" in result["topics"][0]["summary"]


def test_source_change_invalidates_cached_batch():
    calls = []

    async def invoke(endpoint, batch):
        calls.append(batch[0]["text"])
        return knowledge(batch)

    gen, _ = generator(invoke, 1)
    saved = {}
    gen(document(["旧正文"]), on_checkpoint=lambda value: saved.update(value))
    result = gen(document(["新正文"]), checkpoints=saved)
    assert calls == ["旧正文", "新正文"]
    assert result["topics"][0]["summary"] == "新正文"


def test_restart_does_not_erase_later_completed_checkpoints():
    async def invoke(endpoint, batch):
        return knowledge(batch)

    gen, _ = generator(invoke, 1)
    doc = document(["甲" * 4000, "乙" * 4000, "丙" * 4000])
    saved = {}
    gen(doc, on_checkpoint=lambda value: saved.update(value))
    snapshots = []
    gen(doc, checkpoints=saved, on_checkpoint=lambda value: snapshots.append(len(value["batches"])))
    assert snapshots == [3, 3, 3]


def test_extraction_uses_short_source_aliases_and_restores_original_ids(monkeypatch):
    import asyncio
    import json
    from types import SimpleNamespace

    from qunxue_api.adapters.research_agent import course_knowledge as module

    captured = {}

    class Agent:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

        async def run(self, prompt, **kwargs):
            captured["batch"] = json.loads(prompt)
            return SimpleNamespace(
                output=module.BatchKnowledge.model_validate(
                    {
                        "summary": "摘要",
                        "topics": [{"title": "知识", "summary": "依据", "segment_ids": ["0"]}],
                    }
                )
            )

    monkeypatch.setattr(module, "Agent", Agent)
    endpoint = ModelEndpoint("primary", "https://provider.invalid", "gpt-5.6-sol", "test-key", 30)
    gen = module.CourseKnowledgeGenerator((endpoint,))
    source_id = str(uuid4())
    result = asyncio.run(
        gen._generate_at_endpoint(endpoint, [{"segment_id": source_id, "text": "课程原文"}])
    )
    assert captured["batch"] == [{"segment_id": "0", "text": "课程原文"}]
    assert result["topics"][0]["segment_ids"] == [source_id]
    assert captured["model_settings"]["openai_reasoning_effort"] == "low"
