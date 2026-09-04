import asyncio
import threading
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from pydantic import ValidationError
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from pydantic_ai.models.openai import OpenAIChatModel
from sqlalchemy.exc import IntegrityError

from qunxue_api.adapters.model import (
    InMemoryModelAttemptRecorder,
    ModelEndpoint,
    ModelRouteExecutor,
)
from qunxue_api.adapters.research_agent.catalog_tools import KnowledgeToolRegistry
from qunxue_api.adapters.research_agent.pydantic_runner import (
    DeterministicKnowledgeRunner,
    PydanticAIKnowledgeRunner,
    _append_result_evidence,
    _select_result_evidence,
    _text_result,
)
from qunxue_api.adapters.sqlite.agent_conversation_model import AgentRunRow
from qunxue_api.adapters.sqlite.agent_conversation_repository import SqliteConversationRepository
from qunxue_api.adapters.sqlite.research_document_proposal import (
    SqliteResearchDocumentProposalRepository,
)
from qunxue_api.api.contracts.agent import AgentTurnRequest
from qunxue_api.api.routes.agent import (
    _cancel_active_run,
    _effective_agent_runtime_mode,
    _register_active_run,
    _release_active_run,
)
from qunxue_api.application.disciplinary_agent import DisciplinaryAgentApplication
from qunxue_api.bootstrap import create_app
from qunxue_api.modules.agent_conversation import (
    AgentCitation,
    AgentEvidence,
    AgentInterrupted,
    AgentRun,
    AgentRunResult,
    AgentToolEvent,
    AgentTurn,
    ConversationNotFound,
    ConversationService,
    IdempotentTurn,
    RunAlreadyActive,
)
from qunxue_api.modules.agent_conversation import domain as agent_domain
from qunxue_api.settings import Settings


def _agent_endpoints(
    *,
    primary_model: str = "primary-model",
    fallback_model: str = "backup-model",
    fallback_base_url: str = "https://backup.example.test/v1",
) -> tuple[ModelEndpoint, ...]:
    return (
        ModelEndpoint(
            endpoint_id="primary",
            base_url="https://primary.example.test/v1",
            api_key="primary-key",
            model=primary_model,
            timeout_seconds=30,
            provider="openai-compatible",
        ),
        ModelEndpoint(
            endpoint_id="fallback-1",
            base_url=fallback_base_url,
            api_key="backup-key",
            model=fallback_model,
            timeout_seconds=30,
            provider="openai-compatible",
        ),
    )


def _agent_route_executor(
    *,
    base_url: str,
    model: str,
    api_key: str | None,
    fallback_endpoints: tuple[
        tuple[str, str] | tuple[str, str, str], ...
    ] = (),
) -> ModelRouteExecutor:
    endpoints = [
        ModelEndpoint(
            endpoint_id="primary",
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=30,
            provider="openai-compatible",
        )
    ]
    for index, fallback in enumerate(fallback_endpoints, start=1):
        endpoint_url, endpoint_key = fallback[:2]
        endpoint_model = fallback[2] if len(fallback) == 3 else model
        endpoints.append(
            ModelEndpoint(
                endpoint_id=f"fallback-{index}",
                base_url=endpoint_url,
                api_key=endpoint_key,
                model=endpoint_model,
                timeout_seconds=30,
                provider="openai-compatible",
            )
        )
    return ModelRouteExecutor(endpoints=tuple(endpoints))


def test_agent_runtime_mode_honors_api_key_override_without_using_legacy_gateway() -> None:
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=Settings(
                    _env_file=None,
                    runtime_mode="mock",
                    model_api_key="configured-key",
                )
            )
        )
    )

    assert _effective_agent_runtime_mode(request) == "base"


def test_agent_turn_request_limits_material_attachments_to_twenty() -> None:
    with pytest.raises(ValidationError):
        AgentTurnRequest(
            message="比较这些材料",
            workspace="research",
            task_id=UUID(int=99),
            material_ids=tuple(UUID(int=index + 1) for index in range(21)),
        )


def test_agent_runtime_mode_treats_blank_api_key_as_unconfigured() -> None:
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=Settings(
                    _env_file=None,
                    runtime_mode="mock",
                    model_api_key="   ",
                )
            )
        )
    )

    assert _effective_agent_runtime_mode(request) == "mock"


def test_starting_another_conversation_does_not_cancel_the_current_run() -> None:
    user_id = UUID("00000000-0000-0000-0000-000000000001")
    first_cancel = threading.Event()
    second_cancel = threading.Event()

    first_run_id = UUID("00000000-0000-0000-0000-000000000011")
    second_run_id = UUID("00000000-0000-0000-0000-000000000012")
    _register_active_run(user_id, first_run_id, first_cancel)
    _register_active_run(user_id, second_run_id, second_cancel)
    try:
        assert first_cancel.is_set() is False
        assert second_cancel.is_set() is False
        assert _cancel_active_run(user_id, first_run_id) is True
        assert first_cancel.is_set() is True
        assert second_cancel.is_set() is False
    finally:
        _release_active_run(user_id, first_run_id, first_cancel)
        _release_active_run(user_id, second_run_id, second_cancel)


class _FakeAgentTools:
    release = SimpleNamespace(knowledge_release_id="release-a")
    evidence = {}


def test_knowledge_tool_registry_exposes_only_read_only_agent_route_context() -> None:
    class _Catalog:
        @staticmethod
        def current_release(*, purpose):
            del purpose
            return SimpleNamespace(knowledge_release_id="release-a")

    registry = KnowledgeToolRegistry(_Catalog())
    registry._user_id = UUID(int=51)
    registry._task_id = UUID(int=52)
    registry._agent_run_id = UUID(int=53)
    registry._conversation_id = UUID(int=54)
    registry._agent_turn_id = UUID(int=55)

    context = registry.agent_route_context()

    assert dict(context) == {
        "user_id": UUID(int=51),
        "task_id": UUID(int=52),
        "agent_run_id": UUID(int=53),
    }
    with pytest.raises(TypeError):
        context["task_id"] = UUID(int=99)


def test_application_only_enables_web_tools_for_an_opted_in_turn() -> None:
    created_tools: list[object] = []

    class _WebAwareTools:
        release = SimpleNamespace(knowledge_release_id="release-a")

        def __init__(self) -> None:
            self.evidence = {}
            self.web_search_enabled = False
            created_tools.append(self)

        def enable_web_search(self) -> None:
            self.web_search_enabled = True

    class _WebAwareRunner(_CountingRunner):
        def run(self, *, prompt, conversation, tools) -> AgentRunResult:
            assert tools.web_search_enabled is True
            return super().run(prompt=prompt, conversation=conversation, tools=tools)

    application = DisciplinaryAgentApplication(
        conversations=ConversationService.in_memory(),
        runner=_WebAwareRunner(),
        tools_factory=_WebAwareTools,
    )

    application.run_turn(
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        conversation_id=None,
        prompt="查找最新政策",
        idempotency_key="web-search-enabled",
        web_search=True,
    )

    assert len(created_tools) == 1
    assert created_tools[0].web_search_enabled is True


class _CountingRunner:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, *, prompt, conversation, tools) -> AgentRunResult:
        del prompt, conversation, tools
        self.calls += 1
        return AgentRunResult(
            answer=f"answer-{self.calls}",
            citations=(),
            release_id="release-a",
            provider="fake",
            model="fake",
        )


class _UsageRunner(_CountingRunner):
    def run(self, *, prompt, conversation, tools) -> AgentRunResult:
        result = super().run(prompt=prompt, conversation=conversation, tools=tools)
        return AgentRunResult(
            answer=result.answer,
            citations=result.citations,
            release_id=result.release_id,
            provider="pydantic-ai",
            model="deepseek-v4-flash",
            input_tokens=600,
            output_tokens=800,
        )


class _RecordingCredits:
    def __init__(self) -> None:
        self.charges: list[dict[str, object]] = []

    def ensure_can_start(self, *, user_id: UUID) -> None:
        del user_id

    def reserve(self, *, user_id: UUID, run_id: UUID) -> None:
        del user_id, run_id

    def release(self, *, user_id: UUID, run_id: UUID) -> None:
        del user_id, run_id

    def charge(self, **usage) -> None:
        self.charges.append(usage)


class _PreReturnIdentityProbeRunner:
    def __init__(self, *, delegate, provider: str, model: str, probe) -> None:
        self._delegate = delegate
        self.runtime_identity = SimpleNamespace(provider=provider, model=model)
        self._probe = probe

    def run(self, *, prompt, conversation, tools) -> AgentRunResult:
        self._probe()
        return self._delegate.run(
            prompt=prompt,
            conversation=conversation,
            tools=tools,
        )


class _FailOnceRunner(_CountingRunner):
    def run(self, *, prompt, conversation, tools) -> AgentRunResult:
        if self.calls == 0:
            self.calls += 1
            raise RuntimeError("temporary runner failure")
        return super().run(prompt=prompt, conversation=conversation, tools=tools)


class _AlwaysFailingRunner:
    def run(self, *, prompt, conversation, tools) -> AgentRunResult:
        del prompt, conversation, tools
        raise RuntimeError("temporary runner failure")


class _ForgedCitationRunner:
    def run(self, *, prompt, conversation, tools) -> AgentRunResult:
        del prompt, conversation, tools
        return AgentRunResult(
            answer="这条回答伪造了一个知识库引用。",
            citations=(
                AgentEvidence(
                    citation_id="knowledge:forged",
                    label="伪造条目",
                    kind="entry",
                    excerpt="不属于本轮工具证据。",
                    knowledge_id="forged",
                ),
            ),
            release_id="release-a",
            provider="fake",
            model="fake",
        )


class _TracingSuccessRunner:
    def run_stream(
        self,
        *,
        prompt,
        conversation,
        tools,
        on_delta,
        on_tool_event=None,
    ) -> AgentRunResult:
        del conversation
        if on_tool_event is not None:
            on_tool_event(
                AgentToolEvent(
                    tool="search_knowledge",
                    phase="started",
                    call_id="call-search-success",
                    input={"query": prompt},
                    detail="正在检索知识库",
                )
            )
            on_tool_event(
                AgentToolEvent(
                    tool="search_knowledge",
                    phase="finished",
                    call_id="call-search-success",
                    input={"query": prompt},
                    output={"result_count": 1},
                    detail="找到 1 条可引用证据",
                )
            )
        answer = "我先从知识库中找到一条可引用证据来解释。"
        on_delta(answer)
        return AgentRunResult(
            answer=answer,
            citations=(),
            release_id=tools.release.knowledge_release_id,
            provider="fake",
            model="fake",
        )


class _TracingFailureRunner:
    def run_stream(
        self,
        *,
        prompt,
        conversation,
        tools,
        on_delta,
        on_tool_event=None,
    ) -> AgentRunResult:
        del conversation, on_delta
        if on_tool_event is not None:
            on_tool_event(
                AgentToolEvent(
                    tool="search_knowledge",
                    phase="started",
                    call_id="call-search-failed",
                    input={"query": prompt},
                    detail="正在检索知识库",
                )
            )
            on_tool_event(
                AgentToolEvent(
                    tool="search_knowledge",
                    phase="failed",
                    call_id="call-search-failed",
                    input={"query": prompt},
                    detail="知识库检索暂时失败",
                    error="knowledge_search_failed",
                )
            )
        raise RuntimeError("temporary runner failure")


def test_conversation_service_keeps_turns_owned_and_idempotent() -> None:
    service = ConversationService.in_memory()
    user_id = UUID("00000000-0000-0000-0000-000000000001")

    created = service.create_conversation(user_id=user_id, title="社会互助")
    turn = service.append_turn(
        user_id=user_id,
        conversation_id=created.conversation_id,
        idempotency_key="turn-1",
        user_content="为什么互助减少？",
        assistant_content="知识库中可以先从互惠规范切入。",
        citations=(AgentCitation("knowledge:001", "互惠规范", "entry"),),
    )

    replay = service.append_turn(
        user_id=user_id,
        conversation_id=created.conversation_id,
        idempotency_key="turn-1",
        user_content="为什么互助减少？",
        assistant_content="不应重复写入。",
        citations=(),
    )

    assert isinstance(replay, IdempotentTurn)
    assert replay.turn_id == turn.turn_id
    assert (
        len(
            service.get_conversation(
                user_id=user_id,
                conversation_id=created.conversation_id,
            ).turns
        )
        == 1
    )

    with pytest.raises(ConversationNotFound):
        service.get_conversation(
            user_id=UUID("00000000-0000-0000-0000-000000000002"),
            conversation_id=created.conversation_id,
        )


def test_agent_turn_rejects_citations_outside_current_evidence() -> None:
    with pytest.raises(ValueError, match="citation"):
        AgentTurn.create(
            user_content="问题",
            assistant_content="回答",
            citations=(AgentCitation("knowledge:missing", "未知", "entry"),),
            evidence_ids=frozenset({"knowledge:present"}),
        )


def test_successful_real_agent_turn_charges_actual_provider_tokens_once() -> None:
    credits = _RecordingCredits()
    application = DisciplinaryAgentApplication(
        conversations=ConversationService.in_memory(),
        runner=_UsageRunner(),
        tools_factory=_FakeAgentTools,
        credits=credits,
    )
    user_id = UUID("00000000-0000-0000-0000-000000000001")

    completed = application.run_turn(
        user_id=user_id,
        conversation_id=None,
        prompt="解释社会联结",
        idempotency_key="usage-turn",
    )
    application.run_turn(
        user_id=user_id,
        conversation_id=completed.conversation.conversation_id,
        prompt="解释社会联结",
        idempotency_key="usage-turn",
    )

    assert credits.charges == [
        {
            "user_id": user_id,
            "run_id": completed.run_id,
            "input_tokens": 600,
            "output_tokens": 800,
            "model": "deepseek-v4-flash",
        }
    ]


def test_application_rejects_runner_citations_outside_tool_evidence() -> None:
    application = DisciplinaryAgentApplication(
        conversations=ConversationService.in_memory(),
        runner=_ForgedCitationRunner(),
        tools_factory=_FakeAgentTools,
    )

    with pytest.raises(ValueError, match="citation"):
        application.run_turn(
            user_id=UUID("00000000-0000-0000-0000-000000000001"),
            conversation_id=None,
            prompt="给出一个引用",
            idempotency_key="forged-citation",
        )


def test_agent_idempotency_replays_its_own_turn_after_later_turns() -> None:
    runner = _CountingRunner()
    application = DisciplinaryAgentApplication(
        conversations=ConversationService.in_memory(),
        runner=runner,
        tools_factory=_FakeAgentTools,
    )
    user_id = UUID("00000000-0000-0000-0000-000000000001")

    first = application.run_turn(
        user_id=user_id,
        conversation_id=None,
        prompt="第一问",
        idempotency_key="key-1",
    )
    second = application.run_turn(
        user_id=user_id,
        conversation_id=first.conversation.conversation_id,
        prompt="第二问",
        idempotency_key="key-2",
    )
    replay = application.run_turn(
        user_id=user_id,
        conversation_id=second.conversation.conversation_id,
        prompt="第一问",
        idempotency_key="key-1",
    )

    assert replay.replayed is True
    assert replay.result.answer == "answer-1"
    assert replay.turn is not None
    assert replay.turn.turn_id == first.turn.turn_id
    assert (replay.result.provider, replay.result.model) == ("fake", "fake")
    assert runner.calls == 2


def test_agent_failed_idempotency_key_can_retry_without_replaying_another_turn() -> None:
    runner = _FailOnceRunner()
    application = DisciplinaryAgentApplication(
        conversations=ConversationService.in_memory(),
        runner=runner,
        tools_factory=_FakeAgentTools,
    )
    user_id = UUID("00000000-0000-0000-0000-000000000001")

    with pytest.raises(RuntimeError, match="temporary runner failure"):
        application.run_turn(
            user_id=user_id,
            conversation_id=None,
            prompt="可重试的问题",
            idempotency_key="retry-key",
        )

    retried = application.run_turn(
        user_id=user_id,
        conversation_id=None,
        prompt="可重试的问题",
        idempotency_key="retry-key",
    )

    assert retried.replayed is False
    assert retried.result.answer == "answer-2"


def test_interrupted_run_is_not_persisted_as_a_completed_turn() -> None:
    runner = _CountingRunner()
    application = DisciplinaryAgentApplication(
        conversations=ConversationService.in_memory(),
        runner=runner,
        tools_factory=_FakeAgentTools,
    )
    user_id = UUID("00000000-0000-0000-0000-000000000001")

    with pytest.raises(AgentInterrupted):
        application.run_turn(
            user_id=user_id,
            conversation_id=None,
            prompt="在回答完成前停止",
            idempotency_key="interrupt-key",
            is_cancelled=lambda: True,
        )

    run = application._conversations.find_run(user_id=user_id, idempotency_key="interrupt-key")
    assert run is not None
    assert run.status == "interrupted"
    conversation = application.list_conversations(user_id=user_id)
    assert len(conversation) == 1
    assert conversation[0].turns == ()


def test_sqlite_failed_key_reset_does_not_bypass_a_concurrent_active_run() -> None:
    conversation_id = UUID("00000000-0000-0000-0000-000000000012")
    user_id = UUID("00000000-0000-0000-0000-000000000013")
    failed = AgentRunRow(
        run_id="00000000-0000-0000-0000-000000000014",
        conversation_id=str(conversation_id),
        user_id=str(user_id),
        idempotency_key="retry-key",
        status="failed",
        provider="pydantic-ai",
        model="knowledge-agent",
        knowledge_release_id="release-a",
        usage={},
        tool_summary=[],
        started_at=datetime.now(UTC),
    )
    active = AgentRunRow(
        run_id="00000000-0000-0000-0000-000000000015",
        conversation_id=str(conversation_id),
        user_id=str(user_id),
        idempotency_key="other-key",
        status="running",
        provider="pydantic-ai",
        model="knowledge-agent",
        knowledge_release_id="release-a",
        usage={},
        tool_summary=[],
        started_at=datetime.now(UTC),
    )
    session = Mock()
    session.scalar.side_effect = [failed, None, active]
    session.flush.side_effect = IntegrityError("update", {}, RuntimeError("race"))
    repository = SqliteConversationRepository(session)
    run = AgentRun(
        run_id=UUID("00000000-0000-0000-0000-000000000016"),
        conversation_id=conversation_id,
        user_id=user_id,
        idempotency_key="retry-key",
        status="running",
        knowledge_release_id="release-a",
    )

    with pytest.raises(RunAlreadyActive):
        repository.start_run(run)


def test_sqlite_failed_key_retry_refreshes_pre_run_identity() -> None:
    conversation_id = UUID("00000000-0000-0000-0000-000000000017")
    user_id = UUID("00000000-0000-0000-0000-000000000018")
    failed = AgentRunRow(
        run_id="00000000-0000-0000-0000-000000000019",
        conversation_id=str(conversation_id),
        user_id=str(user_id),
        idempotency_key="retry-identity-key",
        status="failed",
        provider="pydantic-ai",
        model="knowledge-agent",
        knowledge_release_id="release-old",
        usage={},
        tool_summary=[],
        started_at=datetime.now(UTC),
    )
    session = Mock()
    session.scalar.side_effect = [failed, None]
    repository = SqliteConversationRepository(session)

    retried = repository.start_run(
        AgentRun(
            run_id=UUID("00000000-0000-0000-0000-000000000020"),
            conversation_id=conversation_id,
            user_id=user_id,
            idempotency_key="retry-identity-key",
            status="running",
            provider="deterministic-knowledge",
            model="local",
            knowledge_release_id="release-new",
        )
    )

    assert retried.run_id == UUID(failed.run_id)
    assert (failed.provider, failed.model) == ("deterministic-knowledge", "local")
    assert failed.knowledge_release_id == "release-new"


def test_sqlite_agent_run_persists_and_restores_material_attachment_snapshots() -> None:
    conversation_id = UUID("00000000-0000-0000-0000-000000000081")
    user_id = UUID("00000000-0000-0000-0000-000000000082")
    attachment = agent_domain.AgentMaterialAttachment(
        material_id=UUID("00000000-0000-0000-0000-000000000083"),
        parse_id=UUID("00000000-0000-0000-0000-000000000084"),
    )
    session = Mock()
    session.scalar.side_effect = [None, None]
    repository = SqliteConversationRepository(session)
    run = AgentRun(
        run_id=UUID("00000000-0000-0000-0000-000000000085"),
        conversation_id=conversation_id,
        user_id=user_id,
        idempotency_key="material-attachments",
        status="running",
        knowledge_release_id="release-a",
        material_attachments=(attachment,),
    )

    repository.start_run(run)

    stored = session.add.call_args.args[0]
    assert stored.material_attachments == [
        {
            "material_id": str(attachment.material_id),
            "parse_id": str(attachment.parse_id),
        }
    ]
    session.scalar.side_effect = [stored]
    restored = repository.find_run(user_id=user_id, idempotency_key="material-attachments")
    assert restored is not None
    assert restored.material_attachments == (attachment,)


def test_sqlite_insert_race_does_not_return_the_other_running_run() -> None:
    conversation_id = UUID("00000000-0000-0000-0000-000000000022")
    user_id = UUID("00000000-0000-0000-0000-000000000023")
    raced = AgentRunRow(
        run_id="00000000-0000-0000-0000-000000000024",
        conversation_id=str(conversation_id),
        user_id=str(user_id),
        idempotency_key="other-key",
        status="running",
        provider="pydantic-ai",
        model="knowledge-agent",
        knowledge_release_id="release-a",
        usage={},
        tool_summary=[],
        started_at=datetime.now(UTC),
    )
    session = Mock()
    session.scalar.side_effect = [None, None, raced]
    session.flush.side_effect = IntegrityError("insert", {}, RuntimeError("race"))
    repository = SqliteConversationRepository(session)
    run = AgentRun(
        run_id=UUID("00000000-0000-0000-0000-000000000025"),
        conversation_id=conversation_id,
        user_id=user_id,
        idempotency_key="new-key",
        status="running",
        knowledge_release_id="release-a",
    )

    with pytest.raises(RunAlreadyActive):
        repository.start_run(run)


def test_sqlite_finish_run_persists_tool_summary() -> None:
    conversation_id = UUID("00000000-0000-0000-0000-000000000032")
    run_id = UUID("00000000-0000-0000-0000-000000000033")
    row = AgentRunRow(
        run_id=str(run_id),
        conversation_id=str(conversation_id),
        user_id="00000000-0000-0000-0000-000000000034",
        idempotency_key="summary-key",
        status="running",
        provider="pydantic-ai",
        model="knowledge-agent",
        knowledge_release_id="release-a",
        usage={},
        tool_summary=[],
        started_at=datetime.now(UTC),
    )
    session = Mock()
    session.get.return_value = row
    repository = SqliteConversationRepository(session)
    tool_summary = [
        {
            "tool": "search_knowledge",
            "phase": "finished",
            "call_id": "call-search",
            "input": {"query": "青年孤独"},
            "output": {"result_count": 1},
            "detail": "找到 1 条可引用证据",
        }
    ]

    repository.finish_run(
        run_id=run_id,
        status="completed",
        tool_summary=tool_summary,
        turn_id=UUID("00000000-0000-0000-0000-000000000035"),
    )

    assert row.status == "completed"
    assert row.tool_summary == tool_summary
    assert row.turn_id == str(UUID("00000000-0000-0000-0000-000000000035"))
    assert row.completed_at is not None


def test_agent_api_streams_and_persists_a_knowledge_turn(client) -> None:
    registered = client.post(
        "/api/session/register",
        json={"email": "agent@example.com", "password": "password-123", "display_name": "学生"},
        headers={"Idempotency-Key": "register-agent"},
    )
    assert registered.status_code == 201

    response = client.post(
        "/api/agent/turns",
        json={"message": "请检索知识库，解释什么是历史唯物主义？"},
        headers={"Idempotency-Key": "agent-turn-1"},
    )
    assert response.status_code == 200
    assert "event: turn_started" in response.text
    assert "event: tool_started" in response.text
    assert "event: tool_finished" in response.text
    assert "event: assistant_delta" in response.text
    assert "event: turn_completed" in response.text

    replay = client.post(
        "/api/agent/turns",
        json={"message": "请检索知识库，解释什么是历史唯物主义？"},
        headers={"Idempotency-Key": "agent-turn-1"},
    )
    assert replay.status_code == 200
    assert '"replayed": true' in replay.text

    conversations = client.get("/api/agent/conversations")
    assert conversations.status_code == 200
    conversation_id = conversations.json()["items"][0]["conversation_id"]
    detail = client.get(f"/api/agent/conversations/{conversation_id}")
    assert detail.status_code == 200
    assert detail.json()["turn_count"] == 1
    assert detail.json()["turns"][0]["knowledge_release_id"]
    traces = detail.json()["turns"][0]["tool_traces"]
    assert len(traces) == 2
    assert traces[0] == {
        "tool": "search_knowledge",
        "phase": "started",
        "call_id": "deterministic:search_knowledge",
        "input": {"query": "请检索知识库，解释什么是历史唯物主义？"},
        "output": None,
        "detail": "正在检索知识库",
        "error": None,
    }
    finished_trace = traces[1]
    assert finished_trace["phase"] == "finished"
    assert finished_trace["output"]["result_count"] == 1
    item = finished_trace["output"]["items"][0]
    assert item["knowledge_id"] == "D1:C001"
    assert item["title"] == "历史唯物主义"
    assert item["excerpt"]
    assert "历史唯物主义" in finished_trace["detail"]
    with client.app.state.database.session() as session:
        run = session.query(AgentRunRow).filter_by(idempotency_key="agent-turn-1").one()
        assert run.status == "completed"
        assert detail.json()["turns"][0]["knowledge_release_id"] == run.knowledge_release_id
        assert len(run.tool_summary) == 2
        assert run.tool_summary[0]["phase"] == "started"
        assert run.tool_summary[1]["phase"] == "finished"
        assert run.tool_summary[1]["output"]["result_count"] == 1
        assert run.tool_summary[1]["output"]["items"][0]["knowledge_id"] == "D1:C001"


def test_agent_conversation_detail_returns_stable_not_found_error(client) -> None:
    registered = client.post(
        "/api/session/register",
        json={
            "email": "agent-not-found@example.com",
            "password": "password-123",
            "display_name": "学生",
        },
        headers={"Idempotency-Key": "register-agent-not-found"},
    )
    assert registered.status_code == 201

    response = client.get("/api/agent/conversations/00000000-0000-0000-0000-000000000099")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert response.json()["error"]["message"] == "对话不存在或无权访问。"


def test_agent_conversation_can_be_renamed_and_deleted(client) -> None:
    registered = client.post(
        "/api/session/register",
        json={
            "email": "agent-manage@example.com",
            "password": "password-123",
            "display_name": "学生",
        },
        headers={"Idempotency-Key": "register-agent-manage"},
    )
    assert registered.status_code == 201
    user_id = UUID(registered.json()["user"]["user_id"])
    with client.app.state.database.session() as session:
        conversation = ConversationService(
            SqliteConversationRepository(session)
        ).create_conversation(user_id=user_id, title="青年为什么推迟进入婚姻？")
        conversation_id = conversation.conversation_id

    renamed = client.patch(
        f"/api/agent/conversations/{conversation_id}",
        json={"title": "  青年婚姻研究  "},
        headers={"Idempotency-Key": "rename-agent-conversation"},
    )

    assert renamed.status_code == 200
    assert renamed.json()["title"] == "青年婚姻研究"
    assert client.get("/api/agent/conversations").json()["items"][0]["title"] == "青年婚姻研究"

    deleted = client.delete(
        f"/api/agent/conversations/{conversation_id}",
        headers={"Idempotency-Key": "delete-agent-conversation"},
    )

    assert deleted.status_code == 204
    assert client.get(f"/api/agent/conversations/{conversation_id}").status_code == 404


def test_agent_turn_contract_declares_server_sent_events(client) -> None:
    response = client.app.openapi()["paths"]["/api/agent/turns"]["post"]["responses"]["200"]

    assert response["content"]["text/event-stream"]["schema"] == {"type": "string"}


def test_agent_api_persists_failed_run_for_retry(client, monkeypatch: pytest.MonkeyPatch) -> None:
    registered = client.post(
        "/api/session/register",
        json={
            "email": "agent-failure@example.com",
            "password": "password-123",
            "display_name": "学生",
        },
        headers={"Idempotency-Key": "register-agent-failure"},
    )
    assert registered.status_code == 201

    monkeypatch.setattr(
        "qunxue_api.bootstrap.DeterministicKnowledgeRunner",
        _TracingFailureRunner,
    )
    response = client.post(
        "/api/agent/turns",
        json={"message": "会失败的问题"},
        headers={"Idempotency-Key": "agent-failure-1"},
    )

    assert response.status_code == 200
    assert '"code": "agent_unavailable"' in response.text
    with client.app.state.database.session() as session:
        failed = session.query(AgentRunRow).one()
        assert failed.status == "failed"
        assert failed.error == "temporary runner failure"
        assert failed.tool_summary == [
            {
                "tool": "search_knowledge",
                "phase": "started",
                "call_id": "call-search-failed",
                "input": {"query": "会失败的问题"},
                "detail": "正在检索知识库",
            },
            {
                "tool": "search_knowledge",
                "phase": "failed",
                "call_id": "call-search-failed",
                "input": {"query": "会失败的问题"},
                "detail": "知识库检索暂时失败",
                "error": "knowledge_search_failed",
            },
        ]


def test_sqlite_application_persists_failed_run_before_outer_rollback(client) -> None:
    registered = client.post(
        "/api/session/register",
        json={
            "email": "agent-sqlite-failure@example.com",
            "password": "password-123",
            "display_name": "学生",
        },
        headers={"Idempotency-Key": "register-agent-sqlite-failure"},
    )
    user_id = UUID(registered.json()["user"]["user_id"])
    try:
        with client.app.state.database.session() as session:
            application = DisciplinaryAgentApplication(
                conversations=ConversationService(SqliteConversationRepository(session)),
                runner=_AlwaysFailingRunner(),
                tools_factory=_FakeAgentTools,
            )
            with pytest.raises(RuntimeError, match="temporary runner failure"):
                application.run_turn(
                    user_id=user_id,
                    conversation_id=None,
                    prompt="需要审计失败的问题",
                    idempotency_key="sqlite-failure-1",
                )
            raise AssertionError("the exception must reach the database scope")
    except AssertionError:
        pass

    with client.app.state.database.session() as session:
        failed = session.query(AgentRunRow).filter_by(idempotency_key="sqlite-failure-1").one()
        assert failed.status == "failed"


def test_sqlite_application_replaces_start_placeholders_with_runner_identity(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registered = client.post(
        "/api/session/register",
        json={
            "email": "agent-provenance@example.com",
            "password": "password-123",
            "display_name": "学生",
        },
        headers={"Idempotency-Key": "register-agent-provenance"},
    )
    user_id = UUID(registered.json()["user"]["user_id"])
    configured_runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    monkeypatch.setattr(
        configured_runner._agent,
        "run_sync",
        lambda *args, **kwargs: SimpleNamespace(output="已配置模型的回答。"),
    )

    observed_before_result: dict[str, tuple[str, str] | None] = {}
    for key, delegate, expected_identity in (
        (
            "provenance-deterministic",
            DeterministicKnowledgeRunner(),
            ("deterministic-knowledge", "local"),
        ),
        (
            "provenance-configured",
            configured_runner,
            ("pydantic-ai", "deepseek-v4-flash"),
        ),
    ):
        with client.app.state.database.session() as session:
            proposal_repository = SqliteResearchDocumentProposalRepository(session)

            def probe(
                *,
                idempotency_key: str = key,
                repository: SqliteResearchDocumentProposalRepository = proposal_repository,
            ) -> None:
                row = session.query(AgentRunRow).filter_by(idempotency_key=idempotency_key).one()
                observed_before_result[idempotency_key] = repository.agent_run_model(
                    UUID(row.run_id)
                )

            runner = _PreReturnIdentityProbeRunner(
                delegate=delegate,
                provider=expected_identity[0],
                model=expected_identity[1],
                probe=probe,
            )
            application = DisciplinaryAgentApplication(
                conversations=ConversationService(SqliteConversationRepository(session)),
                runner=runner,
                tools_factory=_FakeAgentTools,
            )
            application.run_turn(
                user_id=user_id,
                conversation_id=None,
                prompt="解释一个社会学现象",
                idempotency_key=key,
            )

    assert observed_before_result == {
        "provenance-deterministic": ("deterministic-knowledge", "local"),
        "provenance-configured": ("pydantic-ai", "deepseek-v4-flash"),
    }

    with client.app.state.database.session() as session:
        deterministic = (
            session.query(AgentRunRow).filter_by(idempotency_key="provenance-deterministic").one()
        )
        configured = (
            session.query(AgentRunRow).filter_by(idempotency_key="provenance-configured").one()
        )
        assert (deterministic.provider, deterministic.model) == (
            "deterministic-knowledge",
            "local",
        )
        assert (configured.provider, configured.model) == (
            "pydantic-ai",
            "deepseek-v4-flash",
        )
        proposal_repository = SqliteResearchDocumentProposalRepository(session)
        assert proposal_repository.agent_run_model(UUID(deterministic.run_id)) == (
            "deterministic-knowledge",
            "local",
        )
        assert proposal_repository.agent_run_model(UUID(configured.run_id)) == (
            "pydantic-ai",
            "deepseek-v4-flash",
        )


def test_sqlite_application_persists_tool_summary_for_interrupted_run(client) -> None:
    registered = client.post(
        "/api/session/register",
        json={
            "email": "agent-interrupted@example.com",
            "password": "password-123",
            "display_name": "学生",
        },
        headers={"Idempotency-Key": "register-agent-interrupted"},
    )
    user_id = UUID(registered.json()["user"]["user_id"])

    with client.app.state.database.session() as session:
        application = DisciplinaryAgentApplication(
            conversations=ConversationService(SqliteConversationRepository(session)),
            runner=_TracingSuccessRunner(),
            tools_factory=_FakeAgentTools,
        )
        checks = iter([False, True])
        with pytest.raises(AgentInterrupted):
            application.run_turn(
                user_id=user_id,
                conversation_id=None,
                prompt="在回答完成后停止",
                idempotency_key="sqlite-interrupted-1",
                on_delta=lambda _: None,
                is_cancelled=lambda: next(checks),
            )

    with client.app.state.database.session() as session:
        interrupted = (
            session.query(AgentRunRow).filter_by(idempotency_key="sqlite-interrupted-1").one()
        )
        assert interrupted.status == "interrupted"
        assert interrupted.tool_summary == [
            {
                "tool": "search_knowledge",
                "phase": "started",
                "call_id": "call-search-success",
                "input": {"query": "在回答完成后停止"},
                "detail": "正在检索知识库",
            },
            {
                "tool": "search_knowledge",
                "phase": "finished",
                "call_id": "call-search-success",
                "input": {"query": "在回答完成后停止"},
                "output": {"result_count": 1},
                "detail": "找到 1 条可引用证据",
            },
        ]


def test_deepseek_flash_disables_thinking_by_default() -> None:
    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )

    assert runner._agent.model.settings == {
        "timeout": 30,
        "max_tokens": 2400,
        "extra_body": {"thinking": {"type": "disabled"}},
    }
    assert runner._usage_limits.request_limit == 12
    assert runner._usage_limits.tool_calls_limit == 20


def test_agent_builds_independent_settings_without_leaking_deepseek_options_to_fallback() -> None:
    fallback_endpoints = (
        ("https://openai.example.test/v1", "fallback-key", "gpt-5.6-sol"),
    )
    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="primary-key",
        fallback_endpoints=fallback_endpoints,
        model="deepseek-v4-flash",
        timeout_seconds=30,
        route_executor=_agent_route_executor(
            base_url="https://api.deepseek.com",
            api_key="primary-key",
            model="deepseek-v4-flash",
            fallback_endpoints=fallback_endpoints,
        ),
    )

    primary = runner._agent.model
    fallback = primary._endpoint_models["fallback-1"]

    assert primary.settings is not fallback.settings
    assert primary.settings["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "extra_body" not in fallback.settings
    assert fallback.model_name == "gpt-5.6-sol"


def test_agent_applies_deepseek_options_to_a_deepseek_fallback_only() -> None:
    fallback_endpoints = (
        ("https://api.deepseek.com", "fallback-key", "deepseek-v4-flash"),
    )
    runner = PydanticAIKnowledgeRunner(
        base_url="https://openai.example.test/v1",
        api_key="primary-key",
        fallback_endpoints=fallback_endpoints,
        model="gpt-5.6-sol",
        timeout_seconds=30,
        route_executor=_agent_route_executor(
            base_url="https://openai.example.test/v1",
            api_key="primary-key",
            model="gpt-5.6-sol",
            fallback_endpoints=fallback_endpoints,
        ),
    )

    primary = runner._agent.model
    fallback = primary._endpoint_models["fallback-1"]

    assert primary.settings is not fallback.settings
    assert "extra_body" not in primary.settings
    assert fallback.settings["extra_body"] == {"thinking": {"type": "disabled"}}
    assert fallback.model_name == "deepseek-v4-flash"


def test_deep_research_uses_an_emergency_guard_not_the_chat_tool_budget() -> None:
    runner = PydanticAIKnowledgeRunner(
        base_url="https://models.example.test/v1",
        api_key="local-test-key",
        model="sociology-model",
        timeout_seconds=30,
    )

    limits = runner._usage_limits_for(
        type("DeepResearchTools", (), {"deep_research_enabled": True})()
    )

    assert limits.request_limit == 48
    assert limits.tool_calls_limit == 100


def test_agent_runner_forwards_configured_model_headers() -> None:
    runner = PydanticAIKnowledgeRunner(
        base_url="https://models.example.test/v1",
        api_key="local-test-key",
        model="sociology-model",
        timeout_seconds=30,
        extra_headers={"X-LoRA-ID": "local-lora-test-id"},
    )

    assert runner._agent.model.settings["extra_headers"] == {"X-LoRA-ID": "local-lora-test-id"}


def test_agent_runner_forwards_configured_reasoning_effort() -> None:
    runner = PydanticAIKnowledgeRunner(
        base_url="https://models.example.test/v1",
        api_key="local-test-key",
        model="gpt-5.6-luna",
        timeout_seconds=30,
        reasoning_effort="max",
    )

    assert runner._agent.model.settings["openai_reasoning_effort"] == "max"


def test_agent_bootstrap_forwards_configured_reasoning_effort(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _CapturedRunner(_CountingRunner):
        def __init__(self, **kwargs) -> None:
            super().__init__()
            captured.update(kwargs)

    monkeypatch.setattr(
        "qunxue_api.bootstrap.PydanticAIKnowledgeRunner",
        _CapturedRunner,
    )
    settings = Settings(
        _env_file=None,
        database_url=client.app.state.settings.database_url,
        model_base_url="https://models.example.test/v1",
        model_api_key="local-test-key",
        model_name="gpt-5.6-luna",
        model_reasoning_effort="max",
    )
    app = create_app(
        settings=settings,
        database=client.app.state.database,
        knowledge_retriever=client.app.state.knowledge_retriever,
    )

    with app.state.disciplinary_agent_scope():
        pass

    assert captured["reasoning_effort"] == "max"


def test_agent_bootstrap_reuses_shared_router_and_normalized_endpoints(
    client,
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class _CapturedRunner(_CountingRunner):
        def __init__(self, **kwargs) -> None:
            super().__init__()
            captured.update(kwargs)

    monkeypatch.setattr(
        "qunxue_api.bootstrap.PydanticAIKnowledgeRunner",
        _CapturedRunner,
    )
    settings = Settings(
        _env_file=None,
        database_url=client.app.state.settings.database_url,
        runtime_mode="base",
        model_base_url="https://primary.example.test/v1",
        model_api_key="primary-key",
        model_name="primary-model",
        model_fallbacks=[
            {
                "base_url": "https://backup.example.test/v1/",
                "api_key": "backup-key",
                "model": "backup-model",
            }
        ],
    )
    app = create_app(
        settings=settings,
        database=client.app.state.database,
        knowledge_retriever=client.app.state.knowledge_retriever,
    )

    with app.state.disciplinary_agent_scope():
        pass

    assert captured["route_executor"] is app.state.model_router
    assert captured["fallback_endpoints"] == (
        ("https://backup.example.test/v1", "backup-key", "backup-model"),
    )


def test_agent_bootstrap_forwards_extension_and_sft_headers(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _CapturedRunner(_CountingRunner):
        def __init__(self, **kwargs) -> None:
            super().__init__()
            captured.update(kwargs)

    monkeypatch.setattr(
        "qunxue_api.bootstrap.PydanticAIKnowledgeRunner",
        _CapturedRunner,
    )
    settings = Settings(
        _env_file=None,
        database_url=client.app.state.settings.database_url,
        runtime_mode="sft",
        model_base_url="https://models.example.test/v1",
        model_api_key="local-test-key",
        model_name="sociology-model",
        model_extra_headers={"X-Tenant": "local-tenant"},
        model_sft_resource_id="local-lora-test-id",
    )
    app = create_app(
        settings=settings,
        database=client.app.state.database,
        knowledge_retriever=client.app.state.knowledge_retriever,
    )

    with app.state.disciplinary_agent_scope():
        pass

    assert captured["extra_headers"] == {
        "X-Tenant": "local-tenant",
        "X-LoRA-ID": "local-lora-test-id",
    }


def test_agent_answers_sociology_question_without_preemptive_knowledge_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Tools:
        release = SimpleNamespace(knowledge_release_id="release-a")
        evidence = {}

        def search_knowledge(self, query: str):
            raise AssertionError(f"普通学科对话不应在模型判断前强制检索：{query}")

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    monkeypatch.setattr(
        runner._agent,
        "run_sync",
        lambda *args, **kwargs: SimpleNamespace(
            output="可以从社会联结、劳动节奏与城市流动三个层面理解。"
        ),
    )

    result = runner.run_stream(
        prompt="怎么解释年轻人越来越孤独？",
        conversation=(),
        tools=_Tools(),
        on_delta=lambda _: None,
    )

    assert result.answer == "可以从社会联结、劳动节奏与城市流动三个层面理解。"
    assert result.citations == ()


def test_formal_research_turn_reaches_the_model_before_a_search_query_is_chosen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    citation_id = "retrieval:theory-profile:social-capital:v2"

    class _Tools:
        release = SimpleNamespace(knowledge_release_id="release-a")
        research_map_enabled = False

        def __init__(self) -> None:
            self.evidence = {}
            self.selected_evidence_ids: tuple[str, ...] = ()
            self.search_calls: list[str] = []

        def search_knowledge(self, query: str, *, limit: int = 5):
            assert limit == 5
            self.search_calls.append(query)
            self.evidence[citation_id] = AgentEvidence(
                citation_id=citation_id,
                label="社会资本理论",
                kind="theory",
                excerpt="持续关系、信任与互惠规范支持集体行动。",
                knowledge_id="D2:P001",
            )
            return [
                {
                    "citation_id": citation_id,
                    "knowledge_id": "D2:P001",
                    "title": "社会资本理论",
                    "excerpt": "持续关系、信任与互惠规范支持集体行动。",
                    "evidence_status": "verified",
                }
            ]

        def select_evidence(self, citation_ids):
            self.selected_evidence_ids = tuple(citation_ids)
            return self.selected_evidence_ids

    prompt = "我要写本科生毕业论文，帮我想一个选题，我们快速研究。"
    tools = _Tools()
    captured: dict[str, object] = {}
    runner = PydanticAIKnowledgeRunner(
        base_url="https://models.example.test/v1",
        api_key="local-test-key",
        model="sociology-model",
        timeout_seconds=30,
    )

    def run_sync(user_prompt, **kwargs):
        captured["prompt"] = user_prompt
        return SimpleNamespace(output="可以从社区流动与互助关系变化切入。")

    monkeypatch.setattr(runner._agent, "run_sync", run_sync)
    tool_events = []

    result = runner.run_stream(
        prompt=prompt,
        conversation=(),
        tools=tools,
        on_delta=lambda _: None,
        on_tool_event=tool_events.append,
    )

    assert tools.search_calls == []
    assert tools.selected_evidence_ids == ()
    assert captured["prompt"] == prompt
    assert tool_events == []
    assert result.citations == ()


def test_reading_an_unknown_knowledge_id_returns_a_tool_error() -> None:
    class _Catalog:
        def current_release(self, *, purpose):
            del purpose
            return SimpleNamespace(knowledge_release_id="release-a")

        def get_entry(self, *, knowledge_id, release_id):
            del release_id
            raise LookupError(knowledge_id)

    result = KnowledgeToolRegistry(_Catalog()).read_knowledge_entry("directory/path")

    assert result == {
        "error": "knowledge_entry_not_found",
        "knowledge_id": "directory/path",
        "message": "当前知识库版本中没有找到这个条目。",
    }


def test_agent_runner_sends_previous_turns_as_role_preserving_message_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = PydanticAIKnowledgeRunner(
        base_url="https://models.example.test/v1",
        api_key="local-test-key",
        model="sociology-model",
        timeout_seconds=30,
    )
    captured: dict[str, object] = {}

    def run_sync(user_prompt, **kwargs):
        captured["user_prompt"] = user_prompt
        captured["message_history"] = kwargs.get("message_history")
        return SimpleNamespace(output="米德与戈夫曼的自我理论侧重不同。")

    monkeypatch.setattr(runner._agent, "run_sync", run_sync)
    previous_turn = AgentTurn.create(
        user_content="请介绍米德的自我理论。",
        assistant_content="米德区分了主我与客我。",
        citations=(),
        evidence_ids=frozenset(),
    )

    runner.run(
        prompt="那它和戈夫曼的观点有什么区别？",
        conversation=(previous_turn,),
        tools=_FakeAgentTools(),
    )

    assert captured["user_prompt"] == "那它和戈夫曼的观点有什么区别？"
    history = captured["message_history"]
    assert isinstance(history, list)
    assert len(history) == 2
    assert isinstance(history[0], ModelRequest)
    assert isinstance(history[0].parts[0], UserPromptPart)
    assert history[0].parts[0].content == "请介绍米德的自我理论。"
    assert isinstance(history[1], ModelResponse)
    assert isinstance(history[1].parts[0], TextPart)
    assert history[1].parts[0].content == "米德区分了主我与客我。"


def test_agent_application_passes_the_last_eight_turns_without_flattening() -> None:
    class _HistoryRecordingRunner(_CountingRunner):
        def __init__(self) -> None:
            super().__init__()
            self.histories: list[object] = []

        def run(self, *, prompt, conversation, tools) -> AgentRunResult:
            self.histories.append(conversation)
            return super().run(prompt=prompt, conversation=conversation, tools=tools)

    runner = _HistoryRecordingRunner()
    application = DisciplinaryAgentApplication(
        conversations=ConversationService.in_memory(),
        runner=runner,
        tools_factory=_FakeAgentTools,
    )
    user_id = UUID("00000000-0000-0000-0000-000000000001")
    conversation_id = None

    for index in range(10):
        execution = application.run_turn(
            user_id=user_id,
            conversation_id=conversation_id,
            prompt=f"message-{index}",
            idempotency_key=f"role-history-{index}",
        )
        conversation_id = execution.conversation.conversation_id

    history = runner.histories[-1]
    assert isinstance(history, tuple)
    assert [turn.user_message.content for turn in history] == [
        f"message-{index}" for index in range(1, 9)
    ]


def test_agent_identity_request_is_answered_naturally_by_the_agent() -> None:
    class _IdentityAwareRunner:
        runtime_identity = SimpleNamespace(
            provider="private-provider",
            model="private-runtime-model",
        )

        def __init__(self) -> None:
            self.calls = 0

        def run(self, *, prompt, conversation, tools):
            del conversation, tools
            assert prompt
            self.calls += 1
            return AgentRunResult(
                answer="我不知道自己具体是什么模型。",
                citations=(),
                release_id="release-a",
                provider="private-provider",
                model="private-runtime-model",
            )

    runner = _IdentityAwareRunner()

    application = DisciplinaryAgentApplication(
        conversations=ConversationService.in_memory(),
        runner=runner,
        tools_factory=_FakeAgentTools,
    )
    user_id = UUID("00000000-0000-0000-0000-000000000001")

    for index, prompt in enumerate(
        (
            "报告你的模型",
            "你是哪个模型？",
            "你是哪家供应商的？",
            "你是不是 GPT-5.6-terra？",
        )
    ):
        execution = application.run_turn(
            user_id=user_id,
            conversation_id=None,
            prompt=prompt,
            idempotency_key=f"identity-{index}",
        )

        assert execution.result.answer == "我不知道自己具体是什么模型。"
        assert "private-runtime-model" not in execution.result.answer

    assert runner.calls == 4

    regular_runner = _CountingRunner()
    regular_application = DisciplinaryAgentApplication(
        conversations=ConversationService.in_memory(),
        runner=regular_runner,
        tools_factory=_FakeAgentTools,
    )
    regular_application.run_turn(
        user_id=user_id,
        conversation_id=None,
        prompt="你是如何看待科技公司里的劳动异化？",
        idempotency_key="regular-company-question",
    )

    assert regular_runner.calls == 1


def test_agent_sync_uses_the_main_model_when_no_knowledge_tool_is_needed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Tools:
        release = SimpleNamespace(knowledge_release_id="release-a")
        evidence = {}

        def search_knowledge(self, query: str):
            raise AssertionError(f"模型没有调用工具时不应自动检索：{query}")

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    monkeypatch.setattr(
        runner._agent,
        "run_sync",
        lambda *args, **kwargs: SimpleNamespace(output="这是基于通用社会学知识的回答。"),
    )

    result = runner.run(prompt="问题", conversation=(), tools=_Tools())

    assert result.answer == "这是基于通用社会学知识的回答。"
    assert result.citations == ()


def test_agent_can_search_and_read_web_pages_when_the_turn_opts_in() -> None:
    url = "https://www.gov.cn/zhengce/example.html"
    citation_id = f"web:{url}"

    class _Tools:
        release = SimpleNamespace(knowledge_release_id="release-a")
        web_search_enabled = True

        def __init__(self) -> None:
            self.evidence = {}
            self.selected_evidence_ids: tuple[str, ...] = ()
            self.searches: list[str] = []
            self.reads: list[str] = []

        def search_web(self, query: str, *, limit: int = 5):
            self.searches.append(query)
            self.evidence[citation_id] = AgentEvidence(
                citation_id=citation_id,
                label="高校毕业生就业政策",
                kind="source",
                excerpt="政策摘要",
                source_id=url,
                source_kind="web",
            )
            return [{
                "citation_id": citation_id,
                "title": "高校毕业生就业政策",
                "url": url,
                "excerpt": "政策摘要",
            }]

        def read_web_page(self, requested_url: str):
            self.reads.append(requested_url)
            return {
                "citation_id": citation_id,
                "title": "高校毕业生就业政策",
                "url": requested_url,
                "content": "政策完整正文",
            }

        def select_evidence(self, citation_ids):
            self.selected_evidence_ids = tuple(citation_ids)
            return self.selected_evidence_ids

    tools = _Tools()

    async def model_stream(messages, info):
        del messages, info
        if not tools.searches:
            yield {
                0: DeltaToolCall(
                    name="search_web",
                    json_args='{"query":"高校毕业生 就业 政策"}',
                    tool_call_id="call-web-search",
                )
            }
        elif not tools.reads:
            yield {
                0: DeltaToolCall(
                    name="read_web_page",
                    json_args=f'{{"url":"{url}"}}',
                    tool_call_id="call-web-read",
                )
            }
        else:
            yield "根据政府网页，相关就业支持政策已经发布。"

    runner = PydanticAIKnowledgeRunner(
        base_url="https://models.example.test/v1",
        api_key="local-test-key",
        model="sociology-model",
        timeout_seconds=30,
    )
    tool_events = []
    with runner._agent.override(model=FunctionModel(stream_function=model_stream)):
        result = runner.run_stream(
            prompt="查找近期高校毕业生就业政策",
            conversation=(),
            tools=tools,
            on_delta=lambda _: None,
            on_tool_event=tool_events.append,
        )

    assert tools.searches == ["高校毕业生 就业 政策"]
    assert tools.reads == [url]
    assert result.citations == (tools.evidence[citation_id],)
    assert [(event.tool, event.phase) for event in tool_events] == [
        ("search_web", "started"),
        ("search_web", "finished"),
        ("read_web_page", "started"),
        ("read_web_page", "finished"),
    ]


def test_read_web_pages_accumulate_as_citations_within_one_turn() -> None:
    urls = [f"https://www.gov.cn/zhengce/example-{suffix}.html" for suffix in ("a", "b")]

    class _Tools:
        def __init__(self) -> None:
            self.evidence = {
                f"web:{url}": AgentEvidence(
                    citation_id=f"web:{url}",
                    label=url.rsplit("/", 1)[-1],
                    kind="source",
                    excerpt="正文",
                    source_id=url,
                    source_kind="web",
                )
                for url in urls
            }
            self.selected_evidence_ids: tuple[str, ...] = ()

        def select_evidence(self, citation_ids):
            self.selected_evidence_ids = tuple(citation_ids)

    tools = _Tools()
    _append_result_evidence(tools, [{"citation_id": f"web:{urls[0]}"}])
    _append_result_evidence(tools, [{"citation_id": f"web:{urls[1]}"}])

    assert tools.selected_evidence_ids == tuple(f"web:{url}" for url in urls)


def test_agent_result_preserves_every_selected_citation_beyond_eight() -> None:
    knowledge_results = [
        {
            "citation_id": f"knowledge:{index}",
            "source_citation_ids": [f"source:{index}"],
        }
        for index in range(5)
    ]
    web_results = [{"citation_id": f"web:https://example.com/{index}"} for index in range(3)]
    expected_ids = tuple(
        citation_id
        for result in (*knowledge_results, *web_results)
        for citation_id in (result["citation_id"], *result.get("source_citation_ids", []))
    )

    class _Tools:
        release = SimpleNamespace(knowledge_release_id="release-all-citations")

        def __init__(self) -> None:
            self.evidence = {
                citation_id: AgentEvidence(
                    citation_id=citation_id,
                    label=citation_id,
                    kind="source",
                    excerpt="已采用证据",
                    source_id=citation_id,
                    source_kind="web" if citation_id.startswith("web:") else "knowledge",
                )
                for citation_id in expected_ids
            }
            self.selected_evidence_ids: tuple[str, ...] = ()

        def select_evidence(self, citation_ids):
            self.selected_evidence_ids = tuple(citation_ids)

    tools = _Tools()
    _select_result_evidence(tools, knowledge_results)
    _append_result_evidence(tools, web_results)

    result = _text_result("完整证据回答", tools=tools, model="sociology-model")

    assert tuple(citation.citation_id for citation in result.citations) == expected_ids


def test_agent_policy_searches_for_a_plain_sociology_concept_by_default() -> None:
    citation_id = "knowledge:D1:C003"

    class _Tools:
        release = SimpleNamespace(knowledge_release_id="release-a")

        def __init__(self) -> None:
            self.evidence = {}
            self.selected_evidence_ids: tuple[str, ...] = ()
            self.queries: list[str] = []

        def select_evidence(self, citation_ids):
            values = tuple(citation_ids)
            assert set(values) <= set(self.evidence)
            self.selected_evidence_ids = values
            return values

        def search_knowledge(self, query: str, *, limit: int = 5):
            assert limit == 5
            self.queries.append(query)
            self.evidence[citation_id] = AgentEvidence(
                citation_id=citation_id,
                label="异化劳动",
                kind="entry",
                excerpt="异化劳动描述劳动者与劳动活动及其结果的结构性分离。",
                knowledge_id="D1:C003",
            )
            return [
                {
                    "citation_id": citation_id,
                    "knowledge_id": "D1:C003",
                    "title": "异化劳动",
                    "excerpt": "异化劳动描述劳动者与劳动活动及其结果的结构性分离。",
                    "evidence_status": "verified",
                }
            ]

    tools = _Tools()

    async def model_stream(messages, info):
        del messages
        instructions = info.instructions or ""
        follows_default_search_policy = (
            "社会学概念、理论和社会现象" in instructions
            and "默认先调用 search_knowledge" in instructions
        )
        if not tools.queries and follows_default_search_policy:
            yield {
                0: DeltaToolCall(
                    name="search_knowledge",
                    json_args='{"query":"异化劳动"}',
                    tool_call_id="call-search-alienation",
                )
            }
        elif not tools.queries:
            yield "异化是人与其劳动及社会关系发生分离。"
        else:
            yield "根据知识库，异化劳动是劳动者与劳动活动及其结果的结构性分离。"

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    tool_events = []
    with runner._agent.override(model=FunctionModel(stream_function=model_stream)):
        result = runner.run_stream(
            prompt="什么是异化？",
            conversation=(),
            tools=tools,
            on_delta=lambda _: None,
            on_tool_event=tool_events.append,
        )

    assert tools.queries == ["异化劳动"]
    assert [(event.phase, event.call_id) for event in tool_events] == [
        ("started", "call-search-alienation"),
        ("finished", "call-search-alienation"),
    ]
    assert tools.selected_evidence_ids == (citation_id,)
    assert result.answer.startswith("根据知识库")


def test_agent_policy_answers_tool_strategy_questions_without_searching() -> None:
    class _Tools:
        release = SimpleNamespace(knowledge_release_id="release-a")
        evidence = {}

        def __init__(self) -> None:
            self.queries: list[str] = []

        def select_evidence(self, citation_ids):
            assert tuple(citation_ids) == ()
            return ()

        def search_knowledge(self, query: str, *, limit: int = 5):
            self.queries.append(query)
            return []

    tools = _Tools()

    async def model_stream(messages, info):
        del messages
        instructions = info.instructions or ""
        recognizes_tool_strategy_meta_question = (
            "工具调用规则、检索策略或调用条件" in instructions
            and "不要调用知识库" in instructions
        )
        if not tools.queries and not recognizes_tool_strategy_meta_question:
            yield {
                0: DeltaToolCall(
                    name="search_knowledge",
                    json_args='{"query":"知识库调用策略"}',
                    tool_call_id="call-wrong-policy-search",
                )
            }
        else:
            yield "我会根据问题的社会学内容判断是否需要知识库支持。"

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    tool_events = []
    with runner._agent.override(model=FunctionModel(stream_function=model_stream)):
        result = runner.run_stream(
            prompt="在怎样的策略下你会调用知识库？",
            conversation=(),
            tools=tools,
            on_delta=lambda _: None,
            on_tool_event=tool_events.append,
        )

    assert tools.queries == []
    assert tool_events == []
    assert result.answer == "我会根据问题的社会学内容判断是否需要知识库支持。"


def test_agent_does_not_auto_cite_tool_evidence_the_model_did_not_select(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Tools:
        release = SimpleNamespace(knowledge_release_id="release-a")
        evidence = {
            "knowledge:D1:C001": AgentEvidence(
                citation_id="knowledge:D1:C001",
                label="青年孤独",
                kind="entry",
                excerpt="这是检索候选，但回答没有采用它。",
                knowledge_id="D1:C001",
            )
        }

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    monkeypatch.setattr(
        runner._agent,
        "run_sync",
        lambda *args, **kwargs: SimpleNamespace(output="这是没有使用该候选证据的回答。"),
    )

    result = runner.run(prompt="解释一个社会现象", conversation=(), tools=_Tools())

    assert result.citations == ()


def test_agent_does_not_infer_citations_by_scanning_a_bare_knowledge_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Tools:
        release = SimpleNamespace(knowledge_release_id="release-preview")
        evidence = {
            "knowledge:D1:C029": AgentEvidence(
                citation_id="knowledge:D1:C029",
                label="社会行动四类型",
                kind="preview",
                excerpt="韦伯区分了四种社会行动类型。",
                knowledge_id="D1:C029",
            )
        }

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    monkeypatch.setattr(
        runner._agent,
        "run_sync",
        lambda *args, **kwargs: SimpleNamespace(
            output="知识卡片 ID：D1:C029，可从社会行动四类型展开理解。"
        ),
    )

    result = runner.run(prompt="解释社会行动四类型", conversation=(), tools=_Tools())

    assert result.citations == ()


def test_agent_does_not_infer_citations_by_scanning_a_catalog_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Tools:
        release = SimpleNamespace(knowledge_release_id="release-preview")
        evidence = {
            "knowledge:D1:C1059": AgentEvidence(
                citation_id="knowledge:D1:C1059",
                label="个体化（中国）",
                kind="preview",
                excerpt="中国的去传统化使个体面临更大风险。",
                knowledge_id="D1:C1059",
            )
        }

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    monkeypatch.setattr(
        runner._agent,
        "run_sync",
        lambda *args, **kwargs: SimpleNamespace(
            output="知识库中的个体化条目（C1059）支持这一理论线索。"
        ),
    )

    result = runner.run(prompt="解释年轻人的孤独", conversation=(), tools=_Tools())

    assert result.citations == ()


def test_agent_rejects_an_ambiguous_catalog_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Tools:
        release = SimpleNamespace(knowledge_release_id="release-preview")
        evidence = {
            f"knowledge:{knowledge_id}": AgentEvidence(
                citation_id=f"knowledge:{knowledge_id}",
                label=label,
                kind="preview",
                excerpt="同一后缀不能决定实际引用的是哪一条知识。",
                knowledge_id=knowledge_id,
            )
            for knowledge_id, label in (
                ("D1:C001", "本体论条目"),
                ("D2:C001", "实践论条目"),
            )
        }

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    monkeypatch.setattr(
        runner._agent,
        "run_sync",
        lambda *args, **kwargs: SimpleNamespace(output="可参考知识条目 C001。"),
    )

    result = runner.run(prompt="解释社会行动", conversation=(), tools=_Tools())

    assert result.citations == ()


def test_agent_can_run_multiple_knowledge_tools_before_answering() -> None:
    citation_id = "knowledge:D1:C001"

    class _Tools:
        release = SimpleNamespace(knowledge_release_id="release-a")

        def __init__(self) -> None:
            self.evidence = {}
            self.selected_evidence_ids: tuple[str, ...] = ()
            self.calls: list[tuple[str, object]] = []

        def select_evidence(self, citation_ids):
            values = tuple(citation_ids)
            assert set(values) <= set(self.evidence)
            self.selected_evidence_ids = values
            return values

        def search_knowledge(self, query: str, *, limit: int = 5):
            self.calls.append(("search_knowledge", {"query": query, "limit": limit}))
            self.evidence[citation_id] = AgentEvidence(
                citation_id=citation_id,
                label="青年孤独",
                kind="entry",
                excerpt="青年孤独与社会联结的结构性变化有关。",
                knowledge_id="D1:C001",
            )
            return [
                {
                    "citation_id": citation_id,
                    "knowledge_id": "D1:C001",
                    "title": "青年孤独",
                    "excerpt": "青年孤独与社会联结的结构性变化有关。",
                }
            ]

        def read_knowledge_entry(self, knowledge_id: str):
            self.calls.append(("read_knowledge_entry", {"knowledge_id": knowledge_id}))
            return {
                "citation_id": citation_id,
                "knowledge_id": knowledge_id,
                "title": "青年孤独",
                "content": "青年孤独与社会联结的结构性变化有关。",
            }

    tools = _Tools()

    async def model_stream(messages, info):
        del messages, info
        if not tools.calls:
            yield {
                0: DeltaToolCall(
                    name="search_knowledge",
                    json_args='{"query":"青年孤独 社会联结"}',
                    tool_call_id="call-search",
                )
            }
        elif len(tools.calls) == 1:
            yield {
                0: DeltaToolCall(
                    name="read_knowledge_entry",
                    json_args='{"knowledge_id":"D1:C001"}',
                    tool_call_id="call-read",
                )
            }
        else:
            yield "可以从社会联结的结构性变化切入。"

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    deltas: list[str] = []
    tool_events = []
    with runner._agent.override(model=FunctionModel(stream_function=model_stream)):
        result = runner.run_stream(
            prompt="年轻人越来越孤独，可以怎么理解？",
            conversation=(),
            tools=tools,
            on_delta=deltas.append,
            on_tool_event=tool_events.append,
        )

    assert tools.calls == [
        (
            "search_knowledge",
            {"query": "青年孤独 社会联结", "limit": 5},
        ),
        ("read_knowledge_entry", {"knowledge_id": "D1:C001"}),
    ]
    assert [(event.tool, event.phase, event.call_id) for event in tool_events] == [
        ("search_knowledge", "started", "call-search"),
        ("search_knowledge", "finished", "call-search"),
        ("read_knowledge_entry", "started", "call-read"),
        ("read_knowledge_entry", "finished", "call-read"),
    ]
    assert tool_events[0].input == {"query": "青年孤独 社会联结"}
    assert tool_events[1].output["result_count"] == 1
    assert tool_events[1].output["items"][0]["knowledge_id"] == "D1:C001"
    assert "".join(deltas) == result.answer
    assert tools.selected_evidence_ids == (citation_id,)
    assert [citation.citation_id for citation in result.citations] == [citation_id]


def test_agent_can_reformulate_an_empty_knowledge_search_before_answering() -> None:
    citation_id = "knowledge:D1:C002"

    class _Tools:
        release = SimpleNamespace(knowledge_release_id="release-a")

        def __init__(self) -> None:
            self.evidence = {}
            self.selected_evidence_ids: tuple[str, ...] = ()
            self.queries: list[str] = []

        def select_evidence(self, citation_ids):
            values = tuple(citation_ids)
            assert set(values) <= set(self.evidence)
            self.selected_evidence_ids = values
            return values

        def search_knowledge(self, query: str, *, limit: int = 5):
            assert limit == 5
            self.queries.append(query)
            if query != "劳动过程中的时间控制与工作自主性":
                return []
            self.evidence[citation_id] = AgentEvidence(
                citation_id=citation_id,
                label="劳动过程中的时间控制",
                kind="entry",
                excerpt="平台通过时间指标加强劳动控制，并压缩劳动者的工作自主性。",
                knowledge_id="D1:C002",
            )
            return [
                {
                    "citation_id": citation_id,
                    "knowledge_id": "D1:C002",
                    "title": "劳动过程中的时间控制",
                    "excerpt": "平台通过时间指标加强劳动控制，并压缩劳动者的工作自主性。",
                    "evidence_status": "verified",
                }
            ]

    tools = _Tools()

    async def model_stream(messages, info):
        del messages, info
        if not tools.queries:
            yield {
                0: DeltaToolCall(
                    name="search_knowledge",
                    json_args='{"query":"外卖平台为何压缩骑手时间"}',
                    tool_call_id="call-search-original",
                )
            }
        elif len(tools.queries) == 1:
            yield {
                0: DeltaToolCall(
                    name="search_knowledge",
                    json_args=('{"query":"劳动过程中的时间控制与工作自主性"}'),
                    tool_call_id="call-search-concept",
                )
            }
        else:
            yield "可以从平台的时间控制与骑手工作自主性被压缩来解释。"

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    tool_events = []
    with runner._agent.override(model=FunctionModel(stream_function=model_stream)):
        result = runner.run_stream(
            prompt="请结合知识库解释：外卖平台为何压缩骑手时间",
            conversation=(),
            tools=tools,
            on_delta=lambda _: None,
            on_tool_event=tool_events.append,
        )

    assert tools.queries == [
        "外卖平台为何压缩骑手时间",
        "劳动过程中的时间控制与工作自主性",
    ]
    assert [(event.phase, event.call_id) for event in tool_events] == [
        ("started", "call-search-original"),
        ("finished", "call-search-original"),
        ("started", "call-search-concept"),
        ("finished", "call-search-concept"),
    ]
    assert result.answer == "可以从平台的时间控制与骑手工作自主性被压缩来解释。"
    assert tools.selected_evidence_ids == (citation_id,)


def test_agent_returns_search_failure_to_the_model_for_a_second_judgment() -> None:
    class _Tools:
        release = SimpleNamespace(knowledge_release_id="release-a")
        evidence = {}

        def __init__(self) -> None:
            self.search_attempts = 0

        def search_knowledge(self, query: str, *, limit: int = 5):
            del query, limit
            self.search_attempts += 1
            raise RuntimeError("database details must not reach the user")

    tools = _Tools()

    async def model_stream(messages, info):
        del messages, info
        if tools.search_attempts == 0:
            yield {
                0: DeltaToolCall(
                    name="search_knowledge",
                    json_args='{"query":"青年孤独"}',
                    tool_call_id="call-search-failed",
                )
            }
        else:
            yield "知识库暂时不可用，我先从社会联结的结构性变化来分析。"

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    tool_events = []
    deltas: list[str] = []
    with runner._agent.override(model=FunctionModel(stream_function=model_stream)):
        result = runner.run_stream(
            prompt="请结合知识库解释年轻人越来越孤独。",
            conversation=(),
            tools=tools,
            on_delta=deltas.append,
            on_tool_event=tool_events.append,
        )

    assert [(event.phase, event.call_id) for event in tool_events] == [
        ("started", "call-search-failed"),
        ("failed", "call-search-failed"),
    ]
    assert tool_events[-1].error == "knowledge_search_failed"
    assert "database details" not in (tool_events[-1].detail or "")
    assert result.answer == "知识库暂时不可用，我先从社会联结的结构性变化来分析。"
    assert "".join(deltas) == result.answer


def test_agent_shared_router_records_primary_and_fallback_with_run_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_id = UUID(int=41)
    agent_run_id = UUID(int=42)
    attempts = InMemoryModelAttemptRecorder()
    router = ModelRouteExecutor(endpoints=_agent_endpoints(), recorder=attempts)
    runner = PydanticAIKnowledgeRunner(
        base_url="https://primary.example.test/v1",
        api_key="primary-key",
        fallback_endpoints=(
            ("https://backup.example.test/v1", "backup-key", "backup-model"),
        ),
        model="primary-model",
        timeout_seconds=30,
        route_executor=router,
    )
    completed_request = object()
    called_models: list[str] = []

    async def request_once(self, *args, **kwargs):
        del args, kwargs
        called_models.append(self.model_name)
        if self.base_url.startswith("https://primary"):
            raise ModelHTTPError(
                status_code=429,
                model_name="primary-model",
                body={"message": "rate limited"},
            )
        return completed_request

    class _RouteAwareTools:
        release = SimpleNamespace(knowledge_release_id="release-a")
        evidence: dict[str, object] = {}
        selected_evidence_ids: tuple[str, ...] = ()

        @staticmethod
        def agent_route_context() -> dict[str, UUID | None]:
            return {
                "user_id": UUID(int=40),
                "task_id": task_id,
                "agent_run_id": agent_run_id,
            }

    monkeypatch.setattr(OpenAIChatModel, "_completions_create", request_once)

    def run_sync(*args, **kwargs):
        del args, kwargs
        result = asyncio.run(
            runner._agent.model._completions_create(
                [], False, {}, ModelRequestParameters()
            )
        )
        assert result is completed_request
        return SimpleNamespace(output="路由完成")

    monkeypatch.setattr(runner._agent, "run_sync", run_sync)

    result = runner.run(
        prompt="你好",
        conversation=(),
        tools=_RouteAwareTools(),
    )

    records = [
        item for item in attempts.list_all() if item.agent_run_id == agent_run_id
    ]
    assert result.answer == "路由完成"
    assert called_models == ["primary-model", "backup-model"]
    assert [item.endpoint_id for item in records] == ["primary", "fallback-1"]
    assert len({item.route_id for item in records}) == 1
    assert records[0].failure_code == "model_rate_limited"
    assert records[0].failure_retryable is True
    assert records[1].success is True
    assert all(item.task_id == task_id for item in records)
    assert all(item.agent_run_id == agent_run_id for item in records)
    assert all(item.capability == "agent_completion" for item in records)
    assert all(
        not hasattr(item, field)
        for item in records
        for field in ("user_id", "prompt", "material")
    )


@pytest.mark.parametrize("outcome", ["normal", "error", "cancelled"])
def test_planner_route_context_is_correlated_and_reset_after_every_exit(
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    task_id = UUID(int=61)
    agent_run_id = UUID(int=62)
    attempts = InMemoryModelAttemptRecorder()
    router = ModelRouteExecutor(
        endpoints=(_agent_endpoints()[0],),
        recorder=attempts,
    )
    runner = PydanticAIKnowledgeRunner(
        base_url="https://primary.example.test/v1",
        api_key="primary-key",
        model="primary-model",
        timeout_seconds=30,
        route_executor=router,
    )
    request_count = 0

    async def request_once(self, *args, **kwargs):
        nonlocal request_count
        del self, args, kwargs
        request_count += 1
        if outcome == "cancelled" and request_count == 1:
            raise asyncio.CancelledError
        return object()

    def planner_run_sync(*args, **kwargs):
        del args, kwargs
        asyncio.run(
            runner._planner_agent.model._completions_create(
                [], False, {}, ModelRequestParameters()
            )
        )
        if outcome == "error":
            raise RuntimeError("planner failed after completion")
        return SimpleNamespace(output=SimpleNamespace(request_type="conversation"))

    tools = SimpleNamespace(
        agent_route_context=lambda: {
            "user_id": UUID(int=60),
            "task_id": task_id,
            "agent_run_id": agent_run_id,
        }
    )
    monkeypatch.setattr(OpenAIChatModel, "_completions_create", request_once)
    monkeypatch.setattr(runner._planner_agent, "run_sync", planner_run_sync)

    if outcome == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            runner.prepare_research(
                prompt="研究平台劳动关系",
                conversation=(),
                tools=tools,
                on_event=lambda event: None,
            )
    else:
        runner.prepare_research(
            prompt="研究平台劳动关系",
            conversation=(),
            tools=tools,
            on_event=lambda event: None,
        )

    asyncio.run(
        runner._agent.model._completions_create(
            [], False, {}, ModelRequestParameters()
        )
    )

    records = attempts.list_all()
    assert records[0].task_id == task_id
    assert records[0].agent_run_id == agent_run_id
    assert records[0].capability == "agent_completion"
    assert records[-1].task_id is None
    assert records[-1].agent_run_id is None
    assert records[-1].capability == "agent_completion"
    assert all(not hasattr(item, "user_id") for item in records)


def test_agent_shared_router_creates_a_fresh_route_for_each_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = InMemoryModelAttemptRecorder()
    endpoints = (_agent_endpoints()[0],)
    router = ModelRouteExecutor(endpoints=endpoints, recorder=attempts)
    runner = PydanticAIKnowledgeRunner(
        base_url="https://primary.example.test/v1",
        api_key="primary-key",
        model="primary-model",
        timeout_seconds=30,
        route_executor=router,
    )

    async def request_once(self, *args, **kwargs):
        del self, args, kwargs
        return object()

    monkeypatch.setattr(OpenAIChatModel, "_completions_create", request_once)

    async def complete_twice() -> None:
        await runner._agent.model._completions_create(
            [], False, {}, ModelRequestParameters()
        )
        await runner._agent.model._completions_create(
            [], False, {}, ModelRequestParameters()
        )

    asyncio.run(complete_twice())

    route_ids = [item.route_id for item in attempts.list_all()]
    assert len(route_ids) == 2
    assert route_ids[0] is not None
    assert route_ids[1] is not None
    assert route_ids[0] != route_ids[1]


def test_agent_shared_router_preserves_model_request_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = InMemoryModelAttemptRecorder()
    router = ModelRouteExecutor(endpoints=_agent_endpoints(), recorder=attempts)
    runner = PydanticAIKnowledgeRunner(
        base_url="https://primary.example.test/v1",
        api_key="primary-key",
        fallback_endpoints=(
            ("https://backup.example.test/v1", "backup-key", "backup-model"),
        ),
        model="primary-model",
        timeout_seconds=30,
        route_executor=router,
    )
    calls: list[str] = []

    async def cancelled_request(self, *args, **kwargs):
        del args, kwargs
        calls.append(self.model_name)
        raise asyncio.CancelledError

    monkeypatch.setattr(OpenAIChatModel, "_completions_create", cancelled_request)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            runner._agent.model._completions_create(
                [], False, {}, ModelRequestParameters()
            )
        )

    records = attempts.list_all()
    assert calls == ["primary-model"]
    assert len(records) == 1
    assert records[0].failure_code == "model_attempt_cancelled"


def test_agent_routes_unknown_provider_to_the_next_model_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fallback_endpoints = (
        ("https://backup.example.test/v1", "backup-key", "backup-model"),
    )
    runner = PydanticAIKnowledgeRunner(
        base_url="https://models.example.test/v1",
        api_key="local-test-key",
        fallback_endpoints=fallback_endpoints,
        model="gpt-5.6-terra",
        timeout_seconds=30,
        route_executor=_agent_route_executor(
            base_url="https://models.example.test/v1",
            api_key="local-test-key",
            model="gpt-5.6-terra",
            fallback_endpoints=fallback_endpoints,
        ),
    )
    model = runner._agent.model
    attempts = 0
    completed_request = object()

    async def request_once(*args, **kwargs):
        nonlocal attempts
        del args, kwargs
        attempts += 1
        if attempts == 1:
            raise ModelHTTPError(
                status_code=400,
                model_name="gpt-5.6-terra",
                body={"message": "unknown provider for model gpt-5.6-terra"},
            )
        return completed_request

    monkeypatch.setattr(OpenAIChatModel, "_completions_create", request_once)
    result = asyncio.run(
        model._completions_create([], False, {}, ModelRequestParameters())
    )

    assert attempts == 2
    assert result is completed_request


def test_agent_does_not_retry_other_bad_model_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = PydanticAIKnowledgeRunner(
        base_url="https://models.example.test/v1",
        api_key="local-test-key",
        model="gpt-5.6-terra",
        timeout_seconds=30,
        route_executor=_agent_route_executor(
            base_url="https://models.example.test/v1",
            api_key="local-test-key",
            model="gpt-5.6-terra",
        ),
    )
    model = runner._agent.model
    attempts = 0

    async def request_once(*args, **kwargs):
        nonlocal attempts
        del args, kwargs
        attempts += 1
        raise ModelHTTPError(
            status_code=400,
            model_name="gpt-5.6-terra",
            body={"message": "invalid request parameter"},
        )

    monkeypatch.setattr(OpenAIChatModel, "_completions_create", request_once)

    with pytest.raises(ModelHTTPError, match="invalid request parameter"):
        asyncio.run(
            model._completions_create([], False, {}, ModelRequestParameters())
        )

    assert attempts == 1


def test_agent_fails_over_to_the_next_model_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fallback_endpoints = (
        ("https://backup.example.test/v1", "backup-key"),
    )
    runner = PydanticAIKnowledgeRunner(
        base_url="https://primary.example.test/v1",
        api_key="primary-key",
        fallback_endpoints=fallback_endpoints,
        model="gpt-5.6-sol",
        timeout_seconds=30,
        route_executor=_agent_route_executor(
            base_url="https://primary.example.test/v1",
            api_key="primary-key",
            model="gpt-5.6-sol",
            fallback_endpoints=fallback_endpoints,
        ),
    )
    model = runner._agent.model
    calls: list[str] = []
    completed_request = object()

    async def request_once(self, *args, **kwargs):
        del args, kwargs
        calls.append(self.base_url)
        if self.base_url.startswith("https://primary"):
            raise ModelHTTPError(
                status_code=503,
                model_name="gpt-5.6-sol",
                body={"message": "Service temporarily unavailable"},
            )
        return completed_request

    monkeypatch.setattr(OpenAIChatModel, "_completions_create", request_once)

    result = asyncio.run(
        model._completions_create([], False, {}, ModelRequestParameters())
    )

    assert result is completed_request
    assert calls == [
        "https://primary.example.test/v1/",
        "https://backup.example.test/v1/",
    ]


def test_agent_uses_primary_before_calling_fallback_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fallback_endpoints = (("https://fast.example.test/v1", "fast-key"),)
    runner = PydanticAIKnowledgeRunner(
        base_url="https://slow.example.test/v1",
        api_key="slow-key",
        fallback_endpoints=fallback_endpoints,
        model="gpt-5.6-sol",
        timeout_seconds=30,
        route_executor=_agent_route_executor(
            base_url="https://slow.example.test/v1",
            api_key="slow-key",
            model="gpt-5.6-sol",
            fallback_endpoints=fallback_endpoints,
        ),
    )
    model = runner._agent.model
    calls: list[str] = []
    primary_response = object()

    async def request_once(self, *args, **kwargs):
        del args, kwargs
        calls.append(self.base_url)
        if self.base_url.startswith("https://slow"):
            await asyncio.sleep(0.05)
            return primary_response
        return object()

    monkeypatch.setattr(OpenAIChatModel, "_completions_create", request_once)

    result = asyncio.run(
        model._completions_create([], False, {}, ModelRequestParameters())
    )

    assert calls == ["https://slow.example.test/v1/"]
    assert result is primary_response


def test_agent_does_not_race_keys_for_the_same_primary_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fallback_endpoints = (
        ("https://primary.example.test/v1", "peer-key"),
        ("https://backup.example.test/v1", "backup-key"),
    )
    runner = PydanticAIKnowledgeRunner(
        base_url="https://primary.example.test/v1",
        api_key="primary-key",
        fallback_endpoints=fallback_endpoints,
        model="gpt-5.6-sol",
        timeout_seconds=30,
        route_executor=_agent_route_executor(
            base_url="https://primary.example.test/v1",
            api_key="primary-key",
            model="gpt-5.6-sol",
            fallback_endpoints=fallback_endpoints,
        ),
    )
    model = runner._agent.model
    calls: list[str] = []
    primary_response = object()

    async def request_once(self, *args, **kwargs):
        del args, kwargs
        api_key = self._provider.client.api_key
        calls.append(api_key)
        if api_key == "primary-key":
            await asyncio.sleep(0.05)
            return primary_response
        pytest.fail("fallback keys must not race a successful primary request")

    monkeypatch.setattr(OpenAIChatModel, "_completions_create", request_once)

    result = asyncio.run(
        model._completions_create([], False, {}, ModelRequestParameters())
    )

    assert result is primary_response
    assert calls == ["primary-key"]


def test_agent_keeps_coding_tools_after_endpoint_failover_change() -> None:
    runner = PydanticAIKnowledgeRunner(
        base_url="https://models.example.test/v1",
        api_key="local-test-key",
        model="gpt-5.6-sol",
        timeout_seconds=30,
    )

    tools = runner._agent._function_toolset.tools

    assert {"propose_coding_plan", "retrieve_coded_segments"} <= set(tools)


def test_knowledge_directory_is_bounded_and_queryable() -> None:
    release = SimpleNamespace(knowledge_release_id="release-a")
    directory = SimpleNamespace(
        nodes=(
            SimpleNamespace(
                node_id="D1",
                node_type="dimension",
                title="认识论",
                parent_node_id=None,
                entry_count=100,
            ),
            SimpleNamespace(
                node_id="D1:symbolic",
                node_type="category",
                title="符号互动论（Symbolic Interactionism）",
                parent_node_id="D1",
                entry_count=17,
            ),
            SimpleNamespace(
                node_id="D1:other",
                node_type="category",
                title="其他理论",
                parent_node_id="D1",
                entry_count=20,
            ),
        )
    )

    class _Catalog:
        def current_release(self, *, purpose):
            del purpose
            return release

        def get_directory(self, *, release_id):
            assert release_id == "release-a"
            return directory

    registry = KnowledgeToolRegistry(_Catalog())

    assert [item["node_id"] for item in registry.browse_knowledge_directory()] == ["D1"]
    assert [
        item["node_id"] for item in registry.browse_knowledge_directory(query="符号互动论", limit=1)
    ] == ["D1:symbolic"]


def test_directory_returns_uniform_entry_evidence_for_published_entries() -> None:
    release = SimpleNamespace(knowledge_release_id="release-final")
    item = SimpleNamespace(
        knowledge_id="D1:C031",
        title="社会事实",
        eligibility=SimpleNamespace(rag_eligible=False),
    )
    directory = SimpleNamespace(
        nodes=(
            SimpleNamespace(
                node_id="D1:classical",
                node_type="category",
                title="古典社会学奠基",
                parent_node_id="D1",
                entry_count=1,
            ),
        )
    )
    detail = SimpleNamespace(summary=item, aliases=(), content="社会事实具有约束力。")

    class _Catalog:
        def current_release(self, *, purpose):
            del purpose
            return release

        def get_directory(self, *, release_id):
            assert release_id == release.knowledge_release_id
            return directory

        def browse(self, **kwargs):
            assert kwargs["category_id"] == "D1:classical"
            return SimpleNamespace(entries=(item,))

        def get_entry(self, *, knowledge_id, release_id):
            assert knowledge_id == item.knowledge_id
            assert release_id == release.knowledge_release_id
            return detail

    registry = KnowledgeToolRegistry(_Catalog())
    [result] = registry.browse_knowledge_directory(query="古典社会学")

    assert result["entries"][0]["evidence_status"] == "verified"
    assert registry.evidence["knowledge:D1:C031"].kind == "entry"


def test_read_published_entry_returns_uniform_entry_evidence() -> None:
    release = SimpleNamespace(knowledge_release_id="release-preview")
    item = SimpleNamespace(
        knowledge_id="D1:C031",
        title="社会事实",
        category="古典社会学奠基",
        dimension="本体论",
        eligibility=SimpleNamespace(rag_eligible=False, browse_eligible=True),
    )
    detail = SimpleNamespace(
        summary=item,
        aliases=(),
        content="社会事实具有外在性和约束力。",
        sources=(),
    )

    class _Catalog:
        def current_release(self, *, purpose):
            del purpose
            return release

        def get_entry(self, **kwargs):
            assert kwargs["knowledge_id"] == "D1:C031"
            return detail

    registry = KnowledgeToolRegistry(_Catalog())
    result = registry.read_knowledge_entry("D1:C031")

    assert result["content"] == "社会事实具有外在性和约束力。"
    assert result["evidence_status"] == "verified"
    assert registry.evidence["knowledge:D1:C031"].kind == "entry"
