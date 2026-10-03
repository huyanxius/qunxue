# ruff: noqa: F811
import json
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.error import HTTPError
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from test_durable_billing import wallet  # noqa: F401
from test_theory_matching_service import PHENOMENON, RELEASE, _bundle, _MatchRunRepository

from qunxue_api.adapters.model import InMemoryModelInvocationRecorder, ModelGateway
from qunxue_api.adapters.model.billing_operations import SqliteBillingOperations
from qunxue_api.adapters.model.metering import BillingContextMissing, OperationScope
from qunxue_api.adapters.model.openai_compatible_provider import OpenAICompatibleModelProvider
from qunxue_api.adapters.model.routed_provider import RoutedModelProvider
from qunxue_api.adapters.model.routing import ModelEndpoint, ModelRouteExecutor
from qunxue_api.application.theory_matching import TheoryMatchingApplication
from qunxue_api.modules.knowledge_catalog import KnowledgeReleaseLevel
from qunxue_api.modules.research_intake import EntryType, ResearchTask
from qunxue_api.modules.theory_matching import TheoryMatchingService

USER = UUID(int=1)


class Requests:
    def __init__(self):
        self.items = {}

    def get_by_idempotency_key(self, *, user_id, idempotency_key):
        return self.items.get((user_id, idempotency_key))

    def add(self, **kwargs):
        self.items[(kwargs["user_id"], kwargs["idempotency_key"])] = (
            kwargs["request_hash"],
            kwargs["match_run_id"],
        )

    def owns(self, *, user_id, match_run_id):
        return any(
            u == user_id and value[1] == match_run_id for (u, _k), value in self.items.items()
        )


def setup_application(
    wallet,
    monkeypatch,
    *,
    count=3,
    failures=None,
    commit_failure=False,
    configured=True,
    fallback=False,
):
    runtime, engine = wallet
    with engine.begin() as c:
        c.execute(text("UPDATE credit_accounts SET user_id=:user"), {"user": str(USER)})
    calls = []
    events = []
    failures = failures or set()

    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, limit):
            content = {
                "status": "ok",
                "knowledge_release_id": RELEASE.knowledge_release_id,
                "theory_ids": [],
                "output": {
                    "verdict": "conditional",
                    "match_rationale": "Synthetic evidence",
                    "applicable_conditions": [],
                    "limitations": [],
                    "material_requirements": [],
                    "evidence_gaps": [],
                    "alternative_explanations": [],
                    "evidence_ref_ids": [],
                },
            }
            if len(calls) in failures:
                content["output"] = {}
            return json.dumps(
                {
                    "id": f"synthetic-research-{len(calls)}",
                    "model": "gpt-6-luna",
                    "choices": [
                        {"message": {"content": json.dumps(content)}, "finish_reason": "stop"}
                    ],
                    "usage": {
                        "prompt_tokens": 1000,
                        "completion_tokens": 100,
                        "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                    },
                }
            ).encode()

    def transport(request, **kwargs):
        calls.append(json.loads(request.data))
        events.append("http")
        if fallback and len(calls) == 1:
            raise HTTPError(request.full_url, 503, "synthetic unavailable", {}, None)
        return Response()

    monkeypatch.setattr("qunxue_api.adapters.model.openai_compatible_provider.urlopen", transport)
    provider = OpenAICompatibleModelProvider(
        base_url="https://synthetic.test/v1",
        api_key=None,
        model="gpt-6-luna",
        timeout_seconds=1,
        capability_tier="base",
        require_billing=True,
    )
    if fallback:
        secondary = OpenAICompatibleModelProvider(
            base_url="https://synthetic-fallback.test/v1",
            api_key=None,
            model="gpt-6-luna",
            timeout_seconds=1,
            capability_tier="base",
            require_billing=True,
        )
        endpoints = tuple(
            ModelEndpoint(
                endpoint_id=name, base_url=url, model="gpt-6-luna", api_key=None, timeout_seconds=1
            )
            for name, url in [
                ("primary", "https://synthetic.test/v1"),
                ("fallback", "https://synthetic-fallback.test/v1"),
            ]
        )
        provider = RoutedModelProvider(
            providers=(provider, secondary), router=ModelRouteExecutor(endpoints=endpoints)
        )
    gateway = ModelGateway(
        provider=provider, recorder=InMemoryModelInvocationRecorder(), contract_version="synthetic"
    )
    release = replace(RELEASE, level=KnowledgeReleaseLevel.FINAL)
    bundle = replace(_bundle(count), release=release)
    matching = TheoryMatchingService(
        evidence_source=SimpleNamespace(retrieve=lambda **k: bundle),
        judge=gateway,
        repository=_MatchRunRepository(),
        provider=provider.descriptor.provider,
        model_version="gpt-6-luna",
        capability="base",
        contract_version="synthetic",
    )
    task = ResearchTask.create(
        task_id=PHENOMENON.task_id,
        user_id=USER,
        entry_type=EntryType.DIRECT_INPUT,
        idempotency_key="synthetic",
        now=datetime.now(UTC),
        seed_theory_id=None,
        seed_theory_name=None,
    )

    class Tasks:
        current = task

        def get(self, task_id, user_id):
            return self.current if user_id == USER else None

        def save_progress(self, task):
            self.current = task
            return task

    def commit():
        events.append("commit")
        if commit_failure and calls:
            raise RuntimeError("synthetic commit failure")

    class Billing:
        def open(self, **kwargs):
            assert kwargs["user_id"] == USER
            assert kwargs["phase"] == "user_research"
            if not configured:
                raise BillingContextMissing("synthetic missing configuration")
            return OperationScope(
                runtime,
                user_id=USER,
                run_id=kwargs["run_id"],
                fingerprint=json.dumps(kwargs["payload"], sort_keys=True),
                before_network=kwargs["before_network"],
            )

    application = TheoryMatchingApplication(
        catalog=SimpleNamespace(current_release=lambda **k: release),
        matching=matching,
        matching_requests=Requests(),
        research_tasks=Tasks(),
        billing=Billing(),
        commit=commit,
        rollback=lambda: events.append("rollback"),
    )
    args = dict(
        user_id=USER,
        task=task,
        phenomenon=PHENOMENON,
        idempotency_key="synthetic-start",
        expected_task_version=task.version,
        phenomenon_query_id=PHENOMENON.phenomenon_query_id,
        phenomenon_version=PHENOMENON.version,
        requested_knowledge_release_id=None,
    )
    return application, args, calls, events


def balance(engine):
    with engine.connect() as c:
        return c.scalar(text("SELECT balance FROM credit_accounts"))


def test_paid_matching_and_retry_use_owner_scope_and_cached_replay(wallet, monkeypatch):
    runtime, engine = wallet
    app, args, calls, events = setup_application(wallet, monkeypatch, count=3, failures={2})
    result = app.start(**args)
    assert len(calls) == 3 and len(result.candidate_failures) == 1
    assert (
        balance(engine) == 9997
    )  # Two valid 1.5-point attempts; invalid attempt is operator-funded.
    assert app.start(**args) == result and len(calls) == 3
    failure = result.candidate_failures[0]
    retry = dict(
        user_id=USER,
        match_run_id=result.match_run_id,
        candidate_id=failure.candidate_id,
        expected_match_run_version=result.version,
        expected_candidate_version=failure.candidate_version,
        idempotency_key="synthetic-retry",
    )
    final = app.retry_candidate(**retry)
    assert len(calls) == 4 and balance(engine) == 9996
    assert app.retry_candidate(**retry) == final and len(calls) == 4
    assert events[-1] == "commit"
    with engine.connect() as c:
        rows = c.execute(text("SELECT user_id, exempt, status FROM billing_operations")).all()
        assert rows == [(str(USER), 0, "success"), (str(USER), 0, "success")]
        attempts = c.execute(
            text(
                "SELECT billable, outcome, reference_cost_pico "
                "FROM billing_attempts ORDER BY created_at"
            )
        ).all()
        assert attempts == [
            (1, "success", 150000000),
            (0, "error", 150000000),
            (1, "success", 150000000),
            (1, "success", 150000000),
        ]


@pytest.mark.parametrize("mode", ["commit_failure", "unconfigured"])
def test_matching_configuration_and_commit_failure_do_not_charge(wallet, monkeypatch, mode):
    _runtime, engine = wallet
    app, args, calls, events = setup_application(
        wallet,
        monkeypatch,
        commit_failure=mode == "commit_failure",
        configured=mode != "unconfigured",
    )
    with pytest.raises(RuntimeError):
        app.start(**args)
    assert balance(engine) == 10000
    if mode == "unconfigured":
        assert not calls
    else:
        assert len(calls) == 1 and events[-1] == "rollback"
        with engine.connect() as c:
            assert c.scalar(text("SELECT status FROM billing_operations")) == "error"
            assert c.scalar(text("SELECT reference_cost_pico FROM billing_attempts")) == 150000000


def test_retry_rejects_nonowner_before_any_http_or_hold(wallet, monkeypatch):
    _runtime, engine = wallet
    app, _args, calls, _events = setup_application(wallet, monkeypatch)
    with pytest.raises(LookupError):
        app.retry_candidate(
            user_id=UUID(int=2),
            match_run_id=uuid4(),
            candidate_id=uuid4(),
            expected_match_run_version=1,
            expected_candidate_version=1,
            idempotency_key="synthetic",
        )
    assert not calls
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM billing_operations")) == 0


def test_user_research_cannot_be_silently_operator_funded(wallet, monkeypatch):
    from contextlib import nullcontext

    from qunxue_api.modules.billing import CreditService

    runtime, _engine = wallet
    seen = []
    monkeypatch.setattr(
        CreditService, "summary", lambda self, **kwargs: seen.append(kwargs["user_id"])
    )
    database = SimpleNamespace(session=lambda: nullcontext(object()))
    factory = SqliteBillingOperations(
        database, runtime, phase_policies={"user_research": "operator"}
    )
    scope = factory.open(user_id=USER, run_id=uuid4(), payload={}, phase="user_research")
    assert seen == [USER] and not scope.exempt


def test_legacy_route_fallback_records_actual_endpoint_and_keeps_unknown_operator_risk(
    wallet, monkeypatch
):
    runtime, engine = wallet
    app, args, calls, _events = setup_application(wallet, monkeypatch, fallback=True)
    result = app.start(**args)
    assert len(result.candidates) == 3 and len(calls) == 4
    assert all(type(body["max_tokens"]) is int and body["max_tokens"] > 0 for body in calls)
    assert balance(engine) == 9996
    with engine.connect() as c:
        attempts = c.execute(
            text(
                "SELECT endpoint_id, provider_host, route_id, outcome, usage_state, "
                "reference_cost_pico FROM billing_attempts ORDER BY created_at"
            )
        ).all()
        assert [(a[0], a[1]) for a in attempts] == [
            ("primary", "synthetic.test"),
            ("fallback", "synthetic-fallback.test"),
            ("primary", "synthetic.test"),
            ("primary", "synthetic.test"),
        ]
        assert all(a[2] for a in attempts)
        assert attempts[0][3:] == ("error", "unknown", None)
        assert attempts[1][3:] == ("success", "known", 150000000)
    assert runtime.operator_risk_pico() > 450000000
