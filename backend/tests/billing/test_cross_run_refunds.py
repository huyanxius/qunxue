# ruff: noqa: F811
"""Synthetic SQLite refunds: rounding belongs to the account, never to one run."""

from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from threading import Barrier
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from sqlalchemy import text
from test_durable_billing import wallet  # noqa: F401

from qunxue_api.modules.billing import PICO_USD, PriceBook, Tariff


def start(runtime, mode, units, *, status="success", exempt=False):
    # The three snapshots deliberately differ. A refund must remove the stored
    # exact contribution, without translating it through the current price/FX.
    tokens, fx = {6: (3, 2000000), 4: (1, 4000000), 14: (7, 2000000)}.get(units, (2, 3000000))
    if mode == "legacy":
        tokens, conversion, rate = units, {"credits_per_usd": 10000}, 10000000
    else:
        if mode == "retail_odd":
            fx += tokens
        conversion = dict(
            credits_per_usd=None,
            points_per_cny=100,
            retail_rate_ppm=100000,
            fx_cny_per_usd_micro=fx,
            fx_snapshot_id=f"synthetic-{fx}",
            fx_as_of="2026-10-02T00:00:00+00:00",
            fx_source="synthetic-test",
        )
        rate = 10000000003 if mode == "retail_odd" else 10000000000
    runtime.book = PriceBook(
        **conversion,
        version=f"synthetic-{mode}-{uuid4()}",
        tariffs={"synthetic-model": Tariff(rate, rate, rate, 0, long_threshold=None)},
    )
    run = runtime.start(user_id="user", run_id=str(uuid4()), fingerprint="synthetic", exempt=exempt)
    add_usage(runtime, run, tokens)
    if status is not None:
        runtime.finish(run_id=run, outcome=status)
    return run


def add_usage(runtime, run, tokens):
    attempt = runtime.before_attempt(
        run_id=run,
        endpoint_id="synthetic",
        model="synthetic-model",
        input_limit=tokens,
        output_limit=1,
        request_hash=str(uuid4()),
    )
    runtime.complete_attempt(
        attempt_id=attempt,
        input_tokens=tokens,
        output_tokens=0,
        returned_model="synthetic-model",
        outcome="success",
    )


def assert_consistent(engine):
    with engine.connect() as connection:
        contributions = connection.scalars(
            text("SELECT credit_pico FROM billing_operations WHERE user_id='user' AND exempt=0")
        ).all()
        exact = sum((Fraction(value) for value in contributions), Fraction(0))
        stored = connection.scalar(
            text("SELECT total_credit_pico FROM billing_precision WHERE user_id='user'")
        )
        assert Fraction(stored or 0) == exact
        balance = connection.scalar(
            text("SELECT balance FROM credit_accounts WHERE user_id='user'")
        )
        assert balance == 10000 - exact // PICO_USD
        assert (
            connection.scalar(text("SELECT coalesce(sum(points),0) FROM credit_ledger"))
            == balance - 10000
        )
        return balance


def refund_points(engine, run):
    ident = str(uuid5(NAMESPACE_URL, f"billing-refund:{run}"))
    with engine.connect() as connection:
        return connection.scalar(
            text("SELECT points FROM credit_ledger WHERE entry_id=:id"), {"id": ident}
        )


@pytest.mark.parametrize("mode", ["legacy", "retail", "retail_odd"])
def test_paused_fraction_refund_cannot_charge_same_carry_twice(wallet, mode):
    runtime, engine = wallet
    a = start(runtime, mode, 6, status="paused")
    start(runtime, mode, 6)
    assert assert_consistent(engine) == 9999
    runtime.finish(run_id=a, outcome="cancelled")
    assert assert_consistent(engine) == 10000
    assert refund_points(engine, a) == 1
    start(runtime, mode, 4)
    assert assert_consistent(engine) == 9999


@pytest.mark.parametrize("mode", ["legacy", "retail", "retail_odd"])
@pytest.mark.parametrize("order", [(0, 1), (1, 0)])
def test_both_refund_orders_replays_and_later_usage_preserve_exact_total(wallet, mode, order):
    runtime, engine = wallet
    runs = [start(runtime, mode, 6, status="paused"), start(runtime, mode, 6)]
    runtime.finish(run_id=runs[order[0]], outcome="error")
    assert assert_consistent(engine) == 10000
    c = start(runtime, mode, 4)
    assert assert_consistent(engine) == 9999
    runtime.finish(run_id=runs[order[1]], outcome="cancelled")
    assert assert_consistent(engine) == 10000
    for _ in range(3):
        for run in runs:
            for outcome in ("error", "cancelled", "success", "paused"):
                runtime.finish(run_id=run, outcome=outcome)
                assert assert_consistent(engine) == 10000
    start(runtime, mode, 6)
    assert assert_consistent(engine) == 9999
    runtime.finish(run_id=c, outcome="error")
    assert assert_consistent(engine) == 10000
    with engine.connect() as connection:
        remaining = connection.scalar(
            text("SELECT run_id FROM billing_operations WHERE status='success'")
        )
    runtime.finish(run_id=remaining, outcome="error")
    assert assert_consistent(engine) == 10000


@pytest.mark.parametrize("mode", ["legacy", "retail", "retail_odd"])
def test_refund_ledger_uses_account_adjustment_instead_of_historical_run_charge(wallet, mode):
    runtime, engine = wallet
    a = start(runtime, mode, 14, status="paused")
    start(runtime, mode, 6)
    assert assert_consistent(engine) == 9998
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT charged_points FROM billing_operations WHERE run_id=:id"), {"id": a}
            )
            == 1
        )
    runtime.finish(run_id=a, outcome="error")
    assert assert_consistent(engine) == 10000
    assert refund_points(engine, a) == 2
    start(runtime, mode, 4)
    assert assert_consistent(engine) == 9999


@pytest.mark.parametrize("mode", ["legacy", "retail"])
def test_interleaved_pause_resumes_can_transfer_more_than_one_integer_carry(wallet, mode):
    runtime, engine = wallet
    a = start(runtime, mode, 4, status="paused")
    others = [start(runtime, mode, 6)]
    for _ in range(2):
        runtime.start(user_id="user", run_id=a, fingerprint="continued", resume=True)
        add_usage(runtime, a, 4 if mode == "legacy" else 1)
        runtime.finish(run_id=a, outcome="paused")
        others.append(start(runtime, mode, 6))
        assert_consistent(engine)
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT charged_points FROM billing_operations WHERE run_id=:id"), {"id": a}
            )
            == 0
        )
    assert assert_consistent(engine) == 9997
    runtime.finish(run_id=a, outcome="cancelled")
    assert assert_consistent(engine) == 9999
    assert refund_points(engine, a) == 2
    for run in reversed(others):
        runtime.finish(run_id=run, outcome="error")
        assert_consistent(engine)
    assert assert_consistent(engine) == 10000


@pytest.mark.parametrize("mode", ["legacy", "retail"])
def test_delivery_guard_failure_uses_same_refund_rounding(wallet, mode):
    runtime, engine = wallet
    a = start(runtime, mode, 6, status="paused")
    start(runtime, mode, 6)
    runtime.start(user_id="user", run_id=a, fingerprint="continued", resume=True)
    add_usage(runtime, a, 10 if mode == "legacy" else 5)
    # Force the final insufficient-hold branch after a known paid attempt.
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE billing_operations SET hold_points=0 WHERE run_id=:id"), {"id": a}
        )
    assert runtime.finish(run_id=a, outcome="success") == "refunded"
    assert assert_consistent(engine) == 10000
    assert refund_points(engine, a) == 1
    start(runtime, mode, 4)
    assert assert_consistent(engine) == 9999


def test_refund_inside_owned_transaction_rolls_back_balance_precision_and_receipt(wallet):
    runtime, engine = wallet
    a = start(runtime, "retail_odd", 6, status="paused")
    start(runtime, "retail_odd", 6)
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        runtime.finish(run_id=a, outcome="cancelled", connection=connection)
        assert connection.scalar(text("SELECT balance FROM credit_accounts")) == 10000
        connection.rollback()
    assert assert_consistent(engine) == 9999
    assert refund_points(engine, a) is None
    runtime.finish(run_id=a, outcome="cancelled")
    assert assert_consistent(engine) == 10000
    start(runtime, "retail_odd", 4)
    assert assert_consistent(engine) == 9999


@pytest.mark.parametrize("mode", ["legacy", "retail_odd"])
def test_exempt_run_carry_never_changes_the_users_exact_total(wallet, mode):
    runtime, engine = wallet
    a = start(runtime, mode, 6, status="paused", exempt=True)
    start(runtime, mode, 6)
    runtime.finish(run_id=a, outcome="error")
    assert refund_points(engine, a) is None
    assert assert_consistent(engine) == 10000
    start(runtime, mode, 4)
    assert assert_consistent(engine) == 9999


@pytest.mark.parametrize("mode", ["legacy", "retail", "retail_odd"])
def test_concurrent_refund_and_other_run_settlement_share_one_atomic_carry(wallet, mode):
    runtime, engine = wallet
    a = start(runtime, mode, 6, status="paused")
    start(runtime, mode, 6)
    c = start(runtime, mode, 4, status=None)
    barrier = Barrier(2)

    def finish(run, outcome):
        barrier.wait(timeout=5)
        runtime.finish(run_id=run, outcome=outcome)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(finish, a, "cancelled"), pool.submit(finish, c, "success")]
        for future in futures:
            future.result(timeout=10)
    assert assert_consistent(engine) == 9999
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT hold_points FROM billing_operations WHERE run_id=:id"), {"id": c}
            )
            == 0
        )


@pytest.mark.parametrize("mode", ["legacy", "retail_odd"])
def test_concurrent_duplicate_refund_cannot_credit_twice(wallet, mode):
    runtime, engine = wallet
    a = start(runtime, mode, 6, status="paused")
    start(runtime, mode, 6)
    barrier = Barrier(2)

    def refund(outcome):
        barrier.wait(timeout=5)
        runtime.finish(run_id=a, outcome=outcome)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(refund, outcome) for outcome in ("error", "cancelled")]
        for future in futures:
            future.result(timeout=10)
    assert assert_consistent(engine) == 10000
    assert refund_points(engine, a) == 1
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM credit_ledger WHERE model='billing-refund'")
            )
            == 1
        )
    start(runtime, mode, 4)
    assert assert_consistent(engine) == 9999


@pytest.mark.parametrize("order", [(0, 1), (1, 0)])
def test_all_runs_refunded_restore_initial_balance_and_record_zero_adjustment(wallet, order):
    runtime, engine = wallet
    runs = [start(runtime, "retail_odd", 6, status="paused"), start(runtime, "retail_odd", 6)]
    for index in order:
        runtime.finish(run_id=runs[index], outcome="error")
        assert_consistent(engine)
    assert assert_consistent(engine) == 10000
    assert refund_points(engine, runs[order[0]]) == 1
    assert refund_points(engine, runs[order[1]]) == 0
    for index in order:
        runtime.finish(run_id=runs[index], outcome="error")
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM credit_ledger WHERE model='billing-refund'")
            )
            == 2
        )
        assert all(
            Fraction(value) == 0
            for value in connection.scalars(text("SELECT credit_pico FROM billing_operations"))
        )
    assert assert_consistent(engine) == 10000
