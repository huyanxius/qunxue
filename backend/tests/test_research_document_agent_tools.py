from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from test_pre_reviewed_theory_release import _write_bundle

import qunxue_api.adapters.research_agent as agent_adapters
from qunxue_api.adapters.research_agent.pydantic_runner import (
    PydanticAIKnowledgeRunner,
    _prepare_document_tool,
)
from qunxue_api.application.disciplinary_agent import DisciplinaryAgentApplication
from qunxue_api.modules.agent_conversation import (
    AgentRunResult,
    ConversationService,
)
from qunxue_api.modules.knowledge_catalog import (
    KnowledgeUsePurpose,
    RetrievalPipelineUnavailable,
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

    def list_for_task(self, task_id):
        return tuple(
            values[-1]
            for values in self.items.values()
            if values and values[-1].task_id == task_id
        )


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

    def list_actionable_for_task(self, task_id):
        return tuple(
            item for item in self.list_for_task(task_id) if item.status.value == "pending"
        )

    def find_create_for_theory_plan(self, *, user_id, task_id, theory_plan_id):
        return next(
            (
                item
                for item in self.items.values()
                if item.user_id == user_id
                and item.task_id == task_id
                and item.theory_plan_id == theory_plan_id
                and item.kind.value == "create"
                and item.status.value in {"pending", "accepted"}
            ),
            None,
        )

    def agent_run_status(self, _agent_run_id):
        return "completed"

    def agent_run_model(self, _agent_run_id):
        return "test-provider", "test-model"

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


def _install_pre_reviewed_release(client) -> str:
    catalog = client.app.state.knowledge_catalog
    preview = catalog.current_release(purpose=KnowledgeUsePurpose.BROWSE)
    with TemporaryDirectory(prefix="qunxue-agent-pre-reviewed-") as directory:
        bundle = _write_bundle(
            Path(directory) / "pre-reviewed-theories.json",
            base_release_id=preview.knowledge_release_id,
        )
        return catalog.install_pre_reviewed_bundle(bundle).release.knowledge_release_id


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


def framework_section_payloads():
    sections = (
        ("research_question", "研究问题"),
        ("research_object_and_field", "研究对象与场域"),
        ("theoretical_perspective", "理论视角"),
        ("core_concepts", "核心概念"),
        ("mechanisms", "作用机制"),
        ("questions_or_hypotheses", "研究假设与质性问题"),
        ("methodology", "研究方法"),
        ("sample_and_sources", "样本与资料来源"),
        ("analysis_steps", "分析步骤"),
        ("ethics", "伦理风险"),
        ("limitations", "局限"),
        ("evidence_gaps", "证据缺口"),
    )
    return [
        {
            "section_id": key,
            "key": key,
            "title": title,
            "content": f"{title}的待审阅内容。",
        }
        for key, title in sections
    ]


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
        sections=framework_section_payloads(),
        rationale="依据已确认理论方案生成草案",
    )
    assert result["status"] == "pending"
    assert result["section_count"] == 12
    assert result["requires_user_approval"] is True
    assert len(proposal_repository.items) == 1


def test_document_tool_rejects_an_incomplete_framework_before_user_review() -> None:
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
        title="不完整研究框架",
        sections=[framework_section_payloads()[0]],
        rationale="只生成了一节",
    )

    assert result == {
        "error": "research_document_proposal_invalid",
        "message": (
            "create proposal must include exactly the 12 required framework sections; "
            "missing: analysis_steps, core_concepts, ethics, evidence_gaps, limitations, "
            "mechanisms, methodology, questions_or_hypotheses, research_object_and_field, "
            "sample_and_sources, theoretical_perspective"
        ),
    }
    assert proposal_repository.items == {}


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
    refused = registry.propose_start_research(
        phenomenon="年轻人的情感性孤独",
        research_intent="解释结构性来源",
        context=None,
    )
    assert refused == {
        "error": "research_task_already_bound",
        "task_id": str(task_id),
        "message": "这段对话已经绑定研究任务，请从现有研究继续。",
    }


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


def test_plain_agent_exposes_only_the_research_start_handoff_tool() -> None:
    visible_tools: set[str] = set()

    class Tools:
        release = SimpleNamespace(knowledge_release_id="release-agent")
        evidence = {}
        research_document_tools_enabled = False
        research_map_enabled = False

        def __init__(self) -> None:
            self.research_handoff_tools_enabled = False

        def enable_research_handoff_tools(self) -> None:
            self.research_handoff_tools_enabled = True

        def bind_agent_context(self, **_context) -> None:
            return None

        def propose_start_research(self, **_payload):
            return {"status": "pending_confirmation"}

    tools = Tools()

    async def model_stream(messages, info):
        del messages
        visible_tools.update(tool.name for tool in info.function_tools)
        yield "这个问题已经可以继续形成一项研究。"

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    application = DisciplinaryAgentApplication(
        conversations=ConversationService.in_memory(),
        runner=runner,
        tools_factory=lambda: tools,
    )
    with runner._agent.override(model=FunctionModel(stream_function=model_stream)):
        application.run_turn(
            user_id=UUID(int=1),
            conversation_id=None,
            prompt="我想继续研究社区流动如何改变邻里互助",
            idempotency_key="plain-agent-research-handoff",
            workspace="agent",
            on_delta=lambda _delta: None,
        )

    assert "propose_start_research" in visible_tools
    assert "get_research_workflow_state" not in visible_tools
    assert "start_theory_matching" not in visible_tools
    assert "read_research_document" not in visible_tools
    assert "propose_document_revision" not in visible_tools
    assert "update_research_map" not in visible_tools


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
    _install_pre_reviewed_release(client)
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
            agent_turn_id=turn.turn.turn_id,
        )
        start_proposal = tools.propose_start_research(
            phenomenon="社区成员流动正在改变邻里互助",
            research_intent="解释互助关系变化的机制",
            context="城市社区",
        )
        tools.finalize_agent_turn(source_turn_id=turn.turn.turn_id)

    confirmation = client.post(
        f"/api/agent/research-start-proposals/{start_proposal['proposal_id']}/confirm",
        headers={"Idempotency-Key": "confirm-agent-research-conversation"},
        json={
            "expected_version": start_proposal["version"],
            "phenomenon": start_proposal["phenomenon"],
            "research_intent": start_proposal["research_intent"],
            "context": start_proposal["context"],
        },
    )
    assert confirmation.status_code == 201
    created = confirmation.json()["navigation"]

    with client.app.state.disciplinary_agent_scope() as application:
        tools = application._tools_factory()
        tools.enable_research_document_tools()
        tools.bind_agent_context(
            user_id=user_id,
            conversation_id=turn.conversation.conversation_id,
            agent_run_id=turn.run_id,
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
            sections=framework_section_payloads(),
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

    assert created["current_stage"] == "theory_matching"
    assert matched["status"] == "awaiting_decision"
    assert plan["status"] == "confirmed"
    assert proposal["status"] == "pending"
    assert restored.document_prompt_context["task_id"] == created["task_id"]
    assert restored.document_prompt_context["theory_plan_id"] == plan["theory_plan_id"]


def test_agent_research_turn_fails_closed_without_a_formal_release(plain_client) -> None:
    registered = plain_client.post(
        "/api/session/register",
        json={"email": "agent-no-candidate@example.com", "password": "research-pass-123"},
        headers={"Idempotency-Key": "register-agent-no-candidate"},
    )
    assert registered.status_code == 201
    user_id = UUID(registered.json()["user"]["user_id"])
    with (
        plain_client.app.state.disciplinary_agent_scope() as application,
        pytest.raises(RetrievalPipelineUnavailable, match="final MATCH knowledge release"),
    ):
        application.run_turn(
            user_id=user_id,
            conversation_id=None,
            prompt="建立一个研究",
            idempotency_key="create-agent-no-candidate-conversation",
            workspace="research",
        )


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
            conversation=(),
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
