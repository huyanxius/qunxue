from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from sqlalchemy.exc import IntegrityError

from qunxue_api.adapters.research_agent.catalog_tools import (
    KnowledgeToolRegistry,
    _query_candidates,
)
from qunxue_api.adapters.research_agent.pydantic_runner import (
    PydanticAIKnowledgeRunner,
    _compose_agent_prompt,
)
from qunxue_api.adapters.sqlite.agent_conversation_model import AgentRunRow
from qunxue_api.adapters.sqlite.agent_conversation_repository import SqliteConversationRepository
from qunxue_api.api.routes.agent import _effective_agent_runtime_mode
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
from qunxue_api.settings import Settings


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


class _FakeAgentTools:
    release = SimpleNamespace(knowledge_release_id="release-a")
    evidence = {}


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
        json={"message": "请检索知识库，解释什么是符号互动？"},
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
        json={"message": "请检索知识库，解释什么是符号互动？"},
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
        "input": {"query": "请检索知识库，解释什么是符号互动？"},
        "output": None,
        "detail": "正在检索知识库",
        "error": None,
    }
    finished_trace = traces[1]
    assert finished_trace["phase"] == "finished"
    assert finished_trace["output"]["result_count"] == 1
    item = finished_trace["output"]["items"][0]
    assert item["knowledge_id"] == "D1:C077"
    assert item["title"] == "符号互动论方法论（SI Methodological Standpoint）"
    assert item["excerpt"]
    assert "符号互动论方法论" in finished_trace["detail"]
    with client.app.state.database.session() as session:
        run = session.query(AgentRunRow).filter_by(idempotency_key="agent-turn-1").one()
        assert run.status == "completed"
        assert detail.json()["turns"][0]["knowledge_release_id"] == run.knowledge_release_id
        assert len(run.tool_summary) == 2
        assert run.tool_summary[0]["phase"] == "started"
        assert run.tool_summary[1]["phase"] == "finished"
        assert run.tool_summary[1]["output"]["result_count"] == 1
        assert run.tool_summary[1]["output"]["items"][0]["knowledge_id"] == "D1:C077"


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


def test_agent_runner_forwards_configured_model_headers() -> None:
    runner = PydanticAIKnowledgeRunner(
        base_url="https://models.example.test/v1",
        api_key="local-test-key",
        model="sociology-model",
        timeout_seconds=30,
        extra_headers={"X-LoRA-ID": "local-lora-test-id"},
    )

    assert runner._agent.model.settings["extra_headers"] == {
        "X-LoRA-ID": "local-lora-test-id"
    }


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
    app = create_app(settings=settings, database=client.app.state.database)

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
        conversation="",
        tools=_Tools(),
        on_delta=lambda _: None,
    )

    assert result.answer == "可以从社会联结、劳动节奏与城市流动三个层面理解。"
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


def test_agent_prompt_keeps_history_separate_without_preloaded_rag_evidence() -> None:
    prompt = _compose_agent_prompt(
        prompt="那它和戈夫曼的观点有什么区别？",
        conversation="上一轮讨论了米德的自我理论。",
    )

    assert "<conversation_history>\n上一轮讨论了米德的自我理论。" in prompt
    assert "<current_question>\n那它和戈夫曼的观点有什么区别？" in prompt
    assert "本轮知识库检索证据" not in prompt


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

    result = runner.run(prompt="问题", conversation="", tools=_Tools())

    assert result.answer == "这是基于通用社会学知识的回答。"
    assert result.citations == ()


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

    result = runner.run(prompt="解释一个社会现象", conversation="", tools=_Tools())

    assert result.citations == ()


def test_agent_accepts_a_bare_knowledge_id_from_the_current_tool_evidence(
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

    result = runner.run(prompt="解释社会行动四类型", conversation="", tools=_Tools())

    assert [citation.citation_id for citation in result.citations] == ["knowledge:D1:C029"]


def test_agent_can_run_multiple_knowledge_tools_before_answering() -> None:
    citation_id = "knowledge:D1:C001"

    class _Tools:
        release = SimpleNamespace(knowledge_release_id="release-a")

        def __init__(self) -> None:
            self.evidence = {}
            self.calls: list[tuple[str, object]] = []

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
            yield f"可以从社会联结的结构性变化切入。{citation_id}"

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
            prompt="请结合知识库解释年轻人越来越孤独。",
            conversation="",
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
    assert [citation.citation_id for citation in result.citations] == [citation_id]


def test_agent_continues_with_general_knowledge_when_search_tool_is_unavailable() -> None:
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
    with runner._agent.override(model=FunctionModel(stream_function=model_stream)):
        result = runner.run_stream(
            prompt="请结合知识库解释年轻人越来越孤独。",
            conversation="",
            tools=tools,
            on_delta=lambda _: None,
            on_tool_event=tool_events.append,
        )

    assert result.answer == "知识库暂时不可用，我先从社会联结的结构性变化来分析。"
    assert [(event.phase, event.call_id) for event in tool_events] == [
        ("started", "call-search-failed"),
        ("failed", "call-search-failed"),
    ]
    assert tool_events[-1].error == "knowledge_search_failed"
    assert "database details" not in (tool_events[-1].detail or "")
    assert result.citations == ()


def test_knowledge_query_candidates_extract_terms_from_natural_language() -> None:
    candidates = _query_candidates("请根据当前知识库回答：什么是符号互动论？")

    assert candidates[0] == "请根据当前知识库回答：什么是符号互动论？"
    assert "符号互动" in candidates


def test_knowledge_tool_falls_back_to_fuzzy_catalog_candidates() -> None:
    release = SimpleNamespace(knowledge_release_id="release-a")
    item = SimpleNamespace(
        knowledge_id="D1:C001",
        title="符号互动论",
        category="经典理论范式",
        dimension="认识论",
        eligibility=SimpleNamespace(rag_eligible=True),
    )
    detail = SimpleNamespace(
        summary=item,
        aliases=("互动论", "Symbolic Interactionism"),
        content="符号互动论关注人如何通过互动形成自我理解。",
        sources=(),
    )

    class _Catalog:
        def current_release(self, *, purpose):
            del purpose
            return release

        def browse(self, **kwargs):
            if kwargs["query"] is None:
                return SimpleNamespace(entries=(item,))
            return SimpleNamespace(entries=())

        def get_entry(self, **kwargs):
            del kwargs
            return detail

    result = KnowledgeToolRegistry(_Catalog()).search_knowledge(
        "那个研究人如何通过互动形成自我理解的理论"
    )

    assert result[0]["knowledge_id"] == "D1:C001"


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
        item["node_id"]
        for item in registry.browse_knowledge_directory(query="符号互动论", limit=1)
    ] == ["D1:symbolic"]


def test_knowledge_tool_does_not_force_a_generic_chat_into_irrelevant_rag_evidence() -> None:
    release = SimpleNamespace(knowledge_release_id="release-a")
    item = SimpleNamespace(
        knowledge_id="D1:C001",
        title="符号互动论",
        category="经典理论范式",
        dimension="认识论",
        eligibility=SimpleNamespace(rag_eligible=True),
    )
    detail = SimpleNamespace(
        summary=item,
        aliases=("互动论",),
        content="符号互动论关注人如何通过互动形成自我理解。",
        sources=(),
    )

    class _Catalog:
        def current_release(self, *, purpose):
            del purpose
            return release

        def browse(self, **kwargs):
            return SimpleNamespace(entries=(item,) if kwargs["query"] is None else ())

        def get_entry(self, **kwargs):
            del kwargs
            return detail

    result = KnowledgeToolRegistry(_Catalog()).search_knowledge("你好，介绍一下你自己")

    assert result == []


def test_knowledge_search_returns_preview_content_when_formal_rag_is_empty() -> None:
    release = SimpleNamespace(knowledge_release_id="release-preview")
    item = SimpleNamespace(
        knowledge_id="D1:C029",
        title="社会行动四类型",
        category="古典社会学奠基",
        dimension="本体论",
        eligibility=SimpleNamespace(rag_eligible=False, browse_eligible=True),
    )
    detail = SimpleNamespace(
        summary=item,
        aliases=(),
        content="韦伯将社会行动区分为目的合理、价值合理、情感和传统四类。",
        sources=(),
    )

    class _Catalog:
        def current_release(self, *, purpose):
            del purpose
            return release

        def browse(self, **kwargs):
            if kwargs["query"] is None:
                return SimpleNamespace(entries=(item,), next_cursor=None)
            return SimpleNamespace(entries=(item,), next_cursor=None)

        def get_entry(self, **kwargs):
            assert kwargs["knowledge_id"] == "D1:C029"
            return detail

    registry = KnowledgeToolRegistry(_Catalog())
    results = registry.search_knowledge("社会行动四类型")

    assert results[0]["knowledge_id"] == "D1:C029"
    assert results[0]["evidence_status"] == "preview_unverified"
    assert "韦伯" in results[0]["excerpt"]
    assert registry.evidence["knowledge:D1:C029"].kind == "preview"


def test_read_preview_entry_returns_real_content_with_explicit_status() -> None:
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
    assert result["evidence_status"] == "preview_unverified"
    assert registry.evidence["knowledge:D1:C031"].kind == "preview"
