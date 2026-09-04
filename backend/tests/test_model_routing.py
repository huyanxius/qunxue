import asyncio
from uuid import UUID

import pytest

from qunxue_api.adapters.model.routing import (
    InMemoryModelAttemptRecorder,
    ModelAttemptFailure,
    ModelAttemptResult,
    ModelEndpoint,
    ModelRouteContext,
    ModelRouteExecutor,
    ModelRoutesUnavailable,
)


def test_routing_contracts_are_available_from_model_adapter_package() -> None:
    from qunxue_api.adapters.model import ModelEndpoint as public_endpoint
    from qunxue_api.adapters.model import ModelRouteExecutor as public_executor

    assert public_endpoint is ModelEndpoint
    assert public_executor is ModelRouteExecutor


def _endpoint(endpoint_id: str, *, provider: str | None = "test-provider") -> ModelEndpoint:
    return ModelEndpoint(
        endpoint_id=endpoint_id,
        base_url=f"https://{endpoint_id}.example.test/v1",
        model="test-model",
        api_key=None,
        timeout_seconds=10,
        provider=provider,
    )


def _endpoints() -> tuple[ModelEndpoint, ...]:
    return (_endpoint("primary"), _endpoint("backup"))


def _context() -> ModelRouteContext:
    return ModelRouteContext(
        trace_id=UUID(int=1),
        request_id=UUID(int=2),
        operation="test-operation",
    )


def _terminal_failure(calls: list[str], endpoint_id: str) -> ModelAttemptResult[str]:
    calls.append(endpoint_id)
    raise ModelAttemptFailure(
        code="invalid_request",
        retryable=False,
        message="invalid request",
    )


class MutableClock:
    def __init__(self) -> None:
        self._seconds = 0.0

    def __call__(self) -> float:
        return self._seconds

    def advance(self, *, seconds: float) -> None:
        self._seconds += seconds


def _retryable_failure(_: ModelEndpoint) -> ModelAttemptResult[object]:
    raise ModelAttemptFailure(code="model_timeout", retryable=True)


def _unexpected_call(_: ModelEndpoint) -> ModelAttemptResult[object]:
    raise AssertionError("an unavailable endpoint must not be invoked")


async def _async_fallback(endpoint: ModelEndpoint) -> ModelAttemptResult[str]:
    if endpoint.endpoint_id == "primary":
        raise ModelAttemptFailure(code="model_rate_limited", retryable=True)
    return ModelAttemptResult(value="backup", input_tokens=4, output_tokens=2)


def test_sync_route_uses_next_endpoint_only_after_retryable_failure() -> None:
    recorder = InMemoryModelAttemptRecorder()
    router = ModelRouteExecutor(endpoints=_endpoints(), recorder=recorder)

    result = router.execute(
        context=_context(),
        invoke=lambda endpoint: (
            (_ for _ in ()).throw(
                ModelAttemptFailure(code="model_rate_limited", retryable=True)
            )
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


def test_attempt_records_include_safe_route_correlation_and_fallback_metadata() -> None:
    recorder = InMemoryModelAttemptRecorder()
    context = ModelRouteContext(
        trace_id=UUID(int=1),
        request_id=UUID(int=2),
        operation="test-operation",
        route_id=UUID(int=3),
        task_id=UUID(int=4),
        agent_run_id=UUID(int=5),
        capability="theory_analysis",
    )
    router = ModelRouteExecutor(endpoints=_endpoints(), recorder=recorder)

    router.execute(
        context=context,
        invoke=lambda endpoint: (
            (_ for _ in ()).throw(
                ModelAttemptFailure(code="model_timeout", retryable=True)
            )
            if endpoint.endpoint_id == "primary"
            else ModelAttemptResult(value="backup")
        ),
    )

    first, second = recorder.list_all()
    assert (
        first.route_id,
        first.task_id,
        first.agent_run_id,
        first.capability,
        first.provider,
        first.model,
        first.fallback,
    ) == (
        UUID(int=3),
        UUID(int=4),
        UUID(int=5),
        "theory_analysis",
        "test-provider",
        "test-model",
        False,
    )
    assert second.fallback is True
    assert {
        "api_key",
        "base_url",
        "extra_headers",
        "prompt",
        "response",
    }.isdisjoint(first.__dataclass_fields__)


def test_skipped_primary_still_marks_first_backup_attempt_as_fallback() -> None:
    primary = _endpoint("primary", provider=None)
    backup = _endpoint("backup", provider=None)
    recorder = InMemoryModelAttemptRecorder()
    router = ModelRouteExecutor(
        endpoints=(primary, backup),
        recorder=recorder,
        failure_threshold=1,
    )
    router.note_failure(endpoint_id="primary", retryable=True)

    router.execute(
        context=_context(),
        invoke=lambda endpoint: ModelAttemptResult(value=endpoint.endpoint_id),
    )

    (record,) = recorder.list_all()
    assert record.endpoint_id == "backup"
    assert record.attempt_number == 1
    assert record.fallback is True
    assert record.route_id is not None
    assert record.capability == "test-operation"
    assert record.provider == "backup"


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

    assert router.health_snapshot().status == "unhealthy"
    with pytest.raises(ModelRoutesUnavailable):
        router.execute(context=_context(), invoke=_unexpected_call)

    clock.advance(seconds=30)
    assert router.health_snapshot().status == "unhealthy"

    result = router.execute(
        context=_context(),
        invoke=lambda _: (
            ModelAttemptResult(value="recovered")
            if router.health_snapshot().status == "recovering"
            else (_ for _ in ()).throw(AssertionError("half-open state was not visible"))
        ),
    )

    assert result.value == "recovered"
    assert router.health_snapshot().status == "healthy"


def _router_with_two_open_circuits(clock: MutableClock) -> ModelRouteExecutor:
    router = ModelRouteExecutor(
        endpoints=_endpoints(),
        failure_threshold=1,
        cooldown_seconds=30,
        clock=clock,
    )
    with pytest.raises(ModelAttemptFailure):
        router.execute(context=_context(), invoke=_retryable_failure)
    clock.advance(seconds=30)
    return router


def test_half_open_admits_only_the_endpoint_that_is_invoked_before_success() -> None:
    clock = MutableClock()
    router = _router_with_two_open_circuits(clock)

    result = router.execute(
        context=_context(),
        invoke=lambda endpoint: ModelAttemptResult(value=endpoint.endpoint_id),
    )

    assert result.value == "primary"
    assert [item.status for item in router.health_snapshot().endpoints] == [
        "healthy",
        "unhealthy",
    ]


def test_half_open_terminal_failure_settles_only_the_invoked_endpoint() -> None:
    clock = MutableClock()
    router = _router_with_two_open_circuits(clock)

    with pytest.raises(ModelAttemptFailure, match="invalid request"):
        router.execute(
            context=_context(),
            invoke=lambda _: (_ for _ in ()).throw(
                ModelAttemptFailure(
                    code="invalid_request",
                    retryable=False,
                    message="invalid request",
                )
            ),
        )

    assert [item.status for item in router.health_snapshot().endpoints] == [
        "healthy",
        "unhealthy",
    ]


def test_half_open_exception_settles_only_the_invoked_endpoint() -> None:
    clock = MutableClock()
    router = _router_with_two_open_circuits(clock)

    with pytest.raises(ValueError, match="unexpected"):
        router.execute(
            context=_context(),
            invoke=lambda _: (_ for _ in ()).throw(ValueError("unexpected")),
        )

    assert [item.status for item in router.health_snapshot().endpoints] == [
        "unhealthy",
        "unhealthy",
    ]


def test_health_state_tracks_unknown_degraded_unhealthy_recovering_and_healthy() -> None:
    clock = MutableClock()
    router = ModelRouteExecutor(
        endpoints=(_endpoint("primary"),),
        failure_threshold=3,
        cooldown_seconds=30,
        clock=clock,
    )

    assert router.health_snapshot().status == "unknown"
    for expected_status in ("degraded", "degraded", "unhealthy"):
        with pytest.raises(ModelAttemptFailure):
            router.execute(context=_context(), invoke=_retryable_failure)
        assert router.health_snapshot().status == expected_status

    clock.advance(seconds=30)
    assert router.health_snapshot().status == "unhealthy"

    router.execute(
        context=_context(),
        invoke=lambda _: (
            ModelAttemptResult(value="recovered")
            if router.health_snapshot().status == "recovering"
            else (_ for _ in ()).throw(AssertionError("probe was not recovering"))
        ),
    )

    assert router.health_snapshot().status == "healthy"


def test_sync_terminal_exception_is_recorded_once_without_fallback() -> None:
    recorder = InMemoryModelAttemptRecorder()
    calls: list[str] = []
    router = ModelRouteExecutor(endpoints=_endpoints(), recorder=recorder)

    with pytest.raises(ValueError, match="unexpected failure"):
        router.execute(
            context=_context(),
            invoke=lambda endpoint: _raise_unexpected(calls, endpoint.endpoint_id),
        )

    assert calls == ["primary"]
    assert [
        (item.endpoint_id, item.success, item.selected, item.failure_code, item.failure_retryable)
        for item in recorder.list_all()
    ] == [("primary", False, False, "model_attempt_exception", False)]
    assert "prompt=secret" not in repr(recorder.list_all()[0])


def test_terminal_exception_preserves_existing_degraded_health() -> None:
    router = ModelRouteExecutor(endpoints=(_endpoint("primary"),))
    for _ in range(2):
        with pytest.raises(ModelAttemptFailure):
            router.execute(context=_context(), invoke=_retryable_failure)

    with pytest.raises(ValueError, match="unexpected failure"):
        router.execute(
            context=_context(),
            invoke=lambda endpoint: _raise_unexpected([], endpoint.endpoint_id),
        )

    endpoint = router.health_snapshot().endpoints[0]
    assert endpoint.status == "degraded"
    assert endpoint.consecutive_retryable_failures == 2


def _raise_unexpected(calls: list[str], endpoint_id: str) -> ModelAttemptResult[object]:
    calls.append(endpoint_id)
    raise ValueError("unexpected failure; prompt=secret")


@pytest.mark.anyio
async def test_async_route_records_the_same_attempt_shape() -> None:
    recorder = InMemoryModelAttemptRecorder()
    router = ModelRouteExecutor(endpoints=_endpoints(), recorder=recorder)

    result = await router.execute_async(context=_context(), invoke=_async_fallback)

    assert result.value == "backup"
    assert [item.attempt_number for item in recorder.list_all()] == [1, 2]


@pytest.mark.anyio
async def test_async_terminal_exception_is_recorded_once_without_fallback() -> None:
    recorder = InMemoryModelAttemptRecorder()
    calls: list[str] = []
    router = ModelRouteExecutor(endpoints=_endpoints(), recorder=recorder)

    with pytest.raises(ValueError, match="unexpected failure"):
        await router.execute_async(
            context=_context(),
            invoke=lambda endpoint: _raise_unexpected_async(calls, endpoint.endpoint_id),
        )

    assert calls == ["primary"]
    assert [
        (item.endpoint_id, item.success, item.selected, item.failure_code, item.failure_retryable)
        for item in recorder.list_all()
    ] == [("primary", False, False, "model_attempt_exception", False)]
    assert "prompt=secret" not in repr(recorder.list_all()[0])


@pytest.mark.anyio
async def test_async_cancellation_releases_half_open_slot_and_records_once() -> None:
    clock = MutableClock()
    recorder = InMemoryModelAttemptRecorder()
    router = ModelRouteExecutor(
        endpoints=_endpoints(),
        recorder=recorder,
        failure_threshold=1,
        cooldown_seconds=30,
        clock=clock,
    )
    router.note_failure(endpoint_id="primary", retryable=True)
    clock.advance(seconds=30)
    calls: list[str] = []

    async def cancel(endpoint: ModelEndpoint) -> ModelAttemptResult[object]:
        calls.append(endpoint.endpoint_id)
        assert router.health_snapshot().endpoints[0].status == "recovering"
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await router.execute_async(context=_context(), invoke=cancel)

    assert router.health_snapshot().endpoints[0].status == "unhealthy"
    assert calls == ["primary"]
    assert [
        (item.endpoint_id, item.failure_code, item.failure_retryable, item.fallback)
        for item in recorder.list_all()
    ] == [("primary", "model_attempt_cancelled", False, False)]


async def _raise_unexpected_async(
    calls: list[str], endpoint_id: str
) -> ModelAttemptResult[object]:
    calls.append(endpoint_id)
    raise ValueError("unexpected failure; prompt=secret")
