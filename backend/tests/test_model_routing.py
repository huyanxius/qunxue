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


def _endpoint(endpoint_id: str) -> ModelEndpoint:
    return ModelEndpoint(
        endpoint_id=endpoint_id,
        base_url=f"https://{endpoint_id}.example.test/v1",
        model="test-model",
        api_key=None,
        timeout_seconds=10,
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
