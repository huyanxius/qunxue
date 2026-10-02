# ruff: noqa: F811
# Synthetic financial fault/stream checks. No paid provider or production access.
import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.providers.openai import OpenAIProvider
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from test_durable_billing import wallet  # noqa: F401

from qunxue_api.adapters.model.metering import MeteredOpenAIChatModel, OperationScope
from qunxue_api.adapters.sqlite.billing_model import (
    CreditAccountRow,
    CreditLedgerRow,
    CreditRedemptionCodeRow,
)
from qunxue_api.adapters.sqlite.billing_repository import SqliteCreditRepository
from qunxue_api.adapters.sqlite.durable_billing import DurableBilling, create_billing_tables
from qunxue_api.modules.billing import PriceBook


@pytest.mark.parametrize("finish_reason", ["stop", "length", "content_filter"])
def test_metered_stream_handles_async_context_and_terminal_billing(wallet, finish_reason):
    runtime, engine = wallet
    calls = []

    def reply(request):
        calls.append(request)
        chunks = [
            {
                "choices": [
                    {"index": 0, "delta": {"content": "Partial output"}, "finish_reason": None}
                ]
            },
            {"choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}]},
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 30,
                    "total_tokens": 130,
                    "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                },
            },
        ]
        for c in chunks:
            c.update(
                id="synthetic-stream-finish",
                object="chat.completion.chunk",
                created=1,
                model="gpt-6.1-sol",
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content="".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n",
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as http:
            model = MeteredOpenAIChatModel(
                "gpt-6.1-sol",
                require_billing=True,
                provider=OpenAIProvider(
                    openai_client=AsyncOpenAI(
                        base_url="https://synthetic.test/v1",
                        api_key="synthetic",
                        http_client=http,
                        max_retries=0,
                    )
                ),
                settings={"max_tokens": 100},
            )
            try:
                with OperationScope(
                    runtime, user_id="user", run_id=str(uuid4()), fingerprint="synthetic"
                ) as scope:
                    async with Agent(model).run_stream("synthetic") as result:
                        await result.get_output()
                    scope.finish("success")
            except Exception:
                # A terminal rejection must retain cost and waive the user.
                if finish_reason == "stop":
                    raise

    asyncio.run(run())
    assert len(calls) == 1
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT balance FROM credit_accounts WHERE user_id='user'")
        ).scalar()
        assert row == (9995 if finish_reason == "stop" else 10000)
        assert conn.scalar(text("SELECT reference_cost_pico FROM billing_attempts")) == 500000000


def test_redemption_and_new_hold_are_atomic(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/redeem-race.db")
    for model in (CreditAccountRow, CreditLedgerRow, CreditRedemptionCodeRow):
        model.__table__.create(engine)
    create_billing_tables(engine)
    user, code = uuid4(), uuid4()
    now = datetime.now(UTC)
    with Session(engine) as session:
        session.add(
            CreditAccountRow(
                user_id=str(user),
                balance=50000,
                active_run_id=None,
                active_run_expires_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            CreditRedemptionCodeRow(
                code_id=str(code),
                code_hash="test-hash",
                batch_id="synthetic",
                code_index=0,
                created_by_user_id=str(user),
                created_at=now,
                expires_at=now + timedelta(days=1),
                redeemed_by_user_id=None,
                redeemed_at=None,
            )
        )
        session.commit()
    runtime = DurableBilling(
        engine,
        price_book=PriceBook(credits_per_usd=10000, version="synthetic"),
        max_attempt_pico=5 * 10**12,
        max_operation_pico=5 * 10**12,
        daily_budget_pico=50 * 10**12,
    )
    with Session(engine) as session:
        repository = SqliteCreditRepository(session)
        original = repository._billing_details

        def interleaving(user_id, limit, offset):
            observed = original(user_id, limit, offset)
            assert observed[0] == 0
            # A separate SQLite writer commits after the frozen check, before redeem writes.
            runtime.start(user_id=user, run_id=str(uuid4()), fingerprint="concurrent-hold")
            return observed

        repository._billing_details = interleaving
        try:
            repository.redeem_code(user_id=user, code_hash="test-hash", now=now)
            session.commit()
        except Exception:
            session.rollback()
    with engine.connect() as conn:
        balance = conn.scalar(text("SELECT balance FROM credit_accounts"))
        held = conn.scalar(
            text(
                "SELECT coalesce(sum(hold_points),0) FROM billing_operations WHERE status='active'"
            )
        )
        assert balance >= held, f"balance={balance}, holds={held}"
    engine.dispose()


def test_redemption_writer_lock_allows_waiting_reservation_to_progress(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    engine = create_engine(f"sqlite:///{tmp_path}/redeem-progress.db")
    for model in (CreditAccountRow, CreditLedgerRow, CreditRedemptionCodeRow):
        model.__table__.create(engine)
    create_billing_tables(engine)
    user, code = uuid4(), uuid4()
    now = datetime.now(UTC)
    with Session(engine) as s:
        s.add(CreditAccountRow(user_id=str(user), balance=50000, created_at=now, updated_at=now))
        s.add(
            CreditRedemptionCodeRow(
                code_id=str(code),
                code_hash="progress-hash",
                batch_id="synthetic",
                code_index=0,
                created_by_user_id=str(user),
                created_at=now,
                expires_at=now + timedelta(days=1),
            )
        )
        s.commit()
    runtime = DurableBilling(
        engine,
        price_book=PriceBook(credits_per_usd=10000, version="synthetic"),
        max_attempt_pico=5 * 10**12,
        max_operation_pico=5 * 10**12,
        daily_budget_pico=50 * 10**12,
    )
    attempted = Event()

    def reserve():
        attempted.set()
        return runtime.start(user_id=user, run_id=str(uuid4()), fingerprint="waiting-reservation")

    future = None
    with ThreadPoolExecutor(max_workers=1) as pool:
        with Session(engine) as s:
            repo = SqliteCreditRepository(s)
            original = repo._billing_details

            def at_freeze_read(user_id, limit, offset):
                nonlocal future
                observed = original(user_id, limit, offset)
                assert observed[0] == 0
                future = pool.submit(reserve)
                assert attempted.wait(2)
                return observed

            repo._billing_details = at_freeze_read
            redemption = repo.redeem_code(user_id=user, code_hash="progress-hash", now=now)
            s.commit()
            assert redemption.balance == 10000
        assert future.result(timeout=5)
    with engine.connect() as c:
        balance = c.scalar(text("SELECT balance FROM credit_accounts"))
        held = c.scalar(
            text("SELECT sum(hold_points) FROM billing_operations WHERE status='active'")
        )
        assert balance == held == 10000
        assert c.scalar(text("SELECT redeemed_by_user_id FROM credit_redemption_codes")) == str(
            user
        )
    engine.dispose()


def test_bill_details_expose_actual_usage_locked_prices_and_pending_cash(wallet):
    runtime, engine = wallet
    with OperationScope(
        runtime, user_id="user", run_id=str(uuid4()), fingerprint="synthetic"
    ) as scope:
        attempt = scope.before_attempt_payload(
            {"model": "gpt-6-luna", "messages": [], "max_tokens": 100},
            provider_host="synthetic.test",
        )
        scope.complete(
            attempt,
            {
                "id": "invoice-synthetic",
                "model": "gpt-6-luna",
                "choices": [],
                "usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 100,
                    "prompt_tokens_details": {"cached_tokens": 200, "cache_write_tokens": 100},
                },
            },
            outcome="success",
        )
        scope.finish("success")
    with Session(engine) as session:
        frozen, operations = SqliteCreditRepository(session)._billing_details("user", 1, 0)
    assert frozen == 0
    operation = operations[0]
    assert operation["points_charged"] == 1
    receipt = operation["attempts"][0]
    assert (receipt["requested_model"], receipt["returned_model"]) == ("gpt-6-luna", "gpt-6-luna")
    assert (
        receipt["input_tokens"],
        receipt["cache_read_tokens"],
        receipt["cache_write_tokens"],
        receipt["output_tokens"],
    ) == (1000, 200, 100, 100)
    assert receipt["reference_cost_pico"] == 134500000
    assert receipt["procurement_cost_pico"] is None
    assert receipt["procurement_status"] == "pending"
    assert receipt["price_snapshot"]["version"] == "synthetic"
    assert receipt["price_snapshot"]["credits_per_usd"] == 10000
