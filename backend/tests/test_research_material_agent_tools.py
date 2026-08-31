from dataclasses import replace
from datetime import UTC, datetime
from inspect import signature
from types import SimpleNamespace
from uuid import UUID

from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from qunxue_api.adapters.research_agent.catalog_tools import KnowledgeToolRegistry
from qunxue_api.adapters.research_agent.document_tools import ResearchDocumentToolRegistry
from qunxue_api.adapters.research_agent.pydantic_runner import (
    DeterministicKnowledgeRunner,
    PydanticAIKnowledgeRunner,
    _select_result_evidence,
)
from qunxue_api.adapters.retrieval import RetrievalChunk
from qunxue_api.adapters.retrieval.hybrid import HybridRetrievalHit, HybridRetrievalResult
from qunxue_api.modules.agent_conversation import AgentEvidence, AgentToolContext
from qunxue_api.modules.research_materials import (
    MaterialBlock,
    MaterialFormat,
    MaterialKind,
    MaterialLocator,
    MaterialParseVersion,
    MaterialStatus,
    ResearchMaterial,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000101")
TASK_ID = UUID("00000000-0000-0000-0000-000000000102")
MATERIAL_ID = UUID("00000000-0000-0000-0000-000000000103")
PARSE_ID = UUID("00000000-0000-0000-0000-000000000104")
HISTORICAL_PARSE_ID = UUID("00000000-0000-0000-0000-000000000107")


def test_agent_material_context_port_accepts_optional_parse_id():
    parameters = signature(AgentToolContext.read_research_material_context).parameters

    assert "parse_id" in parameters
    assert parameters["parse_id"].default is None


def _material_and_parse(*, deleted: bool = False):
    locator = MaterialLocator(page=2, section_path=("照护",), paragraph=3)
    block = MaterialBlock.create(
        parse_id=PARSE_ID,
        material_id=MATERIAL_ID,
        ordinal=0,
        kind="paragraph",
        text="受访者描述了迁移后的照护变化。",
        locator=locator,
    )
    parsed = MaterialParseVersion.create(
        parse_id=PARSE_ID,
        material_id=MATERIAL_ID,
        version=1,
        parser_name="test",
        parser_version="1",
        schema_version="1",
        full_text=block.text,
        structured_document={},
        blocks=(block,),
        now=datetime(2026, 8, 29, tzinfo=UTC),
    )
    material = ResearchMaterial(
        material_id=MATERIAL_ID,
        user_id=USER_ID,
        task_id=TASK_ID,
        idempotency_key="material-1",
        original_filename="访谈.docx",
        display_name="社区访谈",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        material_format=MaterialFormat.DOCX,
        material_kind=MaterialKind.INTERVIEW_TRANSCRIPT,
        size_bytes=100,
        content_hash="a" * 64,
        status=MaterialStatus.DELETED if deleted else MaterialStatus.READY,
        current_parse_id=None if deleted else PARSE_ID,
        current_parse_version=None if deleted else 1,
        processing_policy_version="1",
        created_at=datetime(2026, 8, 29, tzinfo=UTC),
        updated_at=datetime(2026, 8, 29, tzinfo=UTC),
        deleted_at=datetime(2026, 8, 29, tzinfo=UTC) if deleted else None,
    )
    return material, parsed, block


class _Materials:
    def __init__(self, *, deleted: bool = False, external_model_allowed: bool = True):
        self.material, self.parsed, self.block = _material_and_parse(deleted=deleted)
        self.external_model_allowed = external_model_allowed

    def list(self, *, user_id, task_id, include_deleted=False, limit=100, offset=0):
        assert user_id == USER_ID
        assert task_id == TASK_ID
        del limit, offset
        if self.material.status is MaterialStatus.DELETED and not include_deleted:
            return ()
        return (self.material,)

    def get(self, material_id, *, user_id, task_id, include_deleted=False):
        if material_id != MATERIAL_ID or user_id != USER_ID or task_id != TASK_ID:
            return None
        if self.material.status is MaterialStatus.DELETED and not include_deleted:
            return None
        return self.material

    def get_parse(self, material_id, parse_id, *, user_id, task_id):
        if (
            material_id != MATERIAL_ID
            or parse_id != PARSE_ID
            or user_id != USER_ID
            or task_id != TASK_ID
            or self.material.status is MaterialStatus.DELETED
        ):
            return None
        return self.parsed

    def get_segment(self, material_id, parse_id, segment_id, *, user_id, task_id):
        if (
            material_id != MATERIAL_ID
            or parse_id != PARSE_ID
            or segment_id != self.block.segment_id
            or user_id != USER_ID
            or task_id != TASK_ID
            or self.material.status is MaterialStatus.DELETED
        ):
            return None
        return self.block

    def is_external_model_processable(self, material_id, *, user_id, task_id):
        assert material_id == MATERIAL_ID
        assert user_id == USER_ID
        assert task_id == TASK_ID
        return self.external_model_allowed


class _ReparsedMaterials(_Materials):
    """Expose an old immutable parse while the material points at a newer one."""

    def __init__(self):
        super().__init__()
        old_block = MaterialBlock.create(
            parse_id=HISTORICAL_PARSE_ID,
            material_id=MATERIAL_ID,
            ordinal=0,
            kind="paragraph",
            text="重解析前的照护记录。",
            locator=MaterialLocator(page=1, section_path=("旧记录",), paragraph=1),
        )
        self.old_block = old_block
        self.old_parsed = MaterialParseVersion.create(
            parse_id=HISTORICAL_PARSE_ID,
            material_id=MATERIAL_ID,
            version=1,
            parser_name="test",
            parser_version="1",
            schema_version="1",
            full_text=old_block.text,
            structured_document={},
            blocks=(old_block,),
            now=datetime(2026, 8, 28, tzinfo=UTC),
        )
        # The current parse is deliberately different from the historical one.
        self.material = replace(
            self.material,
            current_parse_id=PARSE_ID,
            current_parse_version=2,
        )

    def get_parse(self, material_id, parse_id, *, user_id, task_id):
        if (
            material_id != MATERIAL_ID
            or user_id != USER_ID
            or task_id != TASK_ID
            or self.material.status is MaterialStatus.DELETED
        ):
            return None
        if parse_id == HISTORICAL_PARSE_ID:
            return self.old_parsed
        if parse_id == PARSE_ID:
            return self.parsed
        return None


class _Catalog:
    def current_release(self, *, purpose):
        del purpose
        return SimpleNamespace(knowledge_release_id="release-1", content_hash="hash-1")


class _Retriever:
    def __init__(self):
        self.calls = []

    def search_chunks(self, *, query, chunks, limit):
        self.calls.append((query, tuple(chunks), limit))
        chunk = chunks[0]
        return HybridRetrievalResult(
            retrieval_index_id="materials:test",
            mode="hybrid_reranked",
            embedding_model="shared-embedding",
            reranker_model="shared-reranker",
            degraded_reason=None,
            hits=(
                HybridRetrievalHit(
                    chunk=chunk,
                    fused_score=0.04,
                    retrieval_sources=("lexical", "semantic"),
                    rerank_score=0.91,
                ),
            ),
        )


def _registry(materials, retriever):
    registry = ResearchDocumentToolRegistry(
        catalog=_Catalog(),
        retriever=retriever,
        materials=materials,
        documents=SimpleNamespace(),
        proposals=SimpleNamespace(),
    )
    registry.bind_agent_context(
        user_id=USER_ID,
        conversation_id=UUID("00000000-0000-0000-0000-000000000105"),
        agent_run_id=UUID("00000000-0000-0000-0000-000000000106"),
        task_id=TASK_ID,
    )
    registry.enable_research_material_tools()
    return registry


def test_search_research_materials_uses_shared_hybrid_retrieval_and_exact_locator():
    materials = _Materials()
    retriever = _Retriever()
    registry = _registry(materials, retriever)

    results = registry.search_research_materials("迁移后的照护", limit=3)

    assert len(retriever.calls) == 1
    query, chunks, limit = retriever.calls[0]
    assert query == "迁移后的照护"
    assert limit == 3
    assert len(chunks) == 1
    assert chunks[0].document_kind == "research_material"
    assert chunks[0].knowledge_id is None
    assert results == [
        {
            "citation_id": f"material:{MATERIAL_ID}:{materials.block.segment_id}",
            "source_id": f"material-segment:{materials.block.segment_id}",
            "source_kind": "personal_material",
            "kind": "research_material",
            "material_id": str(MATERIAL_ID),
            "parse_id": str(PARSE_ID),
            "segment_id": materials.block.segment_id,
            "title": "社区访谈",
            "material_kind": "interview_transcript",
            "material_format": "docx",
            "excerpt": materials.block.text,
            "locator": materials.block.locator.as_dict(),
            "retrieval_index_id": "materials:test",
            "retrieval_mode": "hybrid_reranked",
            "retrieval_sources": ["lexical", "semantic"],
            "rerank_score": 0.91,
            "embedding_model": "shared-embedding",
            "reranker_model": "shared-reranker",
            "evidence_status": "verified",
        }
    ]
    evidence = registry.evidence[results[0]["citation_id"]]
    assert evidence.kind == "research_material"
    assert evidence.source_kind == "personal_material"
    assert evidence.locator == materials.block.locator.as_dict()


def test_read_research_material_context_returns_only_owned_current_parse_and_registers_evidence():
    materials = _Materials()
    registry = _registry(materials, _Retriever())

    result = registry.read_research_material_context(
        str(MATERIAL_ID),
        materials.block.segment_id,
        before=1,
        after=1,
    )

    assert result["material_id"] == str(MATERIAL_ID)
    assert result["segment_id"] == materials.block.segment_id
    assert result["locator"] == materials.block.locator.as_dict()
    assert result["context"][0]["text"] == materials.block.text
    assert result["context"][0]["is_target"] is True
    citation_id = result["citation_id"]
    assert registry.evidence[citation_id] == AgentEvidence(
        citation_id=citation_id,
        label="社区访谈",
        kind="research_material",
        excerpt=materials.block.text,
        source_id=f"material-segment:{materials.block.segment_id}",
        source_kind="personal_material",
        material_id=str(MATERIAL_ID),
        parse_id=str(PARSE_ID),
        segment_id=materials.block.segment_id,
        locator=materials.block.locator.as_dict(),
    )


def test_read_research_material_context_can_read_historical_parse_after_reparse():
    materials = _ReparsedMaterials()
    registry = _registry(materials, _Retriever())

    result = registry.read_research_material_context(
        str(MATERIAL_ID),
        materials.old_block.segment_id,
        parse_id=str(HISTORICAL_PARSE_ID),
    )

    assert result["material_id"] == str(MATERIAL_ID)
    assert result["parse_id"] == str(HISTORICAL_PARSE_ID)
    assert result["segment_id"] == materials.old_block.segment_id
    assert result["text"] == materials.old_block.text
    assert result["locator"] == materials.old_block.locator.as_dict()


def test_runner_passes_historical_parse_id_to_material_context_tool():
    materials = _ReparsedMaterials()
    registry = _registry(materials, _Retriever())
    calls: list[str] = []

    async def model_stream(messages, info):
        del messages, info
        if not calls:
            calls.append("read")
            yield {
                0: DeltaToolCall(
                    name="read_research_material_context",
                    json_args=(
                        "{\"material_id\":\""
                        f"{MATERIAL_ID}"
                        "\",\"segment_id\":\""
                        f"{materials.old_block.segment_id}"
                        "\",\"parse_id\":\""
                        f"{HISTORICAL_PARSE_ID}"
                        "\"}"
                    ),
                    tool_call_id="call-read-historical-material",
                )
            }
        else:
            yield "已读取重解析前的原文片段。"

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    with runner._agent.override(model=FunctionModel(stream_function=model_stream)):
        runner.run_stream(
            prompt="读取这条历史材料引用的原文上下文",
            conversation=(),
            tools=registry,
            on_delta=lambda _delta: None,
        )

    historical_citation_id = f"material:{MATERIAL_ID}:{materials.old_block.segment_id}"
    assert historical_citation_id in registry.evidence
    assert registry.evidence[historical_citation_id].parse_id == str(HISTORICAL_PARSE_ID)


def test_deleted_material_is_not_searchable_or_readable():
    materials = _Materials(deleted=True)
    registry = _registry(materials, _Retriever())

    assert registry.search_research_materials("照护") == []
    result = registry.read_research_material_context(
        str(MATERIAL_ID),
        "missing-segment",
    )
    assert result["error"] == "research_material_not_found"


def test_manual_only_material_stays_readable_in_library_but_never_enters_agent_tools():
    materials = _Materials(external_model_allowed=False)
    registry = _registry(materials, _Retriever())

    assert materials.get(MATERIAL_ID, user_id=USER_ID, task_id=TASK_ID) is not None
    assert registry.search_research_materials("照护") == []
    result = registry.read_research_material_context(
        str(MATERIAL_ID),
        materials.block.segment_id,
    )
    assert result["error"] == "research_material_model_processing_restricted"


def test_empty_material_search_does_not_clear_previously_selected_public_evidence():
    public = AgentEvidence(
        citation_id="retrieval:public-empty-material",
        label="公共知识",
        kind="entry",
        excerpt="公共材料证据",
    )
    class _EmptyMaterialRetriever:
        def search_chunks(self, *, query, chunks, limit):
            del query, chunks, limit
            return HybridRetrievalResult(
                retrieval_index_id="materials:test",
                mode="hybrid_reranked",
                embedding_model="shared-embedding",
                reranker_model="shared-reranker",
                degraded_reason=None,
                hits=(),
            )

    tools = _registry(_Materials(), _EmptyMaterialRetriever())
    tools.evidence[public.citation_id] = public
    tools.select_evidence((public.citation_id,))

    assert tools.search_research_materials("完全不存在的词") == []
    assert tools.selected_evidence_ids == (public.citation_id,)


def test_pydantic_empty_material_result_preserves_public_selection():
    public_id = "retrieval:public-before-empty-material"

    class _Tools:
        release = SimpleNamespace(knowledge_release_id="release-1")
        research_material_tools_enabled = True
        research_document_tools_enabled = False
        research_handoff_tools_enabled = False
        research_map_enabled = False

        def __init__(self):
            self.evidence = {}
            self.selected_evidence_ids = ()
            self.calls = []

        def select_evidence(self, citation_ids):
            values = tuple(citation_ids)
            assert set(values) <= set(self.evidence)
            self.selected_evidence_ids = values
            return values

        def search_knowledge(self, query, *, limit=5):
            del query, limit
            self.calls.append("public")
            self.evidence[public_id] = AgentEvidence(
                citation_id=public_id,
                label="公共知识",
                kind="entry",
                excerpt="公共材料证据",
            )
            return [{"citation_id": public_id, "title": "公共知识"}]

        def search_research_materials(self, query, *, limit=5):
            del query, limit
            self.calls.append("personal")
            return []

    tools = _Tools()

    async def model_stream(messages, info):
        del messages, info
        if not tools.calls:
            yield {
                0: DeltaToolCall(
                    name="search_knowledge",
                    json_args='{"query":"照护"}',
                    tool_call_id="call-public-before-material",
                )
            }
        elif tools.calls == ["public"]:
            yield {
                0: DeltaToolCall(
                    name="search_research_materials",
                    json_args='{"query":"照护"}',
                    tool_call_id="call-empty-material",
                )
            }
        else:
            yield "基于公共知识回答。"

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    with runner._agent.override(model=FunctionModel(stream_function=model_stream)):
        result = runner.run_stream(
            prompt="请结合知识库和我的材料解释照护变化",
            conversation=(),
            tools=tools,
            on_delta=lambda _delta: None,
        )

    assert result.answer == "基于公共知识回答。"
    assert tools.selected_evidence_ids == (public_id,)


def test_pydantic_bound_research_turn_preloads_public_and_personal_evidence():
    public_id = "retrieval:public-dual-source"
    public_source_ids = tuple(f"source:public-dual-{index}" for index in range(7))
    personal_id = "material:private-dual-source:segment-1"

    class _Tools:
        release = SimpleNamespace(knowledge_release_id="release-1")
        research_material_tools_enabled = True
        research_document_tools_enabled = True
        research_handoff_tools_enabled = False
        research_map_enabled = True
        research_map = {"schema_version": 1, "nodes": [], "relations": []}
        document_prompt_context = {"task_id": str(TASK_ID)}

        def __init__(self):
            self.evidence = {}
            self.selected_evidence_ids = ()

        def select_evidence(self, citation_ids):
            values = tuple(citation_ids)
            assert set(values) <= set(self.evidence)
            self.selected_evidence_ids = values
            return values

        def search_knowledge(self, query, *, limit=5):
            del query, limit
            self.evidence[public_id] = AgentEvidence(
                citation_id=public_id,
                label="照护劳动公共知识",
                kind="entry",
                excerpt="公共知识指出照护责任受到制度安排影响。",
            )
            for source_id in public_source_ids:
                self.evidence[source_id] = AgentEvidence(
                    citation_id=source_id,
                    label="公共知识来源",
                    kind="source",
                    excerpt="公共来源边界。",
                    source_id=source_id.removeprefix("source:"),
                )
            return [
                {
                    "citation_id": public_id,
                    "title": "照护劳动公共知识",
                    "excerpt": "公共知识指出照护责任受到制度安排影响。",
                    "source_citation_ids": list(public_source_ids),
                }
            ]

        def search_research_materials(self, query, *, limit=5):
            del query, limit
            self.evidence[personal_id] = AgentEvidence(
                citation_id=personal_id,
                label="社区访谈",
                kind="research_material",
                excerpt="受访者说搬家后照护互助明显减少。",
                source_kind="personal_material",
                material_id=str(MATERIAL_ID),
                parse_id=str(PARSE_ID),
                segment_id="segment-1",
                locator={"paragraph": 7},
            )
            return [
                {
                    "citation_id": personal_id,
                    "title": "社区访谈",
                    "excerpt": "受访者说搬家后照护互助明显减少。",
                    "source_kind": "personal_material",
                    "material_id": str(MATERIAL_ID),
                    "parse_id": str(PARSE_ID),
                    "segment_id": "segment-1",
                    "locator": {"paragraph": 7},
                }
            ]

    tools = _Tools()

    async def model_stream(messages, info):
        del info
        visible_prompt = "\n".join(
            str(getattr(part, "content", ""))
            for message in messages
            for part in message.parts
        )
        if (
            "公共知识指出照护责任受到制度安排影响" in visible_prompt
            and "受访者说搬家后照护互助明显减少" in visible_prompt
        ):
            yield "已结合公共知识与个人访谈回答。"
        else:
            yield "没有同时取得两类证据。"

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    events = []
    with runner._agent.override(model=FunctionModel(stream_function=model_stream)):
        result = runner.run_stream(
            prompt="请解释社区迁移后照护互助为何减少",
            conversation=(),
            tools=tools,
            on_delta=lambda _delta: None,
            on_tool_event=events.append,
        )

    assert result.answer == "已结合公共知识与个人访谈回答。"
    assert {public_id, personal_id} <= {
        citation.citation_id for citation in result.citations
    }
    assert {
        event.tool
        for event in events
        if event.phase == "finished"
    } >= {"search_knowledge", "search_research_materials"}


def test_pydantic_bound_research_flow_control_does_not_run_rag():
    class _Tools:
        release = SimpleNamespace(knowledge_release_id="release-1")
        research_material_tools_enabled = True
        research_document_tools_enabled = True
        research_handoff_tools_enabled = False
        research_map_enabled = True
        research_map = {"schema_version": 1, "nodes": [], "relations": []}
        document_prompt_context = {"task_id": str(TASK_ID)}

        def __init__(self):
            self.evidence = {}
            self.selected_evidence_ids = ()

        def select_evidence(self, citation_ids):
            self.selected_evidence_ids = tuple(citation_ids)
            return self.selected_evidence_ids

        def search_knowledge(self, query, *, limit=5):
            del query, limit
            return []

        def search_research_materials(self, query, *, limit=5):
            del query, limit
            return []

    async def model_stream(messages, info):
        del messages, info
        yield "已按你的确认继续。"

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    events = []
    with runner._agent.override(model=FunctionModel(stream_function=model_stream)):
        result = runner.run_stream(
            prompt="确认",
            conversation=(),
            tools=_Tools(),
            on_delta=lambda _delta: None,
            on_tool_event=events.append,
        )

    assert result.answer == "已按你的确认继续。"
    assert events == []
    assert result.citations == ()


def test_pydantic_material_search_and_context_keep_public_evidence_selected():
    materials = _Materials()
    tools = _registry(materials, _Retriever())
    public = AgentEvidence(
        citation_id="retrieval:public-before-material-tools",
        label="公共知识",
        kind="entry",
        excerpt="公共材料证据",
    )
    tools.evidence[public.citation_id] = public
    tools.select_evidence((public.citation_id,))
    calls: list[str] = []

    async def model_stream(messages, info):
        del messages, info
        if not calls:
            calls.append("search")
            yield {
                0: DeltaToolCall(
                    name="search_research_materials",
                    json_args='{"query":"照护","limit":3}',
                    tool_call_id="call-search-material-with-public",
                )
            }
        elif calls == ["search"]:
            calls.append("read")
            yield {
                0: DeltaToolCall(
                    name="read_research_material_context",
                    json_args=(
                        '{"material_id":"'
                        f"{MATERIAL_ID}"
                        '","segment_id":"'
                        f"{materials.block.segment_id}"
                        '"}'
                    ),
                    tool_call_id="call-read-material-with-public",
                )
            }
        else:
            yield "结合公共知识与个人材料回答。"

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    with runner._agent.override(model=FunctionModel(stream_function=model_stream)):
        result = runner.run_stream(
            prompt="请结合公共知识和我的访谈材料解释照护变化",
            conversation=(),
            tools=tools,
            on_delta=lambda _delta: None,
        )

    assert {citation.source_kind for citation in result.citations} == {
        None,
        "personal_material",
    }
    assert public.citation_id in tools.selected_evidence_ids


def test_cross_source_tool_results_keep_public_and_personal_evidence_together():
    public = AgentEvidence(
        citation_id="retrieval:public-1",
        label="公共知识",
        kind="entry",
        excerpt="公共材料证据",
    )
    personal = AgentEvidence(
        citation_id="material:private-1:segment-1",
        label="我的访谈",
        kind="research_material",
        excerpt="个人材料证据",
        source_kind="personal_material",
        material_id=str(MATERIAL_ID),
        parse_id=str(PARSE_ID),
        segment_id="segment-1",
        locator={"paragraph": 1},
    )
    tools = KnowledgeToolRegistry(catalog=_Catalog(), retriever=None)
    tools.evidence.update({public.citation_id: public, personal.citation_id: personal})
    tools.select_evidence((public.citation_id,))

    _select_result_evidence(tools, [{"citation_id": personal.citation_id}])

    assert tools.selected_evidence_ids == (public.citation_id, personal.citation_id)


def test_repeated_personal_context_read_keeps_public_evidence_selected():
    public = AgentEvidence(
        citation_id="retrieval:public-2",
        label="公共知识",
        kind="entry",
        excerpt="公共材料证据",
    )
    first_personal = AgentEvidence(
        citation_id="material:private-2:segment-1",
        label="我的访谈",
        kind="research_material",
        excerpt="第一段个人材料",
        source_kind="personal_material",
    )
    second_personal = AgentEvidence(
        citation_id="material:private-2:segment-2",
        label="我的访谈",
        kind="research_material",
        excerpt="上下文中的第二段个人材料",
        source_kind="personal_material",
    )
    tools = KnowledgeToolRegistry(catalog=_Catalog(), retriever=None)
    tools.evidence.update(
        {
            public.citation_id: public,
            first_personal.citation_id: first_personal,
            second_personal.citation_id: second_personal,
        }
    )
    tools.select_evidence((public.citation_id, first_personal.citation_id))

    _select_result_evidence(tools, [{"citation_id": second_personal.citation_id}])

    assert tools.selected_evidence_ids == (public.citation_id, second_personal.citation_id)


def test_lexical_material_fallback_is_stable_when_scores_tie():
    registry = _registry(_Materials(), SimpleNamespace())
    chunks = tuple(
        RetrievalChunk(
            chunk_id=f"material-segment:{index}",
            document_kind="research_material",
            knowledge_id=None,
            theory_id=None,
            content_version=1,
            content_hash="b" * 64,
            title="访谈",
            text="共同的照护叙述",
            source_ids=(f"material-segment:{index}",),
        )
        for index in (1, 2)
    )

    result = registry._search_material_chunks(
        query="照护",
        chunks=chunks,
        limit=2,
        task_id=TASK_ID,
    )

    assert [hit.chunk.chunk_id for hit in result.hits] == [
        "material-segment:1",
        "material-segment:2",
    ]


def test_deterministic_trace_keeps_public_and_personal_tool_outputs_distinct():
    public = AgentEvidence(
        citation_id="retrieval:public-1",
        label="公共知识",
        kind="entry",
        excerpt="公共材料证据",
    )
    personal = AgentEvidence(
        citation_id="material:private-1:segment-1",
        label="我的访谈",
        kind="research_material",
        excerpt="个人材料证据",
        source_kind="personal_material",
    )

    class _MixedTools:
        release = SimpleNamespace(knowledge_release_id="release-1")
        research_map_enabled = False
        research_document_tools_enabled = False
        research_material_tools_enabled = True

        def __init__(self):
            self.evidence = {
                public.citation_id: public,
                personal.citation_id: personal,
            }
            self.selected_evidence_ids = ()

        def select_evidence(self, citation_ids):
            self.selected_evidence_ids = tuple(citation_ids)
            return self.selected_evidence_ids

        def search_knowledge(self, query, *, limit=5):
            del query, limit
            return [{"citation_id": public.citation_id, "title": public.label}]

        def search_research_materials(self, query, *, limit=5):
            del query, limit
            return [
                {
                    "citation_id": personal.citation_id,
                    "title": personal.label,
                    "source_kind": "personal_material",
                }
            ]

    tools = _MixedTools()
    events = []
    result = DeterministicKnowledgeRunner().run_stream(
        prompt="请结合知识库和我的访谈解释照护变化",
        conversation=(),
        tools=tools,
        on_delta=lambda _: None,
        on_tool_event=events.append,
    )

    public_finished = next(
        event
        for event in events
        if event.tool == "search_knowledge" and event.phase == "finished"
    )
    material_finished = next(
        event
        for event in events
        if event.tool == "search_research_materials" and event.phase == "finished"
    )
    assert public_finished.output["items"][0].get("source_kind") != "personal_material"
    assert material_finished.output["items"][0]["source_kind"] == "personal_material"
    assert {citation.citation_id for citation in result.citations} == {
        public.citation_id,
        personal.citation_id,
    }
    assert set(tools.selected_evidence_ids) == {
        public.citation_id,
        personal.citation_id,
    }
