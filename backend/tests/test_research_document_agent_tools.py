from types import SimpleNamespace
from uuid import UUID

from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from sqlalchemy import select

import qunxue_api.adapters.research_agent as agent_adapters
from qunxue_api.adapters.research_agent.pydantic_runner import (
    PydanticAIKnowledgeRunner,
    _prepare_document_tool,
)
from qunxue_api.adapters.sqlite import (
    KnowledgeEntryRevisionRow,
    KnowledgeSourceRow,
    KnowledgeTheoryProfileRow,
)
from qunxue_api.application.disciplinary_agent import DisciplinaryAgentApplication
from qunxue_api.modules.agent_conversation import (
    AgentRunResult,
    ConversationService,
)
from qunxue_api.modules.research_framework import (
    ResearchDocumentProposalService,
    ResearchDocumentSection,
    ResearchDocumentSectionStatus,
    ResearchDocumentService,
)


class MemoryDocuments:
    def __init__(self) -> None:
        self.items = {}

    def add(self, snapshot):
        self.items.setdefault(snapshot.document_id, []).append(snapshot)
        return snapshot

    def latest(self, document_id):
        values = self.items.get(document_id, [])
        return values[-1] if values else None

    def get_version(self, document_id, version):
        return next(
            (item for item in self.items.get(document_id, []) if item.version == version),
            None,
        )

    def list_versions(self, document_id):
        return tuple(reversed(self.items.get(document_id, [])))


class MemoryProposals:
    def __init__(self) -> None:
        self.items = {}

    def add(self, snapshot):
        self.items[snapshot.proposal_id] = snapshot
        return snapshot

    def get(self, proposal_id):
        return self.items.get(proposal_id)

    def save(self, snapshot):
        self.items[snapshot.proposal_id] = snapshot
        return snapshot

    def list_for_document(self, document_id):
        return tuple(item for item in self.items.values() if item.document_id == document_id)

    def list_for_task(self, task_id):
        return tuple(item for item in self.items.values() if item.task_id == task_id)

    def validate_agent_context(self, **_kwargs):
        return True

    def find_revision_for_agent_target(
        self,
        *,
        agent_run_id,
        document_id,
        base_document_version,
        target_section_id,
    ):
        return next(
            (
                item
                for item in self.items.values()
                if item.agent_run_id == agent_run_id
                and item.document_id == document_id
                and item.base_document_version == base_document_version
                and item.target_section_id == target_section_id
            ),
            None,
        )


class Catalog:
    def __init__(self, release_id: str) -> None:
        self.release_id = release_id

    def current_release(self, *, purpose):
        del purpose
        return SimpleNamespace(knowledge_release_id=self.release_id)


class DocumentApplication:
    def __init__(self, documents, user_id: UUID) -> None:
        self.documents = documents
        self.user_id = user_id

    def get(self, *, user_id, document_id, version=None):
        if user_id != self.user_id:
            raise LookupError(document_id)
        return self.documents.get(document_id, version=version)


def section(content: str):
    return ResearchDocumentSection(
        section_id="research_question",
        key="research_question",
        title="研究问题",
        content=content,
        status=ResearchDocumentSectionStatus.REVIEWED,
        evidence_refs=(),
    )


def test_document_tool_creates_a_pending_diff_without_mutating_the_document() -> None:
    user_id = UUID(int=1)
    document_repository = MemoryDocuments()
    documents = ResearchDocumentService(repository=document_repository)
    document = documents.create(
        task_id=UUID(int=2),
        theory_plan_id=UUID(int=3),
        knowledge_release_id="release-a",
        title="理论判断",
        sections=(section("原始问题"),),
    )
    proposal_repository = MemoryProposals()
    proposals = ResearchDocumentProposalService(
        repository=proposal_repository,
        documents=documents,
    )
    registry_type = agent_adapters.ResearchDocumentToolRegistry
    registry = registry_type(
        catalog=Catalog("release-a"),
        documents=DocumentApplication(documents, user_id),
        proposals=proposals,
    )
    registry.bind_agent_context(
        user_id=user_id,
        conversation_id=UUID(int=4),
        agent_run_id=UUID(int=5),
    )

    read = registry.read_research_document(str(document.document_id))
    proposed = registry.propose_document_revision(
        document_id=str(document.document_id),
        expected_version=read["version"],
        section_id="research_question",
        replacement_content="成员流动如何改变社区互助？",
        rationale="收窄问题",
    )

    assert read["knowledge_release_id"] == "release-a"
    assert proposed["status"] == "pending"
    assert proposed["requires_user_approval"] is True
    assert proposed["before"] == "原始问题"
    assert proposed["after"] == "成员流动如何改变社区互助？"
    assert documents.get(document.document_id).version == 1
    assert len(proposal_repository.items) == 1


def test_document_tool_refuses_to_cross_the_pinned_knowledge_release() -> None:
    user_id = UUID(int=1)
    documents = ResearchDocumentService(repository=MemoryDocuments())
    document = documents.create(
        task_id=UUID(int=2),
        theory_plan_id=UUID(int=3),
        knowledge_release_id="release-a",
        title="理论判断",
        sections=(section("原始问题"),),
    )
    proposal_repository = MemoryProposals()
    registry_type = agent_adapters.ResearchDocumentToolRegistry
    registry = registry_type(
        catalog=Catalog("release-b"),
        documents=DocumentApplication(documents, user_id),
        proposals=ResearchDocumentProposalService(
            repository=proposal_repository,
            documents=documents,
        ),
    )
    registry.bind_agent_context(
        user_id=user_id,
        conversation_id=UUID(int=4),
        agent_run_id=UUID(int=5),
    )
    result = registry.propose_document_revision(
        document_id=str(document.document_id),
        expected_version=1,
        section_id="research_question",
        replacement_content="跨版本建议",
        rationale="不应成功",
    )
    assert result["error"] == "knowledge_release_mismatch"
    assert proposal_repository.items == {}


def test_document_tool_creates_a_pending_framework_proposal_with_scoped_context() -> None:
    user_id = UUID(int=1)
    documents = ResearchDocumentService(repository=MemoryDocuments())
    proposal_repository = MemoryProposals()
    registry = agent_adapters.ResearchDocumentToolRegistry(
        catalog=Catalog("release-a"),
        documents=DocumentApplication(documents, user_id),
        proposals=ResearchDocumentProposalService(
            repository=proposal_repository,
            documents=documents,
        ),
    )
    registry.bind_agent_context(
        user_id=user_id,
        conversation_id=UUID(int=4),
        agent_run_id=UUID(int=5),
        task_id=UUID(int=2),
        theory_plan_id=UUID(int=3),
    )
    result = registry.propose_document_creation(
        title="社区互助研究框架",
        sections=[
            {
                "section_id": "research_question",
                "key": "research_question",
                "title": "研究问题",
                "content": "成员流动如何改变社区互助？",
            }
        ],
        rationale="依据已确认理论方案生成草案",
    )
    assert result["status"] == "pending"
    assert result["requires_user_approval"] is True
    assert len(proposal_repository.items) == 1


def test_research_workflow_tools_restore_cross_turn_context_and_gate_writes() -> None:
    user_id = UUID(int=1)
    task_id = UUID(int=2)
    theory_plan_id = UUID(int=3)

    class Workflow:
        def __init__(self) -> None:
            self.confirmed = []

        def restore(self, *, user_id, conversation_id):
            assert user_id == UUID(int=1)
            assert conversation_id == UUID(int=4)
            return {"task_id": task_id, "theory_plan_id": theory_plan_id}

        def create_confirmed_task(self, **payload):
            self.confirmed.append(payload)
            return {"task_id": str(task_id), "status": "phenomenon_confirmed"}

        def get_state(self, **_payload):
            return {"task_id": str(task_id), "theory_plan_id": str(theory_plan_id)}

        def start_matching(self, **_payload):
            return {"match_run_id": str(UUID(int=6)), "candidates": []}

        def save_theory_plan(self, **payload):
            self.confirmed.append(payload)
            return {"theory_plan_id": str(theory_plan_id), "status": "confirmed"}

    workflow = Workflow()
    documents = ResearchDocumentService(repository=MemoryDocuments())
    registry = agent_adapters.ResearchDocumentToolRegistry(
        catalog=Catalog("release-a"),
        documents=DocumentApplication(documents, user_id),
        proposals=ResearchDocumentProposalService(
            repository=MemoryProposals(), documents=documents
        ),
        workflow=workflow,
    )
    registry.bind_agent_context(
        user_id=user_id,
        conversation_id=UUID(int=4),
        agent_run_id=UUID(int=5),
    )
    registry.enable_research_document_tools()

    assert registry.document_prompt_context == {
        "task_id": str(task_id),
        "theory_plan_id": str(theory_plan_id),
        "document_id": None,
        "document_version": None,
        "section_id": None,
    }
    refused = registry.create_confirmed_research_task(
        phenomenon="年轻人的情感性孤独",
        research_intent="解释结构性来源",
        context=None,
        user_confirmed=False,
    )
    assert refused["error"] == "user_confirmation_required"
    created = registry.create_confirmed_research_task(
        phenomenon="年轻人的情感性孤独",
        research_intent="解释结构性来源",
        context=None,
        user_confirmed=True,
    )
    assert created["task_id"] == str(task_id)
    assert workflow.confirmed[-1]["user_confirmed"] is True


def test_agent_application_binds_the_real_persisted_run_to_document_tools() -> None:
    user_id = UUID(int=1)

    class Tools:
        release = SimpleNamespace(knowledge_release_id="release-a")
        evidence = {}

        def __init__(self) -> None:
            self.bound = None

        def bind_agent_context(self, **context) -> None:
            self.bound = context

    tools = Tools()

    class Runner:
        def run(self, *, prompt, conversation, tools):
            del prompt, conversation
            assert tools.bound is not None
            assert tools.bound["user_id"] == user_id
            return AgentRunResult(
                answer="已读取上下文。",
                citations=(),
                release_id="release-a",
                provider="test",
                model="test",
            )

    application = DisciplinaryAgentApplication(
        conversations=ConversationService.in_memory(),
        runner=Runner(),
        tools_factory=lambda: tools,
    )
    execution = application.run_turn(
        user_id=user_id,
        conversation_id=None,
        prompt="审阅文档",
        idempotency_key="bind-document-tools",
    )
    assert tools.bound["conversation_id"] == execution.conversation.conversation_id
    assert tools.bound["agent_run_id"] == execution.run_id


def test_document_tools_are_hidden_from_plain_agent_turns() -> None:
    definition = SimpleNamespace(name="read_research_document")
    disabled = SimpleNamespace(
        deps=SimpleNamespace(
            research_document_tools_enabled=False,
            read_research_document=lambda _: None,
        )
    )
    enabled = SimpleNamespace(
        deps=SimpleNamespace(
            research_document_tools_enabled=True,
            read_research_document=lambda _: None,
        )
    )

    assert _prepare_document_tool(disabled, definition) is None
    assert _prepare_document_tool(enabled, definition) is definition


def test_agent_bootstrap_uses_the_persisted_document_tool_registry(client) -> None:
    registry_type = agent_adapters.ResearchDocumentToolRegistry

    with client.app.state.disciplinary_agent_scope() as application:
        tools = application._tools_factory()

    assert isinstance(tools, registry_type)


def test_agent_research_task_binding_survives_a_new_scope(client) -> None:
    registered = client.post(
        "/api/session/register",
        json={"email": "agent-workflow@example.com", "password": "research-pass-123"},
        headers={"Idempotency-Key": "register-agent-workflow"},
    )
    assert registered.status_code == 201
    user_id = UUID(registered.json()["user"]["user_id"])
    release_id = client.get("/api/knowledge/releases/current").json()["knowledge_release_id"]
    with client.app.state.database.session() as session:
        rows = list(
            session.scalars(
                select(KnowledgeEntryRevisionRow)
                .where(KnowledgeEntryRevisionRow.knowledge_release_id == release_id)
                .order_by(KnowledgeEntryRevisionRow.knowledge_id)
                .limit(3)
            )
        )
        assert len(rows) == 3
        for index, row in enumerate(rows, start=1):
            source_id = f"source:{row.knowledge_id}"
            source = session.get(KnowledgeSourceRow, (release_id, source_id))
            assert source is not None
            source.verification_status = "verified"
            row.review_status = "reviewed"
            row.match_eligible = True
            row.review_record_ids = [f"agent-workflow-review-{index}"]
            session.add(
                KnowledgeTheoryProfileRow(
                    knowledge_release_id=release_id,
                    theory_id=f"agent-workflow-theory-{index}",
                    related_knowledge_ids=[row.knowledge_id],
                    title=f"理论 {index}",
                    core_propositions=[f"命题 {index}"],
                    applicable_phenomena=["社区互动"],
                    analysis_levels=["关系"],
                    prerequisites=["存在互动"],
                    exclusion_signals=["没有互动"],
                    observable_evidence=["互动频率"],
                    competing_or_complementary_theory_ids=[],
                    source_ids=[source_id],
                    content_version=1,
                    review_status="reviewed",
                    match_eligible=True,
                )
            )
    with client.app.state.disciplinary_agent_scope() as application:
        turn = application.run_turn(
            user_id=user_id,
            conversation_id=None,
            prompt="建立关于社区互助的研究",
            idempotency_key="create-agent-research-conversation",
            workspace="research",
        )
        tools = application._tools_factory()
        tools.enable_research_document_tools()
        tools.bind_agent_context(
            user_id=user_id,
            conversation_id=turn.conversation.conversation_id,
            agent_run_id=turn.run_id,
        )
        created = tools.create_confirmed_research_task(
            phenomenon="社区成员流动正在改变邻里互助",
            research_intent="解释互助关系变化的机制",
            context="城市社区",
            user_confirmed=True,
        )
        matched = tools.start_theory_matching()
        decisions = [
            {
                "candidate_id": item["candidate_id"],
                "action": "adopt" if index == 0 else "exclude",
                "reason": "用户确认主理论" if index == 0 else "暂不采用",
                "related_source_ids": item["source_ids"],
            }
            for index, item in enumerate(matched["candidates"])
        ]
        plan = tools.save_confirmed_theory_plan(
            decisions=decisions,
            use_assignments=[
                {
                    "candidate_id": matched["candidates"][0]["candidate_id"],
                    "role_code": "primary",
                    "responsibility": "解释社区流动与互助变化的主要机制",
                }
            ],
            relations=[],
            user_confirmed=True,
        )
        proposal = tools.propose_document_creation(
            title="社区互助研究框架",
            sections=[
                {
                    "section_id": "research_question",
                    "key": "research_question",
                    "title": "研究问题",
                    "content": "社区成员流动如何改变邻里互助？",
                }
            ],
            rationale="依据用户确认的理论方案生成",
        )

    with client.app.state.disciplinary_agent_scope() as application:
        restored = application._tools_factory()
        restored.enable_research_document_tools()
        restored.bind_agent_context(
            user_id=user_id,
            conversation_id=turn.conversation.conversation_id,
            agent_run_id=UUID(int=99),
        )

    assert created["status"] == "phenomenon_confirmed"
    assert matched["status"] == "awaiting_decision"
    assert plan["status"] == "confirmed"
    assert proposal["status"] == "pending"
    assert restored.document_prompt_context["task_id"] == created["task_id"]
    assert restored.document_prompt_context["theory_plan_id"] == plan["theory_plan_id"]


def test_agent_workflow_reports_no_reliable_candidate_before_theory_write(client) -> None:
    registered = client.post(
        "/api/session/register",
        json={"email": "agent-no-candidate@example.com", "password": "research-pass-123"},
        headers={"Idempotency-Key": "register-agent-no-candidate"},
    )
    assert registered.status_code == 201
    user_id = UUID(registered.json()["user"]["user_id"])
    with client.app.state.disciplinary_agent_scope() as application:
        turn = application.run_turn(
            user_id=user_id,
            conversation_id=None,
            prompt="建立一个研究",
            idempotency_key="create-agent-no-candidate-conversation",
            workspace="research",
        )
        tools = application._tools_factory()
        tools.enable_research_document_tools()
        tools.bind_agent_context(
            user_id=user_id,
            conversation_id=turn.conversation.conversation_id,
            agent_run_id=turn.run_id,
        )
        created = tools.create_confirmed_research_task(
            phenomenon="一个没有匹配理论的测试现象",
            research_intent="验证无候选边界",
            context=None,
            user_confirmed=True,
        )
        matched = tools.start_theory_matching()
        result = tools.save_confirmed_theory_plan(
            decisions=[
                {"theory": "preview-only-resource", "action": "adopt", "reason": "用户确认"}
            ],
            use_assignments=[],
            relations=[],
            user_confirmed=True,
        )

    assert created["status"] == "phenomenon_confirmed"
    assert matched["status"] == "no_reliable_candidate"
    assert result["error"] == "no_reliable_candidate"
    assert result["match_run_id"] == matched["match_run_id"]
    assert result["next_action"] == "update_knowledge_release_or_refine_phenomenon"


def test_real_runner_emits_read_and_pending_revision_tool_trace() -> None:
    class Tools:
        release = SimpleNamespace(knowledge_release_id="release-a")
        evidence = {}
        research_document_tools_enabled = True

        def __init__(self) -> None:
            self.calls = []

        def read_research_document(self, document_id):
            self.calls.append("read")
            return {
                "document_id": document_id,
                "version": 2,
                "knowledge_release_id": "release-a",
                "sections": [{"section_id": "research_question", "content": "原文"}],
            }

        def propose_document_revision(self, **payload):
            self.calls.append("propose")
            return {
                "proposal_id": "00000000-0000-0000-0000-000000000099",
                "status": "pending",
                "requires_user_approval": True,
                **payload,
            }

    tools = Tools()

    async def model_stream(messages, info):
        del messages, info
        if not tools.calls:
            yield {
                0: DeltaToolCall(
                    name="read_research_document",
                    json_args='{"document_id":"00000000-0000-0000-0000-000000000010"}',
                    tool_call_id="call-read-document",
                )
            }
        elif tools.calls == ["read"]:
            yield {
                0: DeltaToolCall(
                    name="propose_document_revision",
                    json_args=(
                        '{"document_id":"00000000-0000-0000-0000-000000000010",'
                        '"expected_version":2,"section_id":"research_question",'
                        '"replacement_content":"更谨慎的表述",'
                        '"rationale":"降低因果断言"}'
                    ),
                    tool_call_id="call-propose-revision",
                )
            }
        else:
            yield "已生成待你接受或拒绝的建议；文档尚未修改。"

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    events = []
    with runner._agent.override(model=FunctionModel(stream_function=model_stream)):
        result = runner.run_stream(
            prompt="把选中的研究问题改得更谨慎",
            conversation="",
            tools=tools,
            on_delta=lambda _: None,
            on_tool_event=events.append,
        )
    assert tools.calls == ["read", "propose"]
    assert [(item.tool, item.phase) for item in events] == [
        ("read_research_document", "started"),
        ("read_research_document", "finished"),
        ("propose_document_revision", "started"),
        ("propose_document_revision", "finished"),
    ]
    assert events[-1].output["status"] == "pending"
    assert "尚未修改" in result.answer
