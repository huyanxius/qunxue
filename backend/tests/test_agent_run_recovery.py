"""Interrupted requests stay durable and cannot change identity when resumed."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest

from qunxue_api.application.disciplinary_agent import DisciplinaryAgentApplication
from qunxue_api.modules.agent_conversation import (
    AgentInterrupted,
    AgentResearchEvent,
    AgentRunResult,
    ConversationNotFound,
    ConversationService,
)


class Tools:
    release = SimpleNamespace(knowledge_release_id="release-a")
    evidence = {}
    web_search_enabled = False

    def enable_web_search(self):
        self.web_search_enabled = True


class Runner:
    def __init__(self):
        self.interrupt = True

    def run_stream(self, *, prompt, conversation, tools, on_delta, **kwargs):
        on_delta("保存下来的半段")
        if self.interrupt:
            raise AgentInterrupted("stopped")
        return AgentRunResult(
            answer=f"{prompt}|web={tools.web_search_enabled}|history={len(conversation)}",
            citations=(),
            release_id="release-a",
            provider="test",
            model="test",
        )


def application():
    runner = Runner()
    service = ConversationService.in_memory()
    return (
        DisciplinaryAgentApplication(
            conversations=service,
            runner=runner,
            tools_factory=Tools,
        ),
        runner,
        service,
    )


def interrupted(app, key="first"):
    with pytest.raises(AgentInterrupted):
        app.run_turn(
            user_id=UUID(int=1),
            conversation_id=None,
            prompt="原始问题",
            idempotency_key=key,
            web_search=True,
            on_delta=lambda _: None,
        )
    return app.find_run(user_id=UUID(int=1), idempotency_key=key)


def test_partial_input_survives_reload_without_becoming_a_completed_turn():
    app, _, _ = application()
    run = interrupted(app)
    saved = app.get_conversation(user_id=UUID(int=1), conversation_id=run.conversation_id)
    assert saved.turns == ()
    assert len(saved.unfinished_runs) == 1
    pending = saved.unfinished_runs[0]
    assert pending.partial_answer == "保存下来的半段"
    assert pending.request_snapshot["message"] == "原始问题"
    assert pending.request_snapshot["web_search"] is True
    assert pending.status == "interrupted"


def test_resuming_uses_original_snapshot_and_keeps_other_completed_turns():
    app, runner, _ = application()
    run = interrupted(app)
    runner.interrupt = False
    app.run_turn(
        user_id=UUID(int=1),
        conversation_id=run.conversation_id,
        prompt="新问题",
        idempotency_key="second",
        on_delta=lambda _: None,
    )
    saved = app.get_conversation(user_id=UUID(int=1), conversation_id=run.conversation_id)
    assert len(saved.unfinished_runs) == 1
    resumed = app.run_turn(
        user_id=UUID(int=1),
        conversation_id=run.conversation_id,
        prompt="篡改的问题",
        idempotency_key="first",
        web_search=False,
        on_delta=lambda _: None,
    )
    assert resumed.run_id == run.run_id
    assert resumed.result.answer == "原始问题|web=True|history=1"
    assert len(resumed.conversation.turns) == 2
    assert resumed.conversation.unfinished_runs == ()


def test_completed_key_cannot_replay_into_a_different_conversation():
    app, runner, service = application()
    runner.interrupt = False
    app.run_turn(
        user_id=UUID(int=1),
        conversation_id=None,
        prompt="私有问题",
        idempotency_key="first",
        on_delta=lambda _: None,
    )
    other = service.create_conversation(user_id=UUID(int=1), title="另一段")
    with pytest.raises(ValueError, match="another conversation"):
        app.run_turn(
            user_id=UUID(int=1),
            conversation_id=other.conversation_id,
            prompt="错误重试",
            idempotency_key="first",
            on_delta=lambda _: None,
        )


def test_cancel_during_planning_does_not_publish_a_pending_plan():
    app, _, _ = application()
    cancelled = False

    class Planner(Runner):
        def prepare_research(self, *, on_event, **kwargs):
            nonlocal cancelled
            cancelled = True
            on_event(AgentResearchEvent(kind="plan", payload={"title": "计划", "steps": ["查证"]}))

    app._runner = Planner()
    with pytest.raises(AgentInterrupted):
        app.run_turn(
            user_id=UUID(int=1),
            conversation_id=None,
            prompt="原始问题",
            idempotency_key="plan",
            mode="deep_research",
            on_delta=lambda _: None,
            is_cancelled=lambda: cancelled,
        )
    assert app.find_run(user_id=UUID(int=1), idempotency_key="plan").status == "interrupted"


def test_memory_initialization_failure_finishes_run():
    app, _, _ = application()

    def broken(**kwargs):
        raise RuntimeError("memory unavailable")

    app._memory_tools_factory = broken
    with pytest.raises(RuntimeError, match="memory unavailable"):
        app.run_turn(
            user_id=UUID(int=1),
            conversation_id=None,
            prompt="原始问题",
            idempotency_key="broken",
            on_delta=lambda _: None,
        )
    assert app.find_run(user_id=UUID(int=1), idempotency_key="broken").status == "failed"


def test_expired_run_reopens_as_interrupted_and_old_worker_cannot_finish_it():
    app, _, service = application()
    run = interrupted(app)
    repository = service._repository
    repository.runs[run.run_id] = replace(
        run,
        status="running",
        lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    saved = app.get_conversation(user_id=UUID(int=1), conversation_id=run.conversation_id)
    assert saved.unfinished_runs[0].status == "interrupted"
    assert saved.unfinished_runs[0].partial_answer == "保存下来的半段"


def test_stop_is_owned_and_durable():
    app, _, service = application()
    run = interrupted(app)
    service._repository.runs[run.run_id] = replace(run, status="running")
    with pytest.raises(ConversationNotFound):
        app.request_cancel(user_id=UUID(int=2), run_id=run.run_id)
    stopped = app.request_cancel(user_id=UUID(int=1), run_id=run.run_id)
    assert stopped.cancel_requested is True
    assert app.heartbeat(user_id=UUID(int=1), run_id=run.run_id) is True


def test_resume_supplies_prior_progress_and_uses_one_stable_turn_identity():
    app, _, _ = application()
    bound_turns = []

    class ContextTools(Tools):
        def bind_agent_context(self, *, agent_turn_id, **kwargs):
            bound_turns.append(agent_turn_id)

    class ContextRunner(Runner):
        def run_stream(self, *, tools, **kwargs):
            if not self.interrupt:
                assert tools.agent_run_checkpoint["partial_answer"] == "保存下来的半段"
            return super().run_stream(tools=tools, **kwargs)

    app._tools_factory = ContextTools
    app._runner = ContextRunner()
    run = interrupted(app)
    app._runner.interrupt = False
    result = app.run_turn(
        user_id=UUID(int=1),
        conversation_id=run.conversation_id,
        prompt="原始问题",
        idempotency_key="first",
        on_delta=lambda _: None,
    )
    assert bound_turns[0] == bound_turns[1] == result.turn.turn_id


def test_planner_model_is_cancelled_before_its_response():
    import asyncio
    import threading

    from pydantic_ai.models.function import FunctionModel

    from qunxue_api.adapters.research_agent.pydantic_runner import PydanticAIKnowledgeRunner

    cancel = threading.Event()
    ended = threading.Event()

    async def slow_model(messages, info):
        cancel.set()
        try:
            await asyncio.sleep(2)
            raise AssertionError("planner response should not be awaited after stop")
        finally:
            ended.set()

    runner = PydanticAIKnowledgeRunner(
        base_url="http://model.invalid/v1", api_key="test", model="test", timeout_seconds=5
    )
    with (
        runner._planner_agent.override(model=FunctionModel(slow_model)),
        pytest.raises(AgentInterrupted),
    ):
        runner.prepare_research(
            prompt="研究社区",
            conversation=(),
            tools=Tools(),
            on_event=lambda _: None,
            is_cancelled=cancel.is_set,
        )
    assert ended.is_set()


def test_resume_does_not_repeat_successful_identical_write_tool():
    from qunxue_api.adapters.research_agent.pydantic_runner import PydanticAIKnowledgeRunner

    class MutatingTools(Tools):
        writes = 0
        agent_run_checkpoint = {
            "tool_summary": [
                {
                    "tool": "propose_analysis_memo",
                    "phase": "finished",
                    "call_id": "old-call",
                    "input": {"title": "原提案"},
                    "output": {"candidate_id": "saved-candidate"},
                }
            ]
        }

        def propose_analysis_memo(self, **kwargs):
            self.writes += 1
            return {"candidate_id": "new-candidate"}

    tools = MutatingTools()
    runner = PydanticAIKnowledgeRunner(
        base_url="http://model.invalid/v1", api_key="test", model="test", timeout_seconds=5
    )
    ctx = SimpleNamespace(deps=tools, tool_call_id="different-new-call")
    result = runner._run_analysis_tool(
        ctx, "propose_analysis_memo", {"title": "原提案"}, "生成候选", candidate=True
    )
    assert result == {"candidate_id": "saved-candidate"}
    assert tools.writes == 0
    changed = runner._run_analysis_tool(
        ctx, "propose_analysis_memo", {"title": "更新提案"}, "生成候选", candidate=True
    )
    assert changed == {"candidate_id": "new-candidate"}
    assert tools.writes == 1


def registered_user(client):
    response = client.post(
        "/api/session/register",
        json={
            "email": "recovery@example.com",
            "password": "password-123",
            "display_name": "恢复测试",
        },
        headers={"Idempotency-Key": "recovery-user"},
    )
    assert response.status_code == 201
    return UUID(response.json()["user"]["user_id"])


def test_sqlite_request_committed_before_started_and_reload_keeps_partial(client):
    from qunxue_api.adapters.sqlite.agent_conversation_repository import (
        SqliteConversationRepository,
    )

    user_id = registered_user(client)
    database = client.app.state.database
    with database.session() as session:
        app = DisciplinaryAgentApplication(
            conversations=ConversationService(SqliteConversationRepository(session)),
            runner=Runner(),
            tools_factory=Tools,
        )

        def started(run_id, conversation_id, replayed, **kwargs):
            with database.session() as other:
                stored = SqliteConversationRepository(other).find_run_by_id(
                    user_id=user_id, run_id=run_id
                )
                assert stored.request_snapshot["message"] == "持久化问题"
                assert stored.status == "running"

        with pytest.raises(AgentInterrupted):
            app.run_turn(
                user_id=user_id,
                conversation_id=None,
                prompt="持久化问题",
                idempotency_key="sqlite-recovery",
                on_delta=lambda _: None,
                on_run_started=started,
            )
        run = app.find_run(user_id=user_id, idempotency_key="sqlite-recovery")
    with database.session() as session:
        restored = SqliteConversationRepository(session).get(
            user_id=user_id, conversation_id=run.conversation_id
        )
        assert restored.unfinished_runs[0].partial_answer == "保存下来的半段"
        assert restored.turns == ()


def test_sqlite_old_lease_cannot_checkpoint_or_finish_new_attempt(client):
    from qunxue_api.adapters.sqlite.agent_conversation_repository import (
        SqliteConversationRepository,
    )

    user_id = registered_user(client)
    with client.app.state.database.session() as session:
        repository = SqliteConversationRepository(session)
        service = ConversationService(repository)
        conversation = service.create_conversation(user_id=user_id, title="恢复")
        old = service.start_run(
            user_id=user_id,
            conversation_id=conversation.conversation_id,
            idempotency_key="old-lease",
            knowledge_release_id="release-a",
            request_snapshot={"message": "保持身份"},
        )
        repository.finish_run(run_id=old.run_id, status="interrupted", lease_token=old.lease_token)
        current = service.start_run(
            user_id=user_id,
            conversation_id=conversation.conversation_id,
            idempotency_key="old-lease",
            knowledge_release_id="release-a",
        )
        assert current.lease_token != old.lease_token
        assert (
            repository.checkpoint_run(
                user_id=user_id,
                run_id=old.run_id,
                lease_token=old.lease_token,
                partial_answer="陈旧输出",
            )
            is False
        )
        repository.finish_run(run_id=old.run_id, status="completed", lease_token=old.lease_token)
        actual = repository.find_run_by_id(user_id=user_id, run_id=old.run_id)
        assert actual.status == "running"
        assert actual.partial_answer == ""


def test_unfinished_deleted_material_text_cannot_reappear_on_reload_or_resume(client):
    from qunxue_api.adapters.sqlite.agent_conversation_repository import (
        SqliteConversationRepository,
    )
    from qunxue_api.modules.agent_conversation import (
        AgentMaterialAttachment,
        ResearchMaterialCitationUnavailable,
    )

    user_id = registered_user(client)
    with client.app.state.database.session() as session:
        repository = SqliteConversationRepository(session)
        service = ConversationService(repository)
        conversation = service.create_conversation(user_id=user_id, title="材料恢复")
        run = service.start_run(
            user_id=user_id,
            conversation_id=conversation.conversation_id,
            idempotency_key="deleted-source",
            knowledge_release_id="release-a",
            material_attachments=(AgentMaterialAttachment(UUID(int=800), UUID(int=801)),),
            request_snapshot={"message": "概括文件", "material_ids": [str(UUID(int=800))]},
        )
        repository.checkpoint_run(
            user_id=user_id,
            run_id=run.run_id,
            lease_token=run.lease_token,
            partial_answer="已删除原文secret",
            tool_summary=(
                {
                    "tool": "propose_analysis_memo",
                    "phase": "finished",
                    "input": {"content": "已删除原文secret"},
                    "output": {"candidate_id": "saved", "content": "已删除原文secret"},
                },
            ),
        )
        repository.finish_run(run_id=run.run_id, status="interrupted")
        repository.commit()
    with client.app.state.database.session() as session:
        repository = SqliteConversationRepository(session)
        restored = repository.get(user_id=user_id, conversation_id=run.conversation_id)
        assert "secret" not in repr(restored.unfinished_runs)
        app = DisciplinaryAgentApplication(
            conversations=ConversationService(repository), runner=Runner(), tools_factory=Tools
        )
        with pytest.raises(ResearchMaterialCitationUnavailable):
            app.run_turn(
                user_id=user_id,
                conversation_id=run.conversation_id,
                prompt="概括文件",
                idempotency_key="deleted-source",
                on_delta=lambda _: None,
            )


def test_cancel_monitor_does_not_read_shared_session_while_tool_is_active():
    import time

    from qunxue_api.modules.agent_conversation import AgentToolEvent

    app, _, service = application()
    repository = service._repository
    original_lookup = repository.find_run_by_id
    tool_busy = False

    def guarded_lookup(**kwargs):
        if tool_busy:
            raise RuntimeError("shared session accessed during tool transaction")
        return original_lookup(**kwargs)

    repository.find_run_by_id = guarded_lookup

    class ToolRunner(Runner):
        def run_stream(self, *, on_tool_event, is_cancelled, **kwargs):
            nonlocal tool_busy
            on_tool_event(AgentToolEvent(tool="write", phase="started", call_id="active"))
            tool_busy = True
            try:
                time.sleep(0.21)
                assert is_cancelled() is False
            finally:
                tool_busy = False
                on_tool_event(AgentToolEvent(tool="write", phase="finished", call_id="active"))
            self.interrupt = False
            return super().run_stream(**kwargs)

    app._runner = ToolRunner()
    result = app.run_turn(
        user_id=UUID(int=1),
        conversation_id=None,
        prompt="完成工具",
        idempotency_key="active-tool",
        on_delta=lambda _: None,
    )
    assert result.turn.user_message.content == "完成工具"


def test_two_sessions_cannot_both_claim_the_same_interrupted_run(client):
    from qunxue_api.adapters.sqlite.agent_conversation_model import AgentRunRow
    from qunxue_api.adapters.sqlite.agent_conversation_repository import (
        SqliteConversationRepository,
    )
    from qunxue_api.modules.agent_conversation import AgentRun, RunAlreadyActive

    user_id = registered_user(client)
    database = client.app.state.database
    with database.session() as session:
        service = ConversationService(SqliteConversationRepository(session))
        conversation = service.create_conversation(user_id=user_id, title="竞争恢复")
        old = service.start_run(
            user_id=user_id,
            conversation_id=conversation.conversation_id,
            idempotency_key="racing-resume",
            knowledge_release_id="release-a",
        )
        service.finish_run(run_id=old.run_id, status="interrupted")
        service.commit()
    with database.session() as first_session, database.session() as second_session:
        first_copy = first_session.get(AgentRunRow, str(old.run_id))
        second_copy = second_session.get(AgentRunRow, str(old.run_id))
        assert first_copy.status == second_copy.status == "interrupted"
        request = AgentRun(
            run_id=UUID(int=990),
            user_id=user_id,
            conversation_id=conversation.conversation_id,
            idempotency_key="racing-resume",
            status="running",
        )
        first = SqliteConversationRepository(first_session)
        second = SqliteConversationRepository(second_session)
        claimed = first.start_run(request)
        first.commit()
        with pytest.raises(RunAlreadyActive):
            second.start_run(replace(request, lease_token="losing-lease"))
        with database.session() as check:
            actual = SqliteConversationRepository(check).find_run_by_id(
                user_id=user_id, run_id=old.run_id
            )
            assert actual.lease_token == claimed.lease_token


def test_sqlite_pause_resume_then_replay_charges_account_once(client):
    from sqlalchemy import select

    from qunxue_api.adapters.sqlite.agent_conversation_repository import (
        SqliteConversationRepository,
    )
    from qunxue_api.adapters.sqlite.billing_model import CreditAccountRow, CreditLedgerRow
    from qunxue_api.adapters.sqlite.billing_repository import SqliteCreditRepository
    from qunxue_api.modules.billing import CreditService

    user_id = registered_user(client)
    runner = Runner()
    with client.app.state.database.session() as session:
        credits = CreditService(SqliteCreditRepository(session))
        before = credits.summary(user_id=user_id).balance
        app = DisciplinaryAgentApplication(
            conversations=ConversationService(SqliteConversationRepository(session)),
            runner=runner,
            tools_factory=Tools,
            credits=credits,
        )
        with pytest.raises(AgentInterrupted):
            app.run_turn(
                user_id=user_id,
                conversation_id=None,
                prompt="收费恢复",
                idempotency_key="charged-once",
                on_delta=lambda _: None,
            )
        run = app.find_run(user_id=user_id, idempotency_key="charged-once")
        account = session.get(CreditAccountRow, str(user_id), populate_existing=True)
        assert account.balance == before
        assert account.active_run_id is None

        class UsageRunner(Runner):
            def run_stream(self, **kwargs):
                self.interrupt = False
                return replace(super().run_stream(**kwargs), input_tokens=1, output_tokens=1)

        app._runner = UsageRunner()
        completed = app.run_turn(
            user_id=user_id,
            conversation_id=run.conversation_id,
            prompt="收费恢复",
            idempotency_key="charged-once",
            on_delta=lambda _: None,
        )
        replayed = app.run_turn(
            user_id=user_id,
            conversation_id=run.conversation_id,
            prompt="收费恢复",
            idempotency_key="charged-once",
            on_delta=lambda _: None,
        )
        assert completed.run_id == replayed.run_id == run.run_id
        account = session.get(CreditAccountRow, str(user_id), populate_existing=True)
        assert account.balance == before - 2
        assert account.active_run_id is None
        usage = session.scalars(
            select(CreditLedgerRow).where(CreditLedgerRow.run_id == str(run.run_id))
        ).all()
        assert len(usage) == 1
        assert usage[0].points == -2


def test_persisted_stop_wins_when_received_just_before_final_commit():
    app, _, _ = application()
    run_id = None

    def started(value, *_):
        nonlocal run_id
        run_id = value

    class CompletingRunner(Runner):
        def run_stream(self, **kwargs):
            self.interrupt = False
            result = super().run_stream(**kwargs)
            app.request_cancel(user_id=UUID(int=1), run_id=run_id)
            return result

    app._runner = CompletingRunner()
    with pytest.raises(AgentInterrupted):
        app.run_turn(
            user_id=UUID(int=1),
            conversation_id=None,
            prompt="停止竞态",
            idempotency_key="stop-before-commit",
            on_delta=lambda _: None,
            on_run_started=started,
        )
    run = app.find_run(user_id=UUID(int=1), idempotency_key="stop-before-commit")
    assert run.status == "interrupted"
    assert (
        app.get_conversation(user_id=UUID(int=1), conversation_id=run.conversation_id).turns == ()
    )
