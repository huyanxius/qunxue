# ruff: noqa: F811
from dataclasses import replace
from datetime import UTC, datetime
from fractions import Fraction
from uuid import UUID

import pytest
from sqlalchemy import text
from test_account_management_api import client as account_client  # noqa: F401
from test_agent_memory import register
from test_durable_billing import balance, operation, wallet  # noqa: F401

from qunxue_api.adapters.sqlite.billing_repository import SqliteCreditRepository
from qunxue_api.modules.billing.pricing import PICO_USD, PriceBook


def retail_book(**changes):
    values = dict(
        credits_per_usd=None,
        version="synthetic-fx",
        points_per_cny=100,
        retail_rate_ppm=100000,
        fx_cny_per_usd_micro=7123456,
        fx_snapshot_id="synthetic-only",
        fx_as_of="2026-10-02T00:00:00+00:00",
        fx_source="synthetic-test",
    )
    return PriceBook(**{**values, **changes})


def test_official_usd_reference_to_cny_retail_has_exact_snapshot_and_fraction():
    book = retail_book()
    assert book.credit_numerator(PICO_USD) == Fraction(PICO_USD * 7123456, 100000)
    cost = book.cost_pico_usd("gpt-6-luna", 1000, 100, 200, 300)
    assert cost == 139500000
    assert book.credit_numerator(cost) == Fraction(cost * 7123456, 100000)
    assert book.procurement_estimate_source == "user_reported_estimate"
    assert book.procurement_estimate_ratio == "1/35"


@pytest.mark.parametrize(
    "changes",
    [
        {"fx_source": None},
        {"fx_snapshot_id": None},
        {"fx_as_of": "2026-10-02T00:00:00"},
        {"retail_rate_ppm": 200000},
        {"points_per_cny": 10},
        {"credits_per_usd": 100},
    ],
)
def test_incomplete_or_conflicting_retail_configuration_fails_closed(changes):
    with pytest.raises(ValueError):
        retail_book(**changes)


def test_rational_credit_precision_survives_persistence_and_price_change(wallet):
    runtime, engine = wallet
    runtime.book = retail_book()
    run = operation(runtime)
    a = runtime.before_attempt(
        run_id=run,
        endpoint_id="synthetic",
        model="gpt-6-luna",
        input_limit=1000,
        output_limit=100,
        request_hash="synthetic",
    )
    runtime.complete_attempt(
        attempt_id=a,
        input_tokens=1000,
        output_tokens=100,
        cache_read_tokens=200,
        cache_write_tokens=300,
        returned_model="gpt-6-luna",
        outcome="success",
    )
    runtime.finish(run_id=run, outcome="paused")
    with engine.connect() as c:
        exact = c.scalar(text("SELECT credit_pico FROM billing_operations"))
        snapshot = c.scalar(text("SELECT price_json FROM billing_operations"))
        assert c.scalar(text("SELECT procurement_cost_pico FROM billing_attempts")) is None
    assert Fraction(exact) == retail_book().credit_numerator(139500000)
    assert runtime._book(snapshot).fx_snapshot_id == "synthetic-only"
    runtime.book = replace(retail_book(), fx_cny_per_usd_micro=9999999)
    runtime.start(user_id="user", run_id=run, fingerprint="next-phase", resume=True)
    runtime.finish(run_id=run, outcome="success")
    assert balance(engine) == 10000


def test_signup_gift_and_welcome_projection_are_once_and_use_real_frozen_funds(account_client):
    user = register(account_client)
    data = account_client.get("/api/account/credits").json()
    assert data["balance"] == data["total_granted_points"] == data["credit_limit"] == 3000
    assert data["quota_status"] == "known"
    assert data["active_usage_buckets"][0]["kind"] == "welcome"
    assert data["active_usage_buckets"][0]["limit_points"] == 3000
    from billing_test_support import synthetic_billing_runtime

    runtime = synthetic_billing_runtime(account_client.app.state.database.engine)
    runtime.start(user_id=user, run_id="synthetic-hold", fingerprint="synthetic")
    frozen = account_client.get("/api/account/credits").json()
    assert frozen["available_balance"] == 2000
    assert frozen["active_usage_buckets"][0]["available_points"] == 2000
    with account_client.app.state.database.session() as session:
        repository = SqliteCreditRepository(session)
        repository.ensure_welcome_grant(user_id=UUID(user), points=10000, now=datetime.now(UTC))
        assert (
            session.scalar(
                text("SELECT count(*) FROM credit_ledger WHERE kind='signup_grant' AND user_id=:u"),
                {"u": user},
            )
            == 1
        )
    assert account_client.get("/api/account/credits").json()["balance"] == 3000


def test_historical_redemption_does_not_claim_a_paid_top_up_or_current_period(account_client):
    user = register(account_client)
    with account_client.app.state.database.session() as session:
        session.execute(
            text(
                "INSERT INTO credit_ledger "
                "(entry_id,user_id,run_id,kind,points,balance_after,"
                "input_tokens,output_tokens,created_at) "
                "VALUES ('synthetic-redemption',:u,NULL,'redemption',10000,10000,0,0,"
                "'2026-10-02 00:00:00')"
            ),
            {"u": user},
        )
        session.execute(
            text("UPDATE credit_accounts SET balance=10000 WHERE user_id=:u"), {"u": user}
        )
    data = account_client.get("/api/account/credits").json()
    assert data["balance"] == 10000
    assert data["active_usage_buckets"] == []
    assert data["quota_status"] == "unavailable"
    assert data["total_granted_points"] is None and data["credit_limit"] == 0


@pytest.mark.parametrize("configuration", ["absent", "partial", "complete"])
def test_runtime_requires_explicit_fx_snapshot_and_finite_budgets(wallet, configuration):
    from qunxue_api.bootstrap import _billing_runtime
    from qunxue_api.settings import Settings

    _, engine = wallet
    values = dict(
        _env_file=None,
        billing_price_version="synthetic-fx",
        billing_credits_per_usd=None,
        billing_max_attempt_usd_micro=1000,
        billing_max_operation_usd_micro=10000,
        billing_daily_budget_usd_micro=100000,
    )
    if configuration in {"partial", "complete"}:
        values["billing_fx_cny_per_usd_micro"] = 7123456
    if configuration == "complete":
        values.update(
            billing_fx_snapshot_id="synthetic-only",
            billing_fx_as_of="2026-10-02T00:00:00+00:00",
            billing_fx_source="synthetic-test",
        )
    from types import SimpleNamespace

    runtime = _billing_runtime(Settings(**values), SimpleNamespace(engine=engine))
    if configuration != "complete":
        assert runtime is None
    else:
        assert runtime.book.credits_per_usd is None
        assert runtime.book.fx_snapshot_id == "synthetic-only"
        assert runtime.book.points_per_cny == 100
        assert runtime.book.retail_rate_ppm == 100000
        assert runtime.max_attempt_pico == 10**9
