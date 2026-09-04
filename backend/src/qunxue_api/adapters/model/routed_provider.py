"""Route business model capabilities through the shared executor."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from datetime import UTC, datetime
from threading import Lock
from typing import TypeVar
from uuid import uuid4

from qunxue_api.adapters.model.routing import (
    ModelAttemptFailure,
    ModelAttemptResult,
    ModelRouteContext,
    ModelRouteExecutor,
    ModelRoutesUnavailable,
)
from qunxue_api.adapters.model.types import (
    ModelProvider,
    ModelProviderDescriptor,
    ModelProviderFailure,
    ModelProviderResult,
    ModelScenario,
    ProbeableModelProvider,
)
from qunxue_api.modules.research_framework import (
    FrameworkAuditDraft,
    FrameworkVersionSnapshot,
    ResearchFrameworkDraft,
    ResearchFrameworkDraftInput,
)
from qunxue_api.modules.research_intake import PhenomenonCandidateDraft
from qunxue_api.modules.theory_matching import (
    TheoryJudgementDraft,
    TheoryJudgementInput,
)

OutputT = TypeVar("OutputT")
RouteT = TypeVar("RouteT")

_route_context: ContextVar[ModelRouteContext | None] = ContextVar(
    "business_model_route_context",
    default=None,
)
_RETRYABLE_FAILURE_CODES = frozenset(
    {"model_timeout", "model_unavailable", "model_rate_limited"}
)


@contextmanager
def business_model_route_context(
    context: ModelRouteContext,
) -> Iterator[ModelRouteContext]:
    token = _route_context.set(context)
    try:
        yield context
    finally:
        _route_context.reset(token)


class RoutedModelProvider:
    """Decorate endpoint-specific providers with ordered shared routing."""

    def __init__(
        self,
        *,
        providers: tuple[ProbeableModelProvider, ...],
        router: ModelRouteExecutor,
    ) -> None:
        endpoint_ids = router.endpoint_ids
        if len(endpoint_ids) != len(providers):
            raise ValueError("one model provider is required for every endpoint")
        if len(set(endpoint_ids)) != len(endpoint_ids):
            raise ValueError("model endpoint ids must be unique")
        if not providers:
            raise ValueError("at least one model provider is required")
        self._providers = dict(zip(endpoint_ids, providers, strict=True))
        self._router = router
        self._descriptor = providers[0].descriptor
        self._health_lock = Lock()
        self._health_checked_at: datetime | None = None

    @property
    def descriptor(self) -> ModelProviderDescriptor:
        return self._descriptor

    @property
    def health_checked_at(self) -> datetime | None:
        with self._health_lock:
            return self._health_checked_at

    async def probe(self) -> None:
        context = ModelRouteContext(
            trace_id=uuid4(),
            request_id=uuid4(),
            operation="health_probe",
            capability="health_probe",
        )
        try:
            await self._probe_route(context=context)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._note_health_checked()
            raise
        else:
            self._note_health_checked()

    def extract_phenomenon(
        self,
        *,
        raw_input: str,
        research_intent: str | None,
        context: str | None,
    ) -> ModelProviderResult[PhenomenonCandidateDraft]:
        return self._execute(
            operation="phenomenon_extraction",
            invoke=lambda provider: provider.extract_phenomenon(
                raw_input=raw_input,
                research_intent=research_intent,
                context=context,
            ),
        )

    def judge_candidate(
        self,
        *,
        input: TheoryJudgementInput,
    ) -> ModelProviderResult[TheoryJudgementDraft]:
        return self._execute(
            operation="candidate_judgement_and_rerank",
            invoke=lambda provider: provider.judge_candidate(input=input),
        )

    def draft_framework(
        self,
        *,
        input: ResearchFrameworkDraftInput,
    ) -> ModelProviderResult[ResearchFrameworkDraft]:
        return self._execute(
            operation="framework_draft",
            invoke=lambda provider: provider.draft_framework(input=input),
        )

    def audit_framework(
        self,
        *,
        framework: FrameworkVersionSnapshot,
    ) -> ModelProviderResult[FrameworkAuditDraft]:
        return self._execute(
            operation="framework_audit",
            invoke=lambda provider: provider.audit_framework(framework=framework),
        )

    def _execute(
        self,
        *,
        operation: str,
        invoke: Callable[[ModelProvider], ModelProviderResult[OutputT]],
    ) -> ModelProviderResult[OutputT]:
        context = _route_context.get() or ModelRouteContext(
            trace_id=uuid4(),
            request_id=uuid4(),
            operation=operation,
            capability=operation,
        )
        try:
            result, endpoint_id = self._route(context=context, invoke=invoke)
        finally:
            self._note_health_checked()

        return replace(
            result,
            selected_descriptor=self._providers[endpoint_id].descriptor,
        )

    def _route(
        self,
        *,
        context: ModelRouteContext,
        invoke: Callable[[ModelProvider], RouteT],
    ) -> tuple[RouteT, str]:
        last_failure: ModelProviderFailure | None = None

        def attempt(endpoint) -> ModelAttemptResult[RouteT]:
            nonlocal last_failure
            try:
                provider = self._providers[endpoint.endpoint_id]
            except KeyError as error:
                raise RuntimeError(
                    f"no model provider configured for endpoint {endpoint.endpoint_id}"
                ) from error
            try:
                result = invoke(provider)
            except ModelProviderFailure as error:
                error.selected_descriptor = provider.descriptor
                last_failure = error
                raise ModelAttemptFailure(
                    code=error.code,
                    retryable=error.code in _RETRYABLE_FAILURE_CODES,
                ) from error
            return ModelAttemptResult(value=result)

        try:
            routed = self._router.execute(context=context, invoke=attempt)
        except ModelAttemptFailure:
            if last_failure is None:
                raise
            raise last_failure from None
        except ModelRoutesUnavailable as error:
            raise ModelProviderFailure(
                code="model_unavailable",
                message="No model endpoints are currently available.",
                knowledge_release_id=None,
                scenario=ModelScenario.PROVIDER_UNAVAILABLE,
            ) from error

        return routed.value, routed.endpoint.endpoint_id

    async def _probe_route(self, *, context: ModelRouteContext) -> None:
        last_failure: ModelProviderFailure | None = None

        async def attempt(endpoint) -> ModelAttemptResult[None]:
            nonlocal last_failure
            try:
                provider = self._providers[endpoint.endpoint_id]
            except KeyError as error:
                raise RuntimeError(
                    f"no model provider configured for endpoint {endpoint.endpoint_id}"
                ) from error
            try:
                await provider.probe()
            except ModelProviderFailure as error:
                error.selected_descriptor = provider.descriptor
                last_failure = error
                raise ModelAttemptFailure(
                    code="model_probe_unavailable",
                    retryable=True,
                ) from error
            return ModelAttemptResult(value=None)

        try:
            await self._router.execute_async(context=context, invoke=attempt)
        except ModelAttemptFailure:
            if last_failure is None:
                raise
            raise last_failure from None
        except ModelRoutesUnavailable as error:
            raise ModelProviderFailure(
                code="model_probe_unavailable",
                message="No model endpoints are currently available for health probing.",
                knowledge_release_id=None,
                scenario=ModelScenario.PROVIDER_UNAVAILABLE,
            ) from error

    def _note_health_checked(self) -> None:
        with self._health_lock:
            self._health_checked_at = datetime.now(UTC)
