"""Provider-neutral endpoint routing and attempt recording."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from time import monotonic
from typing import Protocol, TypeVar
from uuid import UUID, uuid4

ResultT = TypeVar("ResultT")


@dataclass(frozen=True, slots=True)
class ModelEndpoint:
    endpoint_id: str
    base_url: str
    model: str
    api_key: str | None = field(repr=False)
    timeout_seconds: float
    provider: str | None = None
    extra_headers: Mapping[str, str] = field(default_factory=dict, repr=False)


@dataclass(frozen=True, slots=True)
class ModelRouteContext:
    trace_id: UUID
    request_id: UUID
    operation: str
    route_id: UUID | None = None
    task_id: UUID | None = None
    agent_run_id: UUID | None = None
    capability: str | None = None


@dataclass(frozen=True, slots=True)
class ModelRouteScope:
    context: ModelRouteContext
    endpoint: ModelEndpoint
    attempt_number: int


_route_scope: ContextVar[ModelRouteScope | None] = ContextVar(
    "model_route_scope",
    default=None,
)


@contextmanager
def model_route_scope(scope: ModelRouteScope) -> Iterator[ModelRouteScope]:
    token = _route_scope.set(scope)
    try:
        yield scope
    finally:
        _route_scope.reset(token)


def current_model_route_scope() -> ModelRouteScope | None:
    return _route_scope.get()


class ModelAttemptFailure(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        retryable: bool,
        message: str = "model attempt failed",
    ) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(message)


class ModelRoutesUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ModelAttemptResult[ResultT]:
    value: ResultT
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ModelRouteResult[ResultT]:
    value: ResultT
    endpoint: ModelEndpoint
    input_tokens: int | None
    output_tokens: int | None


@dataclass(frozen=True, slots=True)
class ModelAttemptRecord:
    attempt_id: UUID
    context: ModelRouteContext
    endpoint_id: str
    route_id: UUID | None
    task_id: UUID | None
    agent_run_id: UUID | None
    capability: str | None
    provider: str | None
    model: str
    fallback: bool
    attempt_number: int
    success: bool
    selected: bool
    input_tokens: int | None
    output_tokens: int | None
    failure_code: str | None
    failure_retryable: bool | None
    started_at: datetime
    completed_at: datetime


class ModelAttemptRecorder(Protocol):
    def record(self, attempt: ModelAttemptRecord) -> None: ...


class InMemoryModelAttemptRecorder:
    def __init__(self) -> None:
        self._attempts: list[ModelAttemptRecord] = []

    def record(self, attempt: ModelAttemptRecord) -> None:
        self._attempts.append(attempt)

    def list_all(self) -> tuple[ModelAttemptRecord, ...]:
        return tuple(self._attempts)


@dataclass(frozen=True, slots=True)
class ModelEndpointHealth:
    endpoint_id: str
    status: str
    consecutive_retryable_failures: int
    cooldown_until: float | None


@dataclass(frozen=True, slots=True)
class ModelHealthSnapshot:
    status: str
    endpoints: tuple[ModelEndpointHealth, ...]


@dataclass(slots=True)
class _EndpointCircuitState:
    consecutive_retryable_failures: int = 0
    cooldown_until: float | None = None
    recovering: bool = False
    successful: bool = False


class ModelRouteExecutor:
    def __init__(
        self,
        *,
        endpoints: tuple[ModelEndpoint, ...],
        recorder: ModelAttemptRecorder | None = None,
        id_factory: Callable[[], UUID] = uuid4,
        wall_clock: Callable[[], datetime] | None = None,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be positive")
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must not be negative")
        endpoint_ids = tuple(endpoint.endpoint_id for endpoint in endpoints)
        if len(set(endpoint_ids)) != len(endpoint_ids):
            raise ValueError("model endpoint ids must be unique")
        self._endpoints = endpoints
        self._recorder = recorder
        self._id_factory = id_factory
        self._wall_clock = wall_clock or (lambda: datetime.now(UTC))
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._lock = Lock()
        self._circuits = {
            endpoint.endpoint_id: _EndpointCircuitState() for endpoint in endpoints
        }

    def execute(
        self,
        *,
        context: ModelRouteContext,
        invoke: Callable[[ModelEndpoint], ModelAttemptResult[ResultT]],
    ) -> ModelRouteResult[ResultT]:
        last_failure: ModelAttemptFailure | None = None
        attempt_number = 0
        for endpoint in self._endpoints:
            if not self._admit_endpoint(endpoint):
                continue
            attempt_number += 1
            started_at = self._wall_clock()
            try:
                with model_route_scope(
                    ModelRouteScope(
                        context=context,
                        endpoint=endpoint,
                        attempt_number=attempt_number,
                    )
                ):
                    result = invoke(endpoint)
            except ModelAttemptFailure as failure:
                self.note_failure(
                    endpoint_id=endpoint.endpoint_id,
                    retryable=failure.retryable,
                )
                self._record_failure(
                    context=context,
                    endpoint=endpoint,
                    attempt_number=attempt_number,
                    failure=failure,
                    started_at=started_at,
                )
                if not failure.retryable:
                    self._note_success(endpoint.endpoint_id)
                    raise
                last_failure = failure
                continue
            except Exception:
                self._note_success(endpoint.endpoint_id)
                self._record_terminal_exception(
                    context=context,
                    endpoint=endpoint,
                    attempt_number=attempt_number,
                    started_at=started_at,
                )
                raise

            self._note_success(endpoint.endpoint_id)
            self._record_success(
                context=context,
                endpoint=endpoint,
                attempt_number=attempt_number,
                result=result,
                started_at=started_at,
            )
            return ModelRouteResult(
                value=result.value,
                endpoint=endpoint,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
            )

        if last_failure is not None:
            raise last_failure
        raise ModelRoutesUnavailable("no model endpoints are currently available")

    async def execute_async(
        self,
        *,
        context: ModelRouteContext,
        invoke: Callable[[ModelEndpoint], Awaitable[ModelAttemptResult[ResultT]]],
    ) -> ModelRouteResult[ResultT]:
        last_failure: ModelAttemptFailure | None = None
        attempt_number = 0
        for endpoint in self._endpoints:
            if not self._admit_endpoint(endpoint):
                continue
            attempt_number += 1
            started_at = self._wall_clock()
            try:
                with model_route_scope(
                    ModelRouteScope(
                        context=context,
                        endpoint=endpoint,
                        attempt_number=attempt_number,
                    )
                ):
                    result = await invoke(endpoint)
            except ModelAttemptFailure as failure:
                self.note_failure(
                    endpoint_id=endpoint.endpoint_id,
                    retryable=failure.retryable,
                )
                self._record_failure(
                    context=context,
                    endpoint=endpoint,
                    attempt_number=attempt_number,
                    failure=failure,
                    started_at=started_at,
                )
                if not failure.retryable:
                    self._note_success(endpoint.endpoint_id)
                    raise
                last_failure = failure
                continue
            except Exception:
                self._note_success(endpoint.endpoint_id)
                self._record_terminal_exception(
                    context=context,
                    endpoint=endpoint,
                    attempt_number=attempt_number,
                    started_at=started_at,
                )
                raise

            self._note_success(endpoint.endpoint_id)
            self._record_success(
                context=context,
                endpoint=endpoint,
                attempt_number=attempt_number,
                result=result,
                started_at=started_at,
            )
            return ModelRouteResult(
                value=result.value,
                endpoint=endpoint,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
            )

        if last_failure is not None:
            raise last_failure
        raise ModelRoutesUnavailable("no model endpoints are currently available")

    def note_failure(self, *, endpoint_id: str, retryable: bool) -> None:
        if not retryable:
            return
        with self._lock:
            state = self._circuit_for(endpoint_id)
            state.consecutive_retryable_failures += 1
            if state.consecutive_retryable_failures >= self._failure_threshold:
                state.cooldown_until = self._clock() + self._cooldown_seconds
                state.recovering = False

    def health_snapshot(self) -> ModelHealthSnapshot:
        with self._lock:
            endpoints = tuple(
                ModelEndpointHealth(
                    endpoint_id=endpoint.endpoint_id,
                    status=self._status_for(self._circuit_for(endpoint.endpoint_id)),
                    consecutive_retryable_failures=self._circuit_for(
                        endpoint.endpoint_id
                    ).consecutive_retryable_failures,
                    cooldown_until=self._circuit_for(endpoint.endpoint_id).cooldown_until,
                )
                for endpoint in self._endpoints
            )
        return ModelHealthSnapshot(
            status=self._aggregate_status(endpoints),
            endpoints=endpoints,
        )

    def _admit_endpoint(self, endpoint: ModelEndpoint) -> bool:
        with self._lock:
            now = self._clock()
            state = self._circuit_for(endpoint.endpoint_id)
            if state.cooldown_until is None:
                return True
            if state.recovering or now < state.cooldown_until:
                return False
            state.recovering = True
            return True

    def _note_success(self, endpoint_id: str) -> None:
        with self._lock:
            state = self._circuit_for(endpoint_id)
            state.consecutive_retryable_failures = 0
            state.cooldown_until = None
            state.recovering = False
            state.successful = True

    def _circuit_for(self, endpoint_id: str) -> _EndpointCircuitState:
        try:
            return self._circuits[endpoint_id]
        except KeyError as error:
            raise ValueError(f"unknown model endpoint: {endpoint_id}") from error

    @staticmethod
    def _status_for(state: _EndpointCircuitState) -> str:
        if state.cooldown_until is not None and state.recovering:
            return "recovering"
        if state.cooldown_until is not None:
            return "unhealthy"
        if state.consecutive_retryable_failures:
            return "degraded"
        if state.successful:
            return "healthy"
        return "unknown"

    @staticmethod
    def _aggregate_status(endpoints: tuple[ModelEndpointHealth, ...]) -> str:
        statuses = {endpoint.status for endpoint in endpoints}
        if not statuses or statuses == {"unknown"}:
            return "unknown"
        if statuses == {"healthy"}:
            return "healthy"
        if statuses == {"unhealthy"}:
            return "unhealthy"
        if statuses <= {"unhealthy", "recovering"} and "recovering" in statuses:
            return "recovering"
        return "degraded"

    def _record_success(
        self,
        *,
        context: ModelRouteContext,
        endpoint: ModelEndpoint,
        attempt_number: int,
        result: ModelAttemptResult[object],
        started_at: datetime,
    ) -> None:
        self._record(
            ModelAttemptRecord(
                attempt_id=self._id_factory(),
                context=context,
                endpoint_id=endpoint.endpoint_id,
                route_id=context.route_id,
                task_id=context.task_id,
                agent_run_id=context.agent_run_id,
                capability=context.capability,
                provider=endpoint.provider,
                model=endpoint.model,
                fallback=attempt_number > 1,
                attempt_number=attempt_number,
                success=True,
                selected=True,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                failure_code=None,
                failure_retryable=None,
                started_at=started_at,
                completed_at=self._wall_clock(),
            )
        )

    def _record_failure(
        self,
        *,
        context: ModelRouteContext,
        endpoint: ModelEndpoint,
        attempt_number: int,
        failure: ModelAttemptFailure,
        started_at: datetime,
    ) -> None:
        self._record(
            ModelAttemptRecord(
                attempt_id=self._id_factory(),
                context=context,
                endpoint_id=endpoint.endpoint_id,
                route_id=context.route_id,
                task_id=context.task_id,
                agent_run_id=context.agent_run_id,
                capability=context.capability,
                provider=endpoint.provider,
                model=endpoint.model,
                fallback=attempt_number > 1,
                attempt_number=attempt_number,
                success=False,
                selected=False,
                input_tokens=None,
                output_tokens=None,
                failure_code=failure.code,
                failure_retryable=failure.retryable,
                started_at=started_at,
                completed_at=self._wall_clock(),
            )
        )

    def _record_terminal_exception(
        self,
        *,
        context: ModelRouteContext,
        endpoint: ModelEndpoint,
        attempt_number: int,
        started_at: datetime,
    ) -> None:
        self._record(
            ModelAttemptRecord(
                attempt_id=self._id_factory(),
                context=context,
                endpoint_id=endpoint.endpoint_id,
                route_id=context.route_id,
                task_id=context.task_id,
                agent_run_id=context.agent_run_id,
                capability=context.capability,
                provider=endpoint.provider,
                model=endpoint.model,
                fallback=attempt_number > 1,
                attempt_number=attempt_number,
                success=False,
                selected=False,
                input_tokens=None,
                output_tokens=None,
                failure_code="model_attempt_exception",
                failure_retryable=False,
                started_at=started_at,
                completed_at=self._wall_clock(),
            )
        )

    def _record(self, attempt: ModelAttemptRecord) -> None:
        if self._recorder is not None:
            self._recorder.record(attempt)
