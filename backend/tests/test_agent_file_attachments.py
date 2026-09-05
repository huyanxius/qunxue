from uuid import UUID, uuid4

import pytest

from qunxue_api.adapters.research_agent.document_tools import ResearchDocumentToolRegistry
from qunxue_api.adapters.sqlite.research_material_repository import SqliteResearchMaterialRepository


def register(client):
    response = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": f"files-{uuid4()}@example.com", "password": "research-passphrase"},
    )
    assert response.status_code == 201
    return UUID(response.json()["user"]["user_id"])


def upload(client, text="紫藤社区有 37 位居民参与夜间互助。", filename="notes.txt"):
    task = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "direct_input"},
    )
    task_id = task.json()["task_id"]
    response = client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "field_note"},
        files={"file": (filename, text.encode(), "text/plain")},
    )
    assert response.status_code == 201
    from dataclasses import replace

    from qunxue_api.adapters.sqlite.professional_material_repository import (
        SqliteProfessionalMaterialRepository,
    )
    from qunxue_api.adapters.sqlite.research_material_model import ResearchMaterialRow
    from qunxue_api.modules.research_materials import DeidentificationStatus, ModelProcessingScope

    data = response.json()
    with client.app.state.database.session() as session:
        row = session.get(ResearchMaterialRow, data["material_id"])
        archive = SqliteProfessionalMaterialRepository(session)
        profile = archive.get_profile(
            UUID(row.material_id), user_id=UUID(row.user_id), task_id=UUID(task_id)
        )
        archive.save_profile(
            replace(
                profile,
                model_processing_scope=ModelProcessingScope.EXTERNAL_ALLOWED,
                deidentification_status=DeidentificationStatus.NOT_REQUIRED,
            )
        )
        session.commit()
    return data


def test_material_context_is_idempotent_and_owned(client):
    register(client)
    headers = {"Idempotency-Key": str(uuid4())}
    first = client.post("/api/agent/material-context", headers=headers, json={})
    assert first.status_code == 200
    second = client.post("/api/agent/material-context", headers=headers, json={})
    assert second.json() == first.json()
    existing = client.post(
        "/api/agent/material-context",
        headers={"Idempotency-Key": str(uuid4())},
        json={"conversation_id": first.json()["conversation_id"]},
    )
    assert existing.json() == first.json()
    register(client)
    denied = client.post(
        "/api/agent/material-context",
        headers={"Idempotency-Key": str(uuid4())},
        json={"conversation_id": first.json()["conversation_id"]},
    )
    assert denied.status_code == 404


def test_global_file_list_contains_only_owned_materials(client):
    register(client)
    first = upload(client)
    second = upload(client, "另一份社区记录")
    response = client.get("/api/agent/materials")
    assert response.status_code == 200
    assert {row["material_id"] for row in response.json()["items"]} == {
        first["material_id"],
        second["material_id"],
    }
    register(client)
    assert client.get("/api/agent/materials").json()["items"] == []


def test_explicit_attachment_can_read_other_owned_task_and_reject_other_user(client):
    user_id = register(client)
    source = upload(client)
    with client.app.state.database.session() as session:
        repo = SqliteResearchMaterialRepository(session)
        tools = object.__new__(ResearchDocumentToolRegistry)
        tools._materials = repo
        attachments = tools.pin_research_material_scope(
            user_id=user_id, task_id=uuid4(), material_ids=(UUID(source["material_id"]),)
        )
        assert str(attachments[0].parse_id) == source["parse_id"]
        with pytest.raises(ValueError):
            tools.pin_research_material_scope(
                user_id=uuid4(), task_id=uuid4(), material_ids=(UUID(source["material_id"]),)
            )


@pytest.mark.parametrize("mode", ["standard", "deep_research"])
def test_standalone_file_answer_survives_history_and_respects_scope(client, mode):
    from types import SimpleNamespace

    from qunxue_api.modules.agent_conversation import AgentRunResult

    user_id = register(client)
    source = upload(client)
    other = upload(client, "不应该进入回答的材料")
    context = client.post(
        "/api/agent/material-context", headers={"Idempotency-Key": str(uuid4())}, json={}
    ).json()

    class FileRunner:
        runtime_identity = SimpleNamespace(provider="test", model="test")

        def run(self, *, prompt, conversation, tools):
            files = tools.material_prompt_context
            assert len(files) == 1
            assert files[0]["material_id"] == source["material_id"]
            result = tools.read_research_material_context(
                files[0]["material_id"], files[0]["first_segment_id"]
            )
            assert result["locator"]["task_id"] == source["task_id"]
            assert (
                tools.read_research_material_context(
                    other["material_id"], files[0]["first_segment_id"]
                )["error"]
                == "research_material_outside_turn_scope"
            )
            found = tools.search_research_materials("夜间互助")
            assert [row["material_id"] for row in found] == [source["material_id"]]
            return AgentRunResult(
                answer=f"有 37 位居民。[{result['citation_id']}]",
                citations=(tools.evidence[result["citation_id"]],),
                release_id=tools.release.knowledge_release_id,
                provider="test",
                model="test",
            )

    with client.app.state.disciplinary_agent_scope() as app:
        app._runner = FileRunner()
        execution = app.run_turn(
            user_id=user_id,
            conversation_id=UUID(context["conversation_id"]),
            prompt="夜间互助有几位居民？",
            idempotency_key=str(uuid4()),
            workspace="agent",
            mode=mode,
            material_ids=(UUID(source["material_id"]),),
        )
    history = client.get(
        f"/api/agent/conversations/{execution.conversation.conversation_id}"
    ).json()
    answer = history["turns"][0]["assistant"]
    assert "37" in answer["content"]
    assert answer["citations"][0]["deleted"] is False
    assert answer["citations"][0]["material_id"] == source["material_id"]
    client.delete(
        f"/api/research-tasks/{source['task_id']}/materials/{source['material_id']}",
        headers={"Idempotency-Key": str(uuid4())},
    )
    deleted = client.get(
        f"/api/agent/conversations/{execution.conversation.conversation_id}"
    ).json()
    assert deleted["turns"][0]["assistant"]["citations"][0]["deleted"] is True


def test_cached_file_vectors_are_owned_persistent_and_deleted_with_source(client):
    from sqlalchemy import select

    from qunxue_api.adapters.retrieval import RetrievalChunk
    from qunxue_api.adapters.sqlite.material_vector_cache import SqliteMaterialVectorCache
    from qunxue_api.adapters.sqlite.research_material_model import ResearchMaterialBlockRow

    user_id = register(client)
    source = upload(client)
    material_id, parse_id = UUID(source["material_id"]), UUID(source["parse_id"])
    with client.app.state.database.session() as session:
        block = session.scalar(
            select(ResearchMaterialBlockRow).where(
                ResearchMaterialBlockRow.parse_id == str(parse_id)
            )
        )
        chunk = RetrievalChunk(
            chunk_id=f"material-segment:{material_id}:{block.segment_id}",
            document_kind="research_material",
            knowledge_id=None,
            theory_id=None,
            content_version=1,
            content_hash=block.content_hash,
            title="笔记",
            text=block.text,
            source_ids=(),
        )
        cache = SqliteMaterialVectorCache(
            session, user_id=user_id, parse_ids={material_id: parse_id}
        )
        assert cache.get_many([chunk], "embedding-a") == [None]
        cache.put_many([chunk], "embedding-a", [[0.1, 0.9]])
        session.commit()
    with client.app.state.database.session() as session:
        cache = SqliteMaterialVectorCache(
            session, user_id=user_id, parse_ids={material_id: parse_id}
        )
        assert cache.get_many([chunk], "embedding-a") == [[0.1, 0.9]]
        assert cache.get_many([chunk], "embedding-b") == [None]
        outsider = SqliteMaterialVectorCache(
            session, user_id=uuid4(), parse_ids={material_id: parse_id}
        )
        assert outsider.get_many([chunk], "embedding-a") == [None]
    response = client.delete(
        f"/api/research-tasks/{source['task_id']}/materials/{source['material_id']}",
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 204
    with client.app.state.database.session() as session:
        cache = SqliteMaterialVectorCache(
            session, user_id=user_id, parse_ids={material_id: parse_id}
        )
        assert cache.get_many([chunk], "embedding-a") == [None]


def test_small_selected_file_uses_original_text_without_embedding_call(client):
    from types import SimpleNamespace

    user_id = register(client)
    source = upload(client)
    with client.app.state.disciplinary_agent_scope() as app:
        tools = app._tools_factory()
        tools.pin_research_material_scope(
            user_id=user_id,
            task_id=UUID(source["task_id"]),
            material_ids=(UUID(source["material_id"]),),
        )
        tools.bind_agent_context(
            user_id=user_id,
            conversation_id=uuid4(),
            agent_run_id=uuid4(),
            task_id=UUID(source["task_id"]),
        )

        def unexpected_embedding(**kwargs):
            raise AssertionError("small files should not need vector retrieval")

        tools._retriever = SimpleNamespace(search_chunks=unexpected_embedding)
        rows = tools.search_research_materials("参与者人数")
        assert rows[0]["retrieval_mode"] == "direct"
        assert "37" in rows[0]["excerpt"]


def test_multifile_hybrid_search_persists_vectors_and_excludes_unselected_files(client, tmp_path):
    from qunxue_api.adapters.research_agent.reranker import RerankScore
    from qunxue_api.adapters.retrieval import SqliteRetrievalIndex
    from qunxue_api.adapters.retrieval.hybrid import HybridRetriever

    user_id = register(client)
    primary = upload(client, "城北研究：29位受访者因托育时间冲突无法参加互助活动。", "城北.txt")
    counter = upload(client, "城南研究：17位受访者主要受限于通勤，托育不是主要障碍。", "城南.txt")
    distractors = [upload(client, f"无关天气资料{i}。" + "晴转多云。" * 350) for i in range(4)]
    upload(client, "城北城南托育通勤：这份未选择的文件绝不可进入模型。")
    document_calls, query_calls, rerank_calls = [], [], []

    # Controlled providers isolate retrieval scope and billing-relevant request counts.
    # Semantic quality of the live BGE service is a separate acceptance check.
    class Embedder:
        def embed_query(self, query):
            query_calls.append(query)
            return [1.0, 0.0]

        def embed_documents(self, texts):
            document_calls.extend(texts)
            return [[1.0, 0.0] if "受访者" in text else [0.0, 1.0] for text in texts]

    class Reranker:
        def rerank(self, *, query, documents, top_n):
            rerank_calls.append(len(documents))
            return tuple(
                RerankScore(index=i, score=0.95 if "受访者" in text else 0.001)
                for i, text in enumerate(documents)
            )

    retriever = HybridRetriever(
        index=SqliteRetrievalIndex(tmp_path / "public-index.db"),
        embedder=Embedder(),
        embedding_model="controlled-embedding",
        chunk_schema_version="1",
        reranker=Reranker(),
        reranker_model="controlled-reranker",
        min_rerank_score=0.01,
    )
    selected = tuple(UUID(row["material_id"]) for row in [primary, counter, *distractors])
    for query in ("照顾孩子和出行分别造成什么困难？", "比较两个地区参与社区活动的阻碍"):
        # Reopen the application scope to ensure reuse is durable, not just an in-run cache.
        with client.app.state.disciplinary_agent_scope() as app:
            tools = app._tools_factory()
            tools._material_retriever = retriever
            tools.pin_research_material_scope(
                user_id=user_id, task_id=UUID(primary["task_id"]), material_ids=selected
            )
            tools.bind_agent_context(
                user_id=user_id,
                task_id=UUID(primary["task_id"]),
                conversation_id=uuid4(),
                agent_run_id=uuid4(),
            )
            rows = tools.search_research_materials(query, limit=2)
            assert {row["material_id"] for row in rows} == {
                primary["material_id"],
                counter["material_id"],
            }
            assert all(row["parse_id"] and row["segment_id"] for row in rows)
            assert sum(len(row["excerpt"]) for row in rows) < 100
    assert len(document_calls) == 6
    assert len(query_calls) == len(rerank_calls) == 2
    assert max(rerank_calls) <= 30
    assert all("绝不可进入模型" not in text for text in document_calls)


def test_runner_keeps_citations_when_reading_multiple_files_in_sequence(client):
    import json

    from pydantic_ai.models.function import DeltaToolCall, FunctionModel

    from qunxue_api.adapters.research_agent.pydantic_runner import PydanticAIKnowledgeRunner

    user_id = register(client)
    sources = [upload(client, text) for text in ("城北有29位居民。", "城南有17位居民。")]
    runner = PydanticAIKnowledgeRunner(
        base_url="https://example.invalid", api_key="test", model="test", timeout_seconds=30
    )
    with client.app.state.disciplinary_agent_scope() as app:
        tools = app._tools_factory()
        tools.pin_research_material_scope(
            user_id=user_id,
            task_id=UUID(sources[0]["task_id"]),
            material_ids=tuple(UUID(row["material_id"]) for row in sources),
        )
        tools.bind_agent_context(
            user_id=user_id,
            task_id=UUID(sources[0]["task_id"]),
            conversation_id=uuid4(),
            agent_run_id=uuid4(),
        )
        tools.enable_research_material_tools()
        pending = list(tools.material_prompt_context)

        async def stream(messages, info):
            if pending:
                source = pending.pop(0)
                yield {
                    0: DeltaToolCall(
                        name="read_research_material_context",
                        json_args=json.dumps(
                            {
                                "material_id": source["material_id"],
                                "segment_id": source["first_segment_id"],
                            }
                        ),
                        tool_call_id=f"read-{len(pending)}",
                    )
                }
            else:
                yield "城北29人，城南17人。"

        with runner._agent.override(model=FunctionModel(stream_function=stream)):
            result = runner.run_stream(
                prompt="比较两份文件",
                conversation=(),
                tools=tools,
                on_delta=lambda _: None,
            )
        assert {citation.material_id for citation in result.citations if citation.material_id} == {
            row["material_id"] for row in sources
        }
