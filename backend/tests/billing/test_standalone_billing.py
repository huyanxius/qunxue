# ruff: noqa: F811
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from test_durable_billing import wallet  # noqa: F401

from qunxue_api.adapters.model.metering import BillingContextMissing, OperationScope
from qunxue_api.adapters.model.openai_compatible_provider import OpenAICompatibleModelProvider
from qunxue_api.application.memory_learning import MemoryLearningWorker


def test_production_probe_requires_scope_before_transport():
    calls = []
    provider = OpenAICompatibleModelProvider(
        base_url="https://synthetic.test/v1",
        api_key="synthetic",
        model="gpt-6-luna",
        timeout_seconds=1,
        capability_tier="base",
        require_billing=True,
        probe_transport=httpx.MockTransport(lambda req: calls.append(req)),
    )
    with pytest.raises(BillingContextMissing):
        asyncio.run(provider.probe())
    assert not calls


def test_probe_records_operator_usage_without_creating_a_gift_account(wallet):
    runtime, engine = wallet
    body = {
        "id": "probe-synthetic",
        "model": "gpt-6-luna",
        "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": 5,
            "completion_tokens": 1,
            "total_tokens": 6,
            "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
        },
    }
    provider = OpenAICompatibleModelProvider(
        base_url="https://synthetic.test/v1",
        api_key="synthetic",
        model="gpt-6-luna",
        timeout_seconds=1,
        capability_tier="base",
        require_billing=True,
        probe_transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body)),
    )
    with OperationScope(
        runtime,
        user_id="operator:model_probe",
        run_id=str(uuid4()),
        fingerprint="synthetic",
        exempt=True,
    ) as scope:
        asyncio.run(provider.probe())
        scope.finish("success")
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM credit_accounts")) == 1
        assert c.scalar(text("SELECT reference_cost_pico FROM billing_attempts")) == 1000000
        assert c.scalar(text("SELECT balance FROM credit_accounts")) == 10000


@pytest.mark.parametrize("failure", ["database_error", "lost_lease"])
def test_memory_persistence_failure_waives_metered_background_work(wallet, failure):
    from contextlib import contextmanager

    runtime, engine = wallet
    batch = SimpleNamespace(user_id="user", conversation_id="synthetic", lease_token=str(uuid4()))

    @contextmanager
    def repository_scope():
        class Repository:
            def claim(self, **kwargs):
                return batch

            def complete(self, *args):
                if failure == "lost_lease":
                    return False
                raise RuntimeError("synthetic persistence failure")

            def failed(self, *args):
                pass

        yield Repository()

    class Billing:
        def open(self, **kwargs):
            assert kwargs["phase"] == "memory_learning"
            return OperationScope(
                runtime, user_id="user", run_id=kwargs["run_id"], fingerprint="synthetic"
            )

    def extract(_batch):
        from qunxue_api.adapters.model.metering import current_operation

        scope = current_operation(required=True)
        attempt = scope.before_attempt_payload(
            {"model": "gpt-6-luna", "messages": [], "max_tokens": 1}
        )
        scope.complete(
            attempt,
            {
                "id": "memory-synthetic",
                "model": "gpt-6-luna",
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 1,
                    "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                },
                "choices": [],
            },
            outcome="success",
        )
        return (), 5, 1

    worker = MemoryLearningWorker(repository_scope, extractor=extract, billing=Billing())
    assert worker.run_once()
    with engine.connect() as c:
        assert c.scalar(text("SELECT status FROM billing_operations")) == "error"
        assert c.scalar(text("SELECT reference_cost_pico FROM billing_attempts")) == 1000000
        assert c.scalar(text("SELECT balance FROM credit_accounts")) == 10000


def test_missing_chargeable_cache_write_is_pending_without_protocol_policy(wallet):
    from qunxue_api.adapters.model.token_usage import UnknownTokenUsage

    runtime, engine = wallet
    with (
        pytest.raises(UnknownTokenUsage),
        OperationScope(
            runtime, user_id="user", run_id=str(uuid4()), fingerprint="synthetic"
        ) as scope,
    ):
        attempt = scope.before_attempt_payload(
            {"model": "gpt-6.1-sol", "messages": [], "max_tokens": 1},
            provider_host="synthetic.test",
        )
        scope.complete(
            attempt,
            {
                "id": "missing-write",
                "model": "gpt-6.1-sol",
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 1,
                    "prompt_tokens_details": {"cached_tokens": 0},
                },
                "choices": [],
            },
            outcome="success",
        )
    with engine.connect() as c:
        assert c.scalar(text("SELECT usage_state FROM billing_attempts")) == "unknown"
        assert c.scalar(text("SELECT balance FROM credit_accounts")) == 10000


def test_explicit_zero_omission_policy_is_locked_and_allows_legacy_receipt(wallet):
    from dataclasses import replace

    runtime, engine = wallet
    runtime.book = replace(
        runtime.book, usage_policies={"synthetic.test:gpt-6-luna": "omitted_cache_subsets_are_zero"}
    )
    with OperationScope(
        runtime, user_id="user", run_id=str(uuid4()), fingerprint="synthetic"
    ) as scope:
        attempt = scope.before_attempt_payload(
            {"model": "gpt-6-luna", "messages": [], "max_tokens": 1}, provider_host="synthetic.test"
        )
        scope.complete(
            attempt,
            {
                "id": "explicit-policy",
                "model": "gpt-6-luna",
                "usage": {"prompt_tokens": 5, "completion_tokens": 1},
                "choices": [],
            },
            outcome="success",
        )
        scope.finish("success")
    with engine.connect() as c:
        assert c.scalar(text("SELECT reference_cost_pico FROM billing_attempts")) == 1000000
        assert "omitted_cache_subsets_are_zero" in c.scalar(
            text("SELECT price_json FROM billing_attempts")
        )


def test_overview_final_snapshot_failure_refunds_before_delivery(wallet):
    from qunxue_api.adapters.model.metering import current_operation
    from qunxue_api.application.memory_overview import MemoryOverview, MemoryOverviewStale

    runtime, engine = wallet

    class Billing:
        def open(self, **kwargs):
            return OperationScope(
                runtime, user_id="user", run_id=kwargs["run_id"], fingerprint="synthetic"
            )

    def generate(_items):
        scope = current_operation(required=True)
        attempt = scope.before_attempt_payload(
            {"model": "gpt-6-luna", "messages": [], "max_tokens": 1}, provider_host="synthetic.test"
        )
        scope.complete(
            attempt,
            {
                "model": "gpt-6-luna",
                "id": "overview-synthetic",
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 1,
                    "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                },
                "choices": [],
            },
            outcome="success",
        )
        return "synthetic summary"

    def verify_snapshot():
        raise MemoryOverviewStale()

    overview = MemoryOverview(generate, billing=Billing())
    items = (SimpleNamespace(memory_id=uuid4(), origin="manual", content="synthetic"),)
    with pytest.raises(MemoryOverviewStale):
        overview.summarize(uuid4(), None, 1, items, before_delivery=verify_snapshot)
    with engine.connect() as c:
        assert c.scalar(text("SELECT balance FROM credit_accounts")) == 10000
        assert c.scalar(text("SELECT status FROM billing_operations")) == "error"
        assert c.scalar(text("SELECT reference_cost_pico FROM billing_attempts")) == 1000000
