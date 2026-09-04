# AI Gateway Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route business-model and Agent-model requests through one in-process retry, circuit, health, and attempt-audit boundary.

**Architecture:** A provider-neutral `ModelRouteExecutor` owns endpoint order and state transitions while existing adapters retain SDK and response parsing. A durable attempt recorder captures every real upstream request; `/api/health` exposes only an aggregate, cached model status and exact deployment revision.

**Tech Stack:** Python 3.12, FastAPI, Pydantic Settings, Pydantic AI, SQLAlchemy 2, Alembic, SQLite, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-05-ai-gateway-stabilization-design.md`

## Execution status (local branch, 2026-09-05)

Tasks 1–5 are implemented in the local `feat/ai-gateway-stabilization` branch. Task 6 regenerated the OpenAPI and frontend contract, completed local verification, documented the delivery contract, and owns the final documentation/generated-contract commit. This is not deployment status: no push, PR, merge, or production rollout has occurred.

Before deployment, the release owner must set `QUNXUE_RELEASE_REVISION` to the immutable release commit, protect all model credentials outside the repository, back up the target database, run `uv run alembic upgrade head`, and validate the public health, attempt-audit, fallback, and probe-shutdown checks defined in the design. A production SSH observation is evidence about that observed deployment only; it does not prove this branch is live or repaired.

## Global Constraints

- Do not add a public OpenAI-compatible API, developer keys, BYOK, pricing administration, payments, or a provider UI.
- Preserve existing Agent SSE events, existing health fields, and existing `model_invocations` behavior.
- Never persist or return credentials, cookies, complete prompts, private material text, or raw provider response bodies.
- Retry only connection/transport failures, timeouts, HTTP 408/409/429/5xx, and the existing transient `unknown provider for model` case.
- Open a circuit after exactly three consecutive retryable failures and allow one recovery attempt after exactly 30 seconds by default.
- Active probes run no more often than every 300 seconds by default; mock mode performs no external probe.
- Endpoint attempts are sequential; do not race or hedge billed requests.
- Legacy fallback entries without `model` inherit the primary model.
- All production behavior follows red-green-refactor; run the named failing test before implementation.

---

### Task 1: Provider-neutral routing and circuit state

**Files:**
- Create: `backend/src/qunxue_api/adapters/model/routing.py`
- Modify: `backend/src/qunxue_api/adapters/model/__init__.py`
- Test: `backend/tests/test_model_routing.py`

**Interfaces:**
- Consumes: only standard-library callables, dataclasses, time, locks, UUIDs, and awaitables.
- Produces: `ModelEndpoint`, `ModelRouteContext`, `ModelRouteScope`, `model_route_scope`, `current_model_route_scope`, `ModelAttemptFailure`, `ModelAttemptResult[T]`, `ModelRouteResult[T]`, `ModelAttemptRecord`, `ModelAttemptRecorder`, `InMemoryModelAttemptRecorder`, `ModelEndpointHealth`, `ModelHealthSnapshot`, and `ModelRouteExecutor.execute/execute_async/note_failure/health_snapshot`.

- [ ] **Step 1: Write failing tests for ordered fallback and terminal failures**

```python
def test_sync_route_uses_next_endpoint_only_after_retryable_failure() -> None:
    recorder = InMemoryModelAttemptRecorder()
    router = ModelRouteExecutor(endpoints=_endpoints(), recorder=recorder)

    result = router.execute(
        context=_context(),
        invoke=lambda endpoint: (
            (_ for _ in ()).throw(ModelAttemptFailure(code="model_rate_limited", retryable=True))
            if endpoint.endpoint_id == "primary"
            else ModelAttemptResult(value="backup", input_tokens=4, output_tokens=2)
        ),
    )

    assert result.value == "backup"
    assert [(item.endpoint_id, item.success, item.selected) for item in recorder.list_all()] == [
        ("primary", False, False),
        ("backup", True, True),
    ]


def test_sync_route_does_not_fallback_after_terminal_failure() -> None:
    calls: list[str] = []
    router = ModelRouteExecutor(endpoints=_endpoints())

    with pytest.raises(ModelAttemptFailure, match="invalid request"):
        router.execute(
            context=_context(),
            invoke=lambda endpoint: _terminal_failure(calls, endpoint.endpoint_id),
        )

    assert calls == ["primary"]
```

- [ ] **Step 2: Run the two tests and verify RED**

Run: `cd backend && uv run pytest tests/test_model_routing.py -k "next_endpoint or terminal_failure" -v`

Expected: collection/import failure because `qunxue_api.adapters.model.routing` does not exist.

- [ ] **Step 3: Implement the data contracts and sync executor**

```python
@dataclass(frozen=True, slots=True)
class ModelEndpoint:
    endpoint_id: str
    base_url: str
    model: str
    api_key: str | None = field(repr=False)
    timeout_seconds: float
    extra_headers: Mapping[str, str] = field(default_factory=dict, repr=False)


class ModelAttemptFailure(RuntimeError):
    def __init__(self, *, code: str, retryable: bool, message: str = "model attempt failed"):
        self.code = code
        self.retryable = retryable
        super().__init__(message)
```

Implement `execute` so each invoked endpoint creates exactly one attempt record, the first successful result is selected, and the last failure is raised when no endpoint succeeds.

- [ ] **Step 4: Run Task 1 sync tests and verify GREEN**

Run: `cd backend && uv run pytest tests/test_model_routing.py -k "sync_route" -v`

Expected: all selected tests pass.

- [ ] **Step 5: Write failing tests for circuit transitions and async parity**

```python
def test_third_retryable_failure_opens_circuit_until_cooldown() -> None:
    clock = MutableClock()
    router = ModelRouteExecutor(
        endpoints=(_endpoint("primary"),),
        failure_threshold=3,
        cooldown_seconds=30,
        clock=clock,
    )
    for _ in range(3):
        with pytest.raises(ModelAttemptFailure):
            router.execute(context=_context(), invoke=_retryable_failure)

    assert router.health_snapshot().status == "unavailable"
    with pytest.raises(ModelRoutesUnavailable):
        router.execute(context=_context(), invoke=_unexpected_call)

    clock.advance(seconds=30)
    assert router.health_snapshot().status == "recovering"


@pytest.mark.anyio
async def test_async_route_records_the_same_attempt_shape() -> None:
    recorder = InMemoryModelAttemptRecorder()
    router = ModelRouteExecutor(endpoints=_endpoints(), recorder=recorder)
    result = await router.execute_async(context=_context(), invoke=_async_fallback)
    assert result.value == "backup"
    assert [item.attempt_number for item in recorder.list_all()] == [1, 2]
```

- [ ] **Step 6: Run circuit/async tests and verify RED**

Run: `cd backend && uv run pytest tests/test_model_routing.py -k "circuit or async_route" -v`

Expected: failures because circuit state and `execute_async` are missing.

- [ ] **Step 7: Implement locked health transitions and async execution**

Use a monotonic clock for cooldown decisions and a UTC wall clock for persisted timestamps. Admit only one half-open request by changing `unhealthy` to `recovering` under the lock before invoking it.

- [ ] **Step 8: Verify Task 1**

Run: `cd backend && uv run ruff check src/qunxue_api/adapters/model tests/test_model_routing.py && uv run pytest tests/test_model_routing.py -v`

Expected: Ruff and all routing tests pass.

- [ ] **Step 9: Commit Task 1**

```bash
git add backend/src/qunxue_api/adapters/model backend/tests/test_model_routing.py
git commit -m "feat(gateway): add shared model route policy"
```

### Task 2: Durable attempt audit

**Files:**
- Create: `backend/src/qunxue_api/adapters/sqlite/model_attempt_model.py`
- Create: `backend/src/qunxue_api/adapters/model/attempt_recording.py`
- Create: `backend/migrations/versions/20260905_0340_model_route_attempts.py`
- Modify: `backend/src/qunxue_api/adapters/sqlite/__init__.py`
- Modify: `backend/src/qunxue_api/adapters/model/__init__.py`
- Test: `backend/tests/test_model_attempt_recording.py`
- Test: `backend/tests/test_migrations.py`

**Interfaces:**
- Consumes: `ModelAttemptRecord` from Task 1 and `Database`.
- Produces: `ModelRouteAttemptRow` and `SqliteModelAttemptRecorder.record/list_for_route/list_for_agent_run`.

- [ ] **Step 1: Write a failing persistence test**

```python
def test_sqlite_attempt_recorder_persists_safe_route_telemetry(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'attempts.db'}")
    database.create_all()
    recorder = SqliteModelAttemptRecorder(database)
    recorder.record(_attempt(agent_run_id=UUID(int=9)))

    persisted = recorder.list_for_agent_run(UUID(int=9))
    assert len(persisted) == 1
    assert persisted[0].endpoint_id == "backup"
    assert persisted[0].input_tokens == 4
    assert not hasattr(persisted[0], "prompt")
    assert not hasattr(persisted[0], "api_key")
```

- [ ] **Step 2: Run the persistence test and verify RED**

Run: `cd backend && uv run pytest tests/test_model_attempt_recording.py -v`

Expected: import failure for the missing SQLite recorder.

- [ ] **Step 3: Add the ORM row and recorder**

The table fields must match the design exactly. Store UUIDs as 36-character strings, latency as an integer number of milliseconds, and tokens as nullable integers. Index `route_id`, `trace_id`, and `agent_run_id`. Do not add prompt, request body, response body, URL, header, or credential columns.

- [ ] **Step 4: Add the Alembic migration**

Use revision `20260905_0340` with `down_revision = "20260904_0330"`. The migration creates `model_route_attempts` and the three indexes and drops them in reverse order.

- [ ] **Step 5: Verify persistence and migration metadata**

Run: `cd backend && uv run pytest tests/test_model_attempt_recording.py tests/test_migrations.py::test_alembic_head_matches_orm_metadata -v`

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 2**

```bash
git add backend/src/qunxue_api/adapters/model backend/src/qunxue_api/adapters/sqlite backend/migrations/versions/20260905_0340_model_route_attempts.py backend/tests/test_model_attempt_recording.py
git commit -m "feat(gateway): persist model route attempts"
```

### Task 3: Route business model capabilities through the shared executor

**Files:**
- Create: `backend/src/qunxue_api/adapters/model/routed_provider.py`
- Modify: `backend/src/qunxue_api/adapters/model/__init__.py`
- Modify: `backend/src/qunxue_api/adapters/model/types.py`
- Modify: `backend/src/qunxue_api/adapters/model/gateway.py`
- Modify: `backend/src/qunxue_api/settings.py`
- Modify: `backend/src/qunxue_api/bootstrap.py`
- Modify: `.env.example`
- Test: `backend/tests/test_model_gateway.py`
- Test: `backend/tests/test_model_gateway_api.py`
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Consumes: Task 1 `ModelRouteExecutor`, Task 2 recorder, existing `ModelProvider` implementations.
- Produces: `RoutedModelProvider` implementing all four `ModelProvider` methods and `ModelGateway` route correlation.

- [ ] **Step 1: Write a failing business fallback test**

```python
def test_business_gateway_falls_back_and_keeps_one_business_trace() -> None:
    attempts = InMemoryModelAttemptRecorder()
    routed = RoutedModelProvider(
        providers=(failing_provider("model_timeout"), successful_provider()),
        router=ModelRouteExecutor(endpoints=_endpoints(), recorder=attempts),
    )
    gateway = ModelGateway(provider=routed, recorder=InMemoryModelInvocationRecorder(), contract_version="v1")

    result = gateway.build(task_id=UUID(int=1), raw_input="现象", research_intent=None, context=None)

    assert result.phenomenon == "现象"
    assert len(attempts.list_all()) == 2
    assert len({item.trace_id for item in attempts.list_all()}) == 1


def test_fallback_can_override_primary_model() -> None:
    settings = Settings(
        model_name="primary-model",
        model_fallbacks=[{"base_url": "https://backup.test/v1", "api_key": "k", "model": "backup-model"}],
    )
    assert settings.resolved_model_endpoints()[1].model == "backup-model"
```

- [ ] **Step 2: Run the test and verify RED**

Run: `cd backend && uv run pytest tests/test_model_gateway.py tests/test_health.py -k "business_gateway_falls_back or fallback_can_override" -v`

Expected: import failure for `RoutedModelProvider`, no second attempt, or missing `resolved_model_endpoints`.

- [ ] **Step 3: Implement routed provider and correlation**

Map existing `ModelProviderFailure.code` values into `ModelAttemptFailure` without storing its message. Pass `ModelGateway` trace/request IDs into the routed call so the attempt rows and final `model_invocations` row share identifiers. Add optional `selected_descriptor` to `ModelProviderResult`; the routed provider sets it and `ModelGateway` uses it for the final business record instead of incorrectly reporting the primary model after fallback.

- [ ] **Step 4: Normalize and validate endpoint settings**

Define a Pydantic model for fallback entries with `base_url`, `api_key`, and optional `model`. Reject credential-bearing URLs and empty model names. `Settings.resolved_model_endpoints()` returns primary followed by `fallback-1`, `fallback-2`, and so on. Keep parsing compatible with existing JSON environment values.

- [ ] **Step 5: Bootstrap all configured business endpoints**

Build one `OpenAICompatibleModelProvider` per endpoint and install one application-scoped router using `SqliteModelAttemptRecorder`. Mock mode keeps the deterministic provider and performs no routed external call.

- [ ] **Step 6: Verify business integration**

Run: `cd backend && uv run pytest tests/test_model_routing.py tests/test_model_gateway.py tests/test_model_gateway_api.py tests/test_openai_compatible_provider.py -v`

Expected: all selected tests pass.

- [ ] **Step 7: Commit Task 3**

```bash
git add .env.example backend/src/qunxue_api/adapters/model backend/src/qunxue_api/settings.py backend/src/qunxue_api/bootstrap.py backend/tests/test_model_gateway.py backend/tests/test_model_gateway_api.py backend/tests/test_health.py
git commit -m "feat(gateway): route business model calls"
```

### Task 4: Route Pydantic AI requests through the shared executor

**Files:**
- Modify: `backend/src/qunxue_api/adapters/research_agent/pydantic_runner.py`
- Modify: `backend/src/qunxue_api/adapters/research_agent/catalog_tools.py`
- Modify: `backend/src/qunxue_api/bootstrap.py`
- Test: `backend/tests/test_agent_conversation.py`

**Interfaces:**
- Consumes: application-scoped `ModelRouteExecutor` and safe context already bound through `bind_agent_context`.
- Produces: Pydantic AI model requests recorded with `agent_run_id` while using the normalized endpoints from Task 3.

- [ ] **Step 1: Write failing Agent routing tests**

```python
def test_agent_shared_router_records_primary_and_fallback_with_run_context(monkeypatch) -> None:
    attempts = InMemoryModelAttemptRecorder()
    router = ModelRouteExecutor(endpoints=_endpoints(), recorder=attempts)
    runner = PydanticAIKnowledgeRunner(
        base_url="https://primary.example.test/v1",
        api_key="primary-key",
        fallback_endpoints=(("https://backup.example.test/v1", "backup-key", "backup-model"),),
        model="primary-model",
        timeout_seconds=30,
        route_executor=router,
    )
    completed_request = object()

    async def request_once(self, *args, **kwargs):
        del args, kwargs
        if self.base_url.startswith("https://primary"):
            raise ModelHTTPError(status_code=429, model_name="primary-model", body={"message": "rate limited"})
        return completed_request

    monkeypatch.setattr(OpenAIChatModel, "_completions_create", request_once)
    with model_route_scope(task_id=TASK_ID, agent_run_id=AGENT_RUN_ID, capability="agent_completion"):
        result = asyncio.run(
            runner._agent.model._completions_create([], False, {}, ModelRequestParameters())
        )

    assert result is completed_request
    assert [item.endpoint_id for item in attempts.list_for_agent_run(AGENT_RUN_ID)] == [
        "primary",
        "fallback-1",
    ]
```

- [ ] **Step 2: Run Agent/settings tests and verify RED**

Run: `cd backend && uv run pytest tests/test_agent_conversation.py -k "shared_router" -v`

Expected: missing router injection or route-scope context lookup.

- [ ] **Step 3: Delegate Agent attempts to the shared executor**

Keep `_RetryingOpenAIChatModel` only as the Pydantic AI bridge. Remove its retry loop and same-base-url race. Each `_completions_create` call creates a fresh route ID and calls `execute_async`; endpoint-specific OpenAI models remain responsible for SDK serialization.

- [ ] **Step 4: Expose bound correlation without prompt data**

Add a read-only method on the tool registry returning only `user_id`, `task_id`, and `agent_run_id`. The runner must not copy prompt or material content into the route context.

- [ ] **Step 5: Verify Agent integration**

Run: `cd backend && uv run pytest tests/test_agent_conversation.py tests/test_api_key_runtime.py tests/test_health.py -v`

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 4**

```bash
git add backend/src/qunxue_api/adapters/research_agent backend/src/qunxue_api/bootstrap.py backend/tests/test_agent_conversation.py
git commit -m "feat(gateway): route agent model attempts"
```

### Task 5: Truthful health and release identity

**Files:**
- Modify: `backend/src/qunxue_api/api/contracts/health.py`
- Modify: `backend/src/qunxue_api/api/routes/health.py`
- Modify: `backend/src/qunxue_api/settings.py`
- Modify: `backend/src/qunxue_api/adapters/model/openai_compatible_provider.py`
- Modify: `backend/src/qunxue_api/adapters/model/routed_provider.py`
- Modify: `backend/src/qunxue_api/bootstrap.py`
- Modify: `.env.example`
- Test: `backend/tests/test_health.py`
- Test: `backend/tests/test_api_contract_freeze.py`

**Interfaces:**
- Consumes: `ModelRouteExecutor.health_snapshot`, model endpoint settings, application lifespan.
- Produces: compatible health response fields `model_status`, `model_checked_at`, `release_revision`; startup/interval probe lifecycle.

- [ ] **Step 1: Write failing health-contract tests**

```python
def test_health_reports_degraded_model_without_leaking_endpoints(client: TestClient) -> None:
    client.app.state.model_router.note_failure("primary", retryable=True, error_code="model_timeout")
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["model_status"] == "degraded"
    assert "base_url" not in response.text


def test_health_returns_503_when_all_real_endpoints_are_unavailable(client: TestClient) -> None:
    for _ in range(3):
        client.app.state.model_router.note_failure("primary", retryable=True, error_code="model_timeout")
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["model_status"] == "unavailable"


def test_health_exposes_configured_release_revision(client: TestClient) -> None:
    app = create_app(settings=_settings(client, release_revision="7e48edff"))
    with TestClient(app) as release_client:
        assert release_client.get("/api/health").json()["release_revision"] == "7e48edff"
```

- [ ] **Step 2: Run health tests and verify RED**

Run: `cd backend && uv run pytest tests/test_health.py -k "model_status or release_revision" -v`

Expected: missing response fields and model state handling.

- [ ] **Step 3: Extend the public contract with aggregate state**

Preserve every existing field. A 503 model response still uses `HealthResponse`, not the generic retrieval error envelope, so operators can read `model_status`. Retrieval failures keep their existing error envelope.

- [ ] **Step 4: Add bounded active probe lifecycle**

Add `probe()` to the OpenAI-compatible and routed providers. Install a daemon/background task in application lifespan only for real runtime. Probe immediately after startup without blocking startup, then wait 300 seconds between probes. Shutdown cancels and joins the task. The probe request uses capability `health_probe`, no user/task IDs, and a one-token completion. Tests use a fake probe and controllable clock; they never call the internet.

- [ ] **Step 5: Verify health, contract, and no-leak behavior**

Run: `cd backend && uv run pytest tests/test_health.py tests/test_api_contract_freeze.py -v`

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 5**

```bash
git add .env.example backend/src/qunxue_api/api/contracts/health.py backend/src/qunxue_api/api/routes/health.py backend/src/qunxue_api/adapters/model/openai_compatible_provider.py backend/src/qunxue_api/adapters/model/routed_provider.py backend/src/qunxue_api/settings.py backend/src/qunxue_api/bootstrap.py backend/tests/test_health.py backend/tests/test_api_contract_freeze.py
git commit -m "feat(gateway): report truthful model health"
```

### Task 6: Documentation and full verification

**Files:**
- Modify: `docs/engineering/ai-gateway-gap-analysis.md`
- Verify: all changed backend files and generated API contract.

**Interfaces:**
- Consumes: completed Tasks 1–5.
- Produces: reviewed implementation, current gap analysis, and clean generated contracts.

- [ ] **Step 1: Regenerate the OpenAPI contract**

Run: `cd backend && uv run python scripts/export_openapi.py`

Expected: `backend/openapi.json` changes only for the added health fields.

- [ ] **Step 2: Regenerate frontend API types**

Run: `cd frontend && npm ci --ignore-scripts && npm run generate:api`

Expected: generated health types include the three new fields and no unrelated contract drift.

- [ ] **Step 3: Run complete verification**

Run: `cd backend && uv run ruff check . && uv run pytest`

Run: `cd frontend && npm run check:boundaries && npm run lint && npm run test && npm run build`

Expected: every command exits zero.

- [ ] **Step 4: Review the complete diff for secrets and scope**

Run: `git diff origin/main --check`

Run: `git diff origin/main -- . ':!backend/openapi.json' ':!frontend/src/api/generated' | rg -n "(api[_-]?key\s*[=:]\s*['\"][^*]|Bearer\s+[A-Za-z0-9])"`

Expected: whitespace check exits zero; secret scan returns no credential-bearing additions.

- [ ] **Step 5: Commit documentation and generated contracts**

```bash
git add docs/engineering/ai-gateway-gap-analysis.md docs/superpowers backend/openapi.json frontend/src/api/generated
git commit -m "docs(gateway): document stabilization contract"
```
