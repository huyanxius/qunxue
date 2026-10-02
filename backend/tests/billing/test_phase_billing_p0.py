# ruff: noqa: F811
import os
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from billing_test_support import synthetic_billing_runtime
from sqlalchemy import text
from test_agent_conversation import _FakeAgentTools
from test_agent_memory import register
from test_application_metering import Runner
from test_durable_billing import balance, operation, wallet  # noqa: F401

from qunxue_api.adapters.model.billing_operations import SqliteBillingOperations
from qunxue_api.adapters.model.metering import current_operation
from qunxue_api.adapters.sqlite.agent_conversation_repository import SqliteConversationRepository
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.application.disciplinary_agent import DisciplinaryAgentApplication
from qunxue_api.modules.agent_conversation import AgentResearchEvent, ConversationService
from qunxue_api.modules.billing import BillingBudgetExceeded, BillingReplayBlocked


def record(runtime, run):
    attempt = runtime.before_attempt(
        run_id=run,
        endpoint_id="synthetic",
        model="gpt-6.1-sol",
        input_limit=1000,
        output_limit=100,
        request_hash=str(uuid4()),
    )
    runtime.complete_attempt(
        attempt_id=attempt,
        input_tokens=1000,
        output_tokens=100,
        returned_model="gpt-6.1-sol",
        outcome="success",
    )


def test_pause_resume_only_charges_new_usage_and_refunds_every_stage(wallet):
    runtime, engine = wallet
    run = operation(runtime)
    record(runtime, run)
    runtime.finish(run_id=run, outcome="paused")
    assert balance(engine) == 9970
    assert runtime.available_balance("user") == 9970
    runtime.start(user_id="user", run_id=run, fingerprint="confirmed", resume=True)
    record(runtime, run)
    runtime.finish(run_id=run, outcome="success")
    runtime.finish(run_id=run, outcome="success")
    assert balance(engine) == 9940
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM credit_ledger")) == 2
    runtime.finish(run_id=run, outcome="error")
    runtime.finish(run_id=run, outcome="error")
    assert balance(engine) == 10000
    assert runtime.operator_risk_pico() == 6 * 10**9


def test_pause_continuation_keeps_budget_attempt_limit_and_price_snapshot(wallet):
    runtime, engine = wallet
    runtime.max_operation_pico = 5 * 10**9
    run = operation(runtime)
    record(runtime, run)
    runtime.finish(run_id=run, outcome="paused")
    old_book = runtime.book
    runtime.book = replace(old_book, credits_per_usd=99999, version="later")
    runtime.start(user_id="user", run_id=run, fingerprint="confirmation", resume=True)
    with engine.connect() as c:
        snapshot = c.scalar(text("SELECT price_json FROM billing_operations"))
    assert '"version": "synthetic"' in snapshot
    with pytest.raises(BillingBudgetExceeded):
        record(runtime, run)
    runtime.finish(run_id=run, outcome="error")
    assert balance(engine) == 10000


@pytest.mark.parametrize("user,resume", [("user", False), ("different-user", True)])
def test_only_an_owned_paused_operation_can_continue(wallet, user, resume):
    runtime, _ = wallet
    run = operation(runtime)
    runtime.finish(run_id=run, outcome="paused")
    with pytest.raises(BillingReplayBlocked):
        runtime.start(user_id=user, run_id=run, fingerprint="same", resume=resume)


def test_repeated_confirmation_and_terminal_replay_cannot_send_again(wallet):
    runtime, _ = wallet
    run = operation(runtime)
    runtime.finish(run_id=run, outcome="paused")
    runtime.start(user_id="user", run_id=run, fingerprint="same", resume=True)
    with pytest.raises(BillingReplayBlocked):
        runtime.start(user_id="user", run_id=run, fingerprint="same", resume=True)
    runtime.finish(run_id=run, outcome="success")
    with pytest.raises(BillingReplayBlocked):
        runtime.start(user_id="user", run_id=run, fingerprint="same", resume=True)


def test_continuation_cannot_reset_maximum_attempts(wallet):
    runtime, _ = wallet
    runtime.max_attempts = 1
    run = operation(runtime)
    record(runtime, run)
    runtime.finish(run_id=run, outcome="paused")
    runtime.start(user_id="user", run_id=run, fingerprint="confirmed", resume=True)
    with pytest.raises(BillingBudgetExceeded):
        record(runtime, run)


def test_unknown_usage_cannot_be_presented_as_a_successful_pause(wallet):
    from qunxue_api.adapters.model.metering import ModelDeliveryRejected, OperationScope

    runtime, engine = wallet
    with (
        pytest.raises(ModelDeliveryRejected),
        OperationScope(runtime, user_id="user", run_id=uuid4(), fingerprint="synthetic") as scope,
    ):
        runtime.before_attempt(
            run_id=scope.run_id,
            endpoint_id="synthetic",
            model="gpt-6-luna",
            input_limit=100,
            output_limit=100,
            request_hash="synthetic",
        )
        scope.finish("paused")
    assert balance(engine) == 10000
    assert runtime.operator_risk_pico() > 0


class Planner(Runner):
    def prepare_research(self, *, prompt, conversation, tools, on_event):
        scope = current_operation(required=True)
        record(scope.runtime, scope.run_id)
        on_event(
            AgentResearchEvent(
                kind="plan", payload={"title": "synthetic", "steps": ["synthetic step"]}
            )
        )


def build_application(database, session, *, runner=None):
    runtime = synthetic_billing_runtime(database.engine)
    repository = SqliteConversationRepository(session)
    operations = SqliteBillingOperations(database, runtime).bound_to(session)
    return (
        DisciplinaryAgentApplication(
            conversations=ConversationService(repository),
            runner=runner or Planner(),
            tools_factory=_FakeAgentTools,
            billing=operations,
            atomic=operations.atomic,
            rollback=session.rollback,
        ),
        runtime,
        repository,
    )


def test_real_sqlite_planning_confirmation_research_and_replay(plain_client):
    user = UUID(register(plain_client))
    database = plain_client.app.state.database
    with database.session() as session:
        app, runtime, _ = build_application(database, session)
        args = dict(
            user_id=user,
            conversation_id=None,
            prompt="synthetic",
            idempotency_key="phase",
            mode="deep_research",
        )
        planned = app.run_turn(**args)
        assert planned.pending_research["state"] == "awaiting_plan_confirmation"
        paused_balance = session.scalar(
            text("SELECT balance FROM credit_accounts WHERE user_id=:u"), {"u": str(user)}
        )
        assert paused_balance == 2970
        confirmed = app.run_turn(
            **args, deep_research_run_id=planned.run_id, deep_research_action="confirm"
        )
        assert confirmed.turn is not None and confirmed.run_id == planned.run_id
        replay = app.run_turn(
            **args, deep_research_run_id=planned.run_id, deep_research_action="confirm"
        )
        assert replay.replayed
        assert (
            session.scalar(
                text("SELECT balance FROM credit_accounts WHERE user_id=:u"), {"u": str(user)}
            )
            == 2878
        )
        assert session.scalar(text("SELECT count(*) FROM billing_attempts")) == 2
        assert runtime.available_balance(user) == 2878


def crash_delivery(database_url, user_id, stage):
    database = Database(database_url)
    with database.session() as session:
        app, runtime, repository = build_application(database, session, runner=Runner())
        original_finish, original_commit = runtime.finish, repository.commit

        def finish(**kwargs):
            if kwargs["outcome"] == "success" and stage == "before_settlement":
                os._exit(73)
            original_finish(**kwargs)
            if kwargs["outcome"] == "success" and stage == "after_settlement":
                os._exit(73)

        def commit():
            original_commit()
            if stage == "after_commit" and session.scalar(
                text("SELECT count(*) FROM agent_runs WHERE status='completed'")
            ):
                os._exit(73)

        runtime.finish, repository.commit = finish, commit
        app.run_turn(
            user_id=UUID(user_id), conversation_id=None, prompt="synthetic", idempotency_key="crash"
        )


@pytest.mark.parametrize("stage", ["before_settlement", "after_settlement", "after_commit"])
def test_process_exit_cannot_save_success_without_financial_settlement(plain_client, stage):
    user = register(plain_client)
    database = plain_client.app.state.database
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            "from test_phase_billing_p0 import crash_delivery; "
            "import sys; crash_delivery(*sys.argv[1:])",
            database.engine.url.render_as_string(),
            user,
            stage,
        ],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        timeout=20,
    )
    assert process.returncode == 73, process.stderr.decode()
    with database.engine.connect() as c:
        saved = c.scalar(text("SELECT count(*) FROM agent_runs WHERE status='completed'"))
        charged = c.scalar(
            text("SELECT balance FROM credit_accounts WHERE user_id=:u"), {"u": user}
        )
        financial = c.scalar(text("SELECT status FROM billing_operations"))
    assert (saved, charged, financial) == (
        (1, 2908, "success") if stage == "after_commit" else (0, 3000, "active")
    )
    runtime = synthetic_billing_runtime(database.engine)
    runtime.recover_stale(before=datetime.now(UTC) + timedelta(days=1))
    assert runtime.available_balance(user) == charged


def test_repeated_business_commit_failure_still_refunds_and_releases_hold(plain_client):
    user = UUID(register(plain_client))
    database = plain_client.app.state.database
    with database.session() as session:
        app, runtime, repository = build_application(database, session, runner=Runner())
        original_finish, original_commit = runtime.finish, repository.commit
        fail_commits = False

        def finish(**kwargs):
            nonlocal fail_commits
            result = original_finish(**kwargs)
            if kwargs["outcome"] == "success":
                fail_commits = True
            return result

        def commit():
            if fail_commits:
                raise RuntimeError("synthetic repeated business commit failure")
            original_commit()

        runtime.finish, repository.commit = finish, commit
        with pytest.raises(RuntimeError, match="synthetic repeated"):
            app.run_turn(
                user_id=user,
                conversation_id=None,
                prompt="synthetic",
                idempotency_key="commit-failure",
            )
        session.rollback()
        assert session.scalar(text("SELECT count(*) FROM agent_runs WHERE status='completed'")) == 0
        assert session.scalar(text("SELECT status FROM billing_operations")) == "error"
        assert session.scalar(text("SELECT hold_points FROM billing_operations")) == 0
        assert runtime.available_balance(user) == 3000
        assert runtime.operator_risk_pico() > 0
