# AI Gateway Stabilization Design

## Goal

Make every real model request in Qunxue use one in-process routing policy that records each upstream attempt, isolates repeatedly failing endpoints, and reports truthful model availability without turning Qunxue into a public model-resale gateway.

## Scope

This change covers the two existing model paths:

- business capabilities through `ModelGateway` and `ModelProvider`;
- Agent requests through `PydanticAIKnowledgeRunner` and Pydantic AI.

It does not add a public `/v1/chat/completions` API, developer API keys, BYOK, pricing administration, online payments, or a provider-management UI.

The production-only evidence-limit failure and deployment cleanup are tracked separately. They must not be hidden inside the gateway refactor.

## Current failure mode

The business path records one final `model_invocations` row but has no fallback. The Agent path implements its own retry and fallback logic in `_RetryingOpenAIChatModel`, but only the final Agent run and aggregate usage are persisted. `/api/health` checks database and retrieval readiness and then returns the statically configured provider and model.

As a result, the same upstream failure has different behavior in each path, an Agent fallback cannot be reconstructed after the fact, and a successful health response does not prove that a completion endpoint is usable.

## Chosen architecture

### Shared route policy

Add `qunxue_api.adapters.model.routing` as a provider-neutral policy module. It owns:

- the ordered endpoint list;
- retry eligibility;
- endpoint circuit state;
- sync and async attempt execution;
- one attempt record for every upstream call.

The executor accepts an invocation callback, so it does not parse business outputs or depend on Pydantic AI types. Existing adapters retain response parsing and domain validation.

```python
@dataclass(frozen=True, slots=True)
class ModelEndpoint:
    endpoint_id: str
    base_url: str
    model: str
    api_key: str | None
    timeout_seconds: float
    extra_headers: Mapping[str, str]

@dataclass(frozen=True, slots=True)
class ModelRouteContext:
    route_id: UUID
    trace_id: UUID
    request_id: UUID
    capability: str
    task_id: UUID | None = None
    agent_run_id: UUID | None = None

class ModelRouteExecutor:
    def execute(
        self,
        *,
        context: ModelRouteContext,
        invoke: Callable[[ModelEndpoint], ModelAttemptResult[T]],
    ) -> ModelRouteResult[T]: ...

    async def execute_async(
        self,
        *,
        context: ModelRouteContext,
        invoke: Callable[[ModelEndpoint], Awaitable[ModelAttemptResult[T]]],
    ) -> ModelRouteResult[T]: ...
```

The routing module also exposes `model_route_scope(...)`, backed by a `ContextVar`, so the Agent application can bind `task_id` and `agent_run_id` around a Pydantic AI run without adding those fields to SDK request bodies.

Both methods use the same endpoint selection and state-transition functions. They try endpoints sequentially. There is no implicit racing because it can duplicate billed requests and makes the winning attempt ambiguous.

### Retry classification

Only the following conditions permit another endpoint attempt:

- connection and transport failures;
- timeout;
- HTTP 408, 409, 429;
- HTTP 5xx;
- the existing narrowly recognized transient `unknown provider for model` response.

Authentication, authorization, request validation, and invalid structured output remain terminal for the current request. A terminal request error does not poison endpoint health unless it proves endpoint configuration is unusable.

### Circuit state

Each endpoint starts as `unknown`. State changes are protected by a lock and are shared by both call paths in the application process.

- success: `healthy`, failure counter reset;
- first or second retryable failure: `degraded`;
- third consecutive retryable failure: `unhealthy`, circuit open for 30 seconds;
- after cooldown: one request is admitted as `recovering`;
- recovery success: `healthy`;
- recovery failure: `unhealthy` for another cooldown.

The thresholds are settings with defaults of three failures and 30 seconds. In-process state matches the current single-PM2-process SQLite deployment. Attempt history remains durable and can later seed multi-process state without changing the public contract.

### Attempt audit

Add `model_route_attempts`. Every row represents one actual upstream request.

Required fields:

- `attempt_id`, `route_id`, `trace_id`, `request_id`;
- optional `task_id` and `agent_run_id` correlation;
- capability, endpoint ID, provider, model, attempt number, fallback flag;
- start, completion, latency;
- success, selected, retryable, error code;
- input and output token counts when the adapter exposes them.

Rows never contain provider credentials, cookies, complete prompts, private material text, or raw provider response bodies. Existing `model_invocations` remains the business-level outcome record for compatibility.

### Business integration

Introduce a routed `ModelProvider` decorator. It maps each configured endpoint to an `OpenAICompatibleModelProvider`, invokes the requested domain method through `ModelRouteExecutor`, and returns the selected provider result. `ModelGateway` keeps responsibility for business trace IDs and final domain-level invocation records.

### Agent integration

Replace retry decisions inside `_RetryingOpenAIChatModel` with `ModelRouteExecutor.execute_async`. Pydantic AI continues to own the model/tool loop, response events, and usage calculation. `DisciplinaryAgentApplication` already binds `user_id`, `task_id`, and `agent_run_id` into the tool registry before the model call; the runner reads that scoped context and enters `model_route_scope` while Pydantic AI runs. Each SDK completion request creates fresh route, trace, and request IDs inside that scope.

Fallback endpoints may specify their own `model`. Legacy fallback objects containing only `base_url` and `api_key` inherit the primary model.

### Health contract

Keep `/api/health` backward compatible and add:

```json
{
  "model_status": "unknown | healthy | degraded | unavailable | recovering",
  "model_checked_at": "ISO-8601 timestamp or null",
  "release_revision": "deployment revision or unknown"
}
```

The public response contains no endpoint URLs or credential identifiers. `unavailable` causes HTTP 503 only when every configured real endpoint is circuit-open or a fresh probe proves all are unavailable. `unknown` and `degraded` keep the application reachable while reporting the truthful state.

The executor passively updates health from normal traffic. A low-cost active probe is run at application startup and then at most once per configured interval, default 300 seconds. The probe uses the same route executor, a one-token completion, and capability `health_probe`. Mock mode performs no external probe and reports `healthy`.

### Deployment identity

Add `QUNXUE_RELEASE_REVISION`, defaulting to `unreleased`. Deployment must set it to the exact release commit. The health response exposes this value so an operator can verify that the code serving traffic matches the intended revision; the default is deliberately not a deployment claim.

## Compatibility

- Existing settings continue to work.
- Existing health fields and business `model_invocations` remain present.
- Mock mode makes no network requests.
- Fallback order remains primary first, then configured backups, but same-base-url racing is intentionally removed.
- Existing Agent SSE events and client contracts do not change.

## Verification

Tests must prove:

- retryable failures move to the next endpoint and non-retryable failures do not;
- three consecutive retryable failures open the circuit and cooldown admits recovery;
- sync business calls and async Agent calls create the same attempt shape;
- attempt persistence contains correlation and telemetry but no prompt or secret fields;
- health distinguishes unknown, degraded, unavailable, recovering, and healthy;
- mock mode never probes externally;
- fallback-specific model names and legacy fallback configuration both work;
- the full migration chain matches ORM metadata;
- Ruff and the complete backend suite pass.

## Operational contract

### Configuration and migration

`QUNXUE_MODEL_FALLBACKS` is an ordered JSON list. Every entry has an HTTP(S), credential-free `base_url`, a secret `api_key`, and an optional non-empty `model`; omitted fallback models inherit the primary model. `QUNXUE_MODEL_PROBE_INTERVAL_SECONDS` defaults to 300. `QUNXUE_RELEASE_REVISION` must be set by the deployed release, never inferred from a stale marker file.

Apply revision `20260905_0340` with the normal Alembic chain before the new application receives traffic. The migration creates `model_route_attempts`; it is reversible in the migration order, but production rollback requires a backup and confirmation that no later release depends on the table.

### Health and probe lifecycle

The route executor has an internal `recovering` state, but the public response intentionally reports it as `degraded`. Public `model_status` is therefore `unknown`, `healthy`, `degraded`, or `unavailable`. Only aggregate `unavailable` produces a model `503 HealthResponse`; retrieval failures retain their existing error envelope. `model_checked_at` is the latest probe/check timestamp, not proof that every business operation will succeed.

For real runtime, the lifespan task probes asynchronously at startup, waits the configured interval between later probes, and is cancelled and awaited at shutdown. It uses the same executor with capability `health_probe`, has no user/task correlation, and performs no probe at all in mock mode.

### Audit safety

An attempt row contains correlation IDs, capability, endpoint ID, provider/model names, ordering/selection flags, timestamps, latency, error classification, and optional token counts. It must never contain endpoint URL, header, cookie, credential, prompt, private material text, request body, or raw provider response body. Operators correlate attempts with `route_id`, `trace_id`, or `agent_run_id`.

## Delivery state

The implementation is present on the local stabilization branch. This document does not assert a production repair: the branch has not been deployed, pushed, or opened as a PR. Deployment verification must confirm the release revision at the public health endpoint, migration state, no sensitive health/audit output, primary/fallback behavior, and clean probe shutdown before the change is called operational.
