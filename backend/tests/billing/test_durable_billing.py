from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from qunxue_api.adapters.sqlite import durable_billing as billing
from qunxue_api.modules.billing import pricing


@pytest.fixture
def wallet(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/synthetic.db")
    with engine.begin() as c:
        c.execute(
            text(
                "CREATE TABLE credit_accounts (user_id TEXT PRIMARY KEY, balance "
                "INTEGER, updated_at TEXT)"
            )
        )
        c.execute(
            text(
                "CREATE TABLE credit_ledger (entry_id TEXT PRIMARY KEY, user_id TEXT, "
                "run_id TEXT UNIQUE, kind TEXT, points INTEGER, balance_after INTEGER, "
                "input_tokens INTEGER, output_tokens INTEGER, model TEXT, created_at "
                "TEXT)"
            )
        )
        c.execute(text("INSERT INTO credit_accounts VALUES ('user',10000,'')"))
    billing.create_billing_tables(engine)
    runtime = billing.DurableBilling(
        engine,
        price_book=pricing.PriceBook(credits_per_usd=10000, version="synthetic"),
        max_attempt_pico=10**11,
        max_operation_pico=10**11,
        daily_budget_pico=10**12,
        max_attempts=10,
    )
    yield runtime, engine
    engine.dispose()


def operation(runtime, run_id=None, user="user", exempt=False):
    return runtime.start(
        user_id=user, run_id=run_id or str(uuid4()), fingerprint="synthetic", exempt=exempt
    )


def success(runtime, run):
    attempt = runtime.before_attempt(
        run_id=run,
        endpoint_id="primary",
        model="gpt-6.1-sol",
        input_limit=1000,
        output_limit=100,
        request_hash="synthetic",
    )
    runtime.complete_attempt(
        attempt_id=attempt,
        input_tokens=1000,
        output_tokens=100,
        cache_read_tokens=200,
        cache_write_tokens=300,
        returned_model="gpt-6.1-sol",
        outcome="success",
    )
    runtime.finish(run_id=run, outcome="success")


def balance(engine):
    with engine.connect() as c:
        return c.scalar(text("SELECT balance FROM credit_accounts WHERE user_id='user'"))


def test_exact_fraction_accumulates_and_repeated_settlement_is_idempotent(wallet):
    runtime, engine = wallet
    for _ in range(10):
        run = operation(runtime)
        success(runtime, run)
        runtime.finish(run_id=run, outcome="success")
    assert balance(engine) == 9723
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM credit_ledger")) == 10


def test_concurrent_reservations_cannot_spend_same_balance(wallet):
    runtime, engine = wallet
    with engine.begin() as c:
        c.execute(text("UPDATE credit_accounts SET balance=1500 WHERE user_id='user'"))
    first = operation(runtime)
    second = operation(runtime)
    with pytest.raises(billing.BillingBudgetExceeded):
        operation(runtime)
    assert runtime.available_balance("user") == 0
    runtime.finish(run_id=first, outcome="cancelled")
    assert runtime.available_balance("user") == 1000
    runtime.finish(run_id=second, outcome="error")
    assert balance(engine) == 1500


def test_failed_finalization_refunds_whole_operation_and_keeps_cost(wallet):
    runtime, engine = wallet
    run = operation(runtime)
    success(runtime, run)
    runtime.finish(run_id=run, outcome="error")
    runtime.finish(run_id=run, outcome="error")
    assert balance(engine) == 10000
    with engine.connect() as c:
        assert c.scalar(text("SELECT sum(reference_cost_pico) FROM billing_attempts")) == 2770000000


def test_unknown_attempt_survives_restart_and_stale_recovery_as_operator_risk(wallet):
    runtime, engine = wallet
    run = operation(runtime)
    runtime.before_attempt(
        run_id=run,
        endpoint_id="primary",
        model="gpt-6.1-sol",
        input_limit=1000,
        output_limit=100,
        request_hash="synthetic",
    )
    runtime.recover_stale(before=datetime.now(UTC) + timedelta(days=1))
    assert balance(engine) == 10000
    assert runtime.operator_risk_pico() == 3500000000
    with pytest.raises(billing.BillingReplayBlocked):
        operation(runtime, run_id=run)
    runtime.finish(run_id=run, outcome="success")
    assert balance(engine) == 10000


def test_admin_exemption_still_records_cost_and_obeys_risk_budget(wallet):
    runtime, engine = wallet
    run = operation(runtime, exempt=True)
    success(runtime, run)
    assert balance(engine) == 10000
    assert runtime.operator_risk_pico() == 2770000000


def test_unknown_price_fails_before_any_attempt_is_sent(wallet):
    runtime, engine = wallet
    run = operation(runtime)
    with pytest.raises(pricing.UnknownPrice):
        runtime.before_attempt(
            run_id=run,
            endpoint_id="fallback",
            model="deepseek-flash",
            input_limit=1000,
            output_limit=100,
            request_hash="synthetic",
        )
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM billing_attempts")) == 0


def test_provider_model_change_is_recorded_and_stops_user_charge(wallet):
    runtime, engine = wallet
    run = operation(runtime)
    attempt = runtime.before_attempt(
        run_id=run,
        endpoint_id="primary",
        model="gpt-6.1-sol",
        input_limit=1000,
        output_limit=100,
        request_hash="synthetic",
    )
    with pytest.raises(billing.BillingRouteMismatch):
        runtime.complete_attempt(
            attempt_id=attempt,
            input_tokens=1000,
            output_tokens=100,
            returned_model="gpt-6-luna",
            outcome="success",
        )
    runtime.finish(run_id=run, outcome="success")
    assert balance(engine) == 10000
    with engine.connect() as c:
        assert c.scalar(text("SELECT reference_cost_pico FROM billing_attempts")) == 150000000


def test_overrun_retains_full_cost_and_waives_operation(wallet):
    runtime, engine = wallet
    run = operation(runtime)
    attempt = runtime.before_attempt(
        run_id=run,
        endpoint_id="primary",
        model="gpt-6.1-sol",
        input_limit=1000,
        output_limit=100,
        request_hash="synthetic",
    )
    with pytest.raises(billing.BillingBudgetExceeded):
        runtime.complete_attempt(
            attempt_id=attempt,
            input_tokens=1000,
            output_tokens=1000,
            returned_model="gpt-6.1-sol",
            outcome="success",
        )
    runtime.finish(run_id=run, outcome="success")
    assert balance(engine) == 10000
    with engine.connect() as c:
        assert c.scalar(text("SELECT reference_cost_pico FROM billing_attempts")) == 12000000000


def test_late_usage_after_error_never_recharges_the_user(wallet):
    runtime, engine = wallet
    run = operation(runtime)
    attempt = runtime.before_attempt(
        run_id=run,
        endpoint_id="primary",
        model="gpt-6.1-sol",
        input_limit=1000,
        output_limit=100,
        request_hash="synthetic",
    )
    runtime.finish(run_id=run, outcome="error")
    runtime.complete_attempt(
        attempt_id=attempt,
        input_tokens=1000,
        output_tokens=100,
        returned_model="gpt-6.1-sol",
        outcome="success",
    )
    runtime.finish(run_id=run, outcome="success")
    assert balance(engine) == 10000
    assert runtime.operator_risk_pico() == 3000000000


def test_unknown_returned_model_preserves_receipt_facts_pending_price(wallet):
    runtime, engine = wallet
    run = operation(runtime)
    attempt = runtime.before_attempt(
        run_id=run,
        endpoint_id="primary",
        model="gpt-6.1-sol",
        input_limit=1000,
        output_limit=100,
        request_hash="synthetic",
    )
    with pytest.raises(pricing.UnknownPrice):
        runtime.complete_attempt(
            attempt_id=attempt,
            input_tokens=20,
            output_tokens=10,
            returned_model="unconfigured-real-model",
            provider_response_id="synthetic-unpriced",
            outcome="success",
        )
    runtime.finish(run_id=run, outcome="error")
    with engine.connect() as c:
        row = c.execute(
            text(
                "SELECT "
                "input_tokens,output_tokens,returned_model,provider_response_id,usage_s"
                "tate,reference_cost_pico FROM billing_attempts"
            )
        ).one()
        assert row == (20, 10, "unconfigured-real-model", "synthetic-unpriced", "unpriced", None)
    assert balance(engine) == 10000


def test_independent_connections_reserve_without_overspending(wallet):
    from concurrent.futures import ThreadPoolExecutor

    runtime, engine = wallet
    with engine.begin() as c:
        c.execute(text("UPDATE credit_accounts SET balance=1000 WHERE user_id='user'"))

    def claim(_):
        try:
            return operation(runtime)
        except billing.BillingBudgetExceeded:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, range(2)))
    assert sum(c is not None for c in claims) == 1
    assert runtime.available_balance("user") == 0
    assert balance(engine) == 1000


def test_unpriced_service_tier_preserves_receipt_without_standard_user_charge(wallet):
    runtime, engine = wallet
    run = operation(runtime)
    attempt = runtime.before_attempt(
        run_id=run,
        endpoint_id="primary",
        model="gpt-6.1-sol",
        input_limit=1000,
        output_limit=100,
        request_hash="synthetic",
    )
    with pytest.raises(pricing.UnknownPrice):
        runtime.complete_attempt(
            attempt_id=attempt,
            input_tokens=5,
            output_tokens=1,
            returned_model="gpt-6.1-sol",
            returned_service_tier="priority",
            outcome="success",
        )
    runtime.finish(run_id=run, outcome="success")
    assert balance(engine) == 10000
    with engine.connect() as c:
        assert c.scalar(text("SELECT usage_state FROM billing_attempts")) == "unpriced"
        assert c.scalar(text("SELECT input_tokens FROM billing_attempts")) == 5


def test_failed_attempt_risk_uses_operator_budget_not_fallback_user_funds(wallet):
    runtime, engine = wallet
    with engine.begin() as c:
        c.execute(text("UPDATE credit_accounts SET balance=35 WHERE user_id='user'"))
    run = operation(runtime)
    failed = runtime.before_attempt(
        run_id=run,
        endpoint_id="primary",
        model="gpt-6.1-sol",
        input_limit=1000,
        output_limit=100,
        request_hash="synthetic",
    )
    runtime.complete_attempt(attempt_id=failed, outcome="error")
    retry = runtime.before_attempt(
        run_id=run,
        endpoint_id="fallback",
        model="gpt-6-luna",
        input_limit=1000,
        output_limit=100,
        request_hash="synthetic",
    )
    runtime.complete_attempt(
        attempt_id=retry,
        input_tokens=1000,
        output_tokens=100,
        returned_model="gpt-6-luna",
        outcome="success",
    )
    runtime.finish(run_id=run, outcome="success")
    assert balance(engine) == 34
    assert runtime.operator_risk_pico() == 3650000000
