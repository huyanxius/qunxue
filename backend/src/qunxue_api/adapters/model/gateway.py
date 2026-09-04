from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from typing import TypeVar, cast
from uuid import UUID, uuid4

from qunxue_api.adapters.model.routed_provider import business_model_route_context
from qunxue_api.adapters.model.routing import ModelRouteContext
from qunxue_api.adapters.model.types import (
    JsonObject,
    ModelCapabilityName,
    ModelInvocationError,
    ModelInvocationRecord,
    ModelInvocationRecorder,
    ModelProvider,
    ModelProviderFailure,
    ModelProviderResult,
    ModelScenario,
)
from qunxue_api.modules.research_framework import (
    FrameworkAuditDraft,
    FrameworkVersionSnapshot,
    ResearchFrameworkDraft,
    ResearchFrameworkDraftInput,
)
from qunxue_api.modules.research_intake import PhenomenonCandidateDraft
from qunxue_api.modules.theory_matching import (
    CandidateJudgementRunStatus,
    MatchCompletionBasis,
    TheoryJudgementBatchInput,
    TheoryJudgementBatchItemResult,
    TheoryJudgementBatchResult,
    TheoryJudgementVerdict,
)

ResultT = TypeVar("ResultT")


class ModelGateway:
    """Provider-neutral implementation of the four consumer-owned model ports."""

    def __init__(
        self,
        *,
        provider: ModelProvider,
        recorder: ModelInvocationRecorder,
        contract_version: str,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._provider = provider
        self._recorder = recorder
        self._contract_version = contract_version
        self._id_factory = id_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def descriptor(self):
        return self._provider.descriptor

    def build(
        self,
        *,
        task_id: UUID,
        raw_input: str,
        research_intent: str | None,
        context: str | None,
    ) -> PhenomenonCandidateDraft:
        safe_input: JsonObject = {
            "task_id": str(task_id),
            "raw_input_sha256": f"sha256:{sha256(raw_input.encode()).hexdigest()}",
            "raw_input_length": len(raw_input),
            "research_intent_present": research_intent is not None,
            "context_present": context is not None,
        }
        return self._invoke(
            capability=ModelCapabilityName.PHENOMENON_EXTRACTION,
            task_id=task_id,
            phenomenon=raw_input,
            input_evidence=safe_input,
            call=lambda: self._provider.extract_phenomenon(
                raw_input=raw_input,
                research_intent=research_intent,
                context=context,
            ),
        )

    def judge_and_rerank(
        self,
        *,
        input: TheoryJudgementBatchInput,
    ) -> TheoryJudgementBatchResult:
        input_order = tuple(item.candidate_id for item in input.items)
        target_ids = set(input.target_candidate_ids or input_order)
        results: list[TheoryJudgementBatchItemResult] = []
        retryable_ids: list[UUID] = []

        for item in input.items:
            if item.candidate_id not in target_ids:
                continue
            judgement_input = item.judgement_input
            trace_id = self._id_factory()
            request_id = self._id_factory()
            input_evidence: JsonObject = {
                "candidate_id": str(item.candidate_id),
                "candidate_version": item.candidate_version,
                "input_candidate_order": [str(value) for value in input_order],
                "target_candidate_ids": [
                    str(value) for value in input.target_candidate_ids
                ],
                "knowledge_release": _to_jsonable(
                    judgement_input.knowledge_release
                ),
                "phenomenon": _to_jsonable(judgement_input.phenomenon),
                "candidate": _to_jsonable(judgement_input.candidate),
                "comparison_candidate_theory_ids": [
                    candidate.theory_id
                    for candidate in judgement_input.comparison_candidates
                ],
                "evidence_ref_ids": [
                    evidence.evidence_ref_id
                    for evidence in judgement_input.evidence_items
                ],
                "evidence": _to_jsonable(judgement_input.evidence_items),
            }
            try:
                judgement = self._invoke(
                    capability=(
                        ModelCapabilityName.CANDIDATE_JUDGEMENT_AND_RERANK
                    ),
                    task_id=judgement_input.phenomenon.task_id,
                    phenomenon=judgement_input.phenomenon.phenomenon,
                    input_evidence=input_evidence,
                    call=lambda judgement_input=judgement_input: (
                        self._provider.judge_candidate(input=judgement_input)
                    ),
                    trace_id=trace_id,
                    request_id=request_id,
                )
            except ModelInvocationError as error:
                status = {
                    "model_timeout": CandidateJudgementRunStatus.TIMED_OUT,
                    "insufficient_sources": (
                        CandidateJudgementRunStatus.INSUFFICIENT_SOURCES
                    ),
                }.get(error.code, CandidateJudgementRunStatus.FAILED)
                if error.code in {
                    "model_timeout",
                    "model_unavailable",
                    "model_rate_limited",
                    "model_invalid_output",
                    "insufficient_sources",
                }:
                    retryable_ids.append(item.candidate_id)
                results.append(
                    TheoryJudgementBatchItemResult(
                        candidate_id=item.candidate_id,
                        candidate_version=item.candidate_version,
                        status=status,
                        judgement=None,
                        failure_code=error.code,
                        trace_id=error.trace_id,
                        request_id=error.request_id,
                        contract_version=self._contract_version,
                    )
                )
                continue

            results.append(
                TheoryJudgementBatchItemResult(
                    candidate_id=item.candidate_id,
                    candidate_version=item.candidate_version,
                    status=CandidateJudgementRunStatus.SUCCEEDED,
                    judgement=judgement,
                    failure_code=None,
                    trace_id=trace_id,
                    request_id=request_id,
                    contract_version=self._contract_version,
                )
            )

        result_by_id = {result.candidate_id: result for result in results}
        ranked_order = tuple(
            sorted(
                input_order,
                key=lambda candidate_id: _judgement_rank(
                    result_by_id.get(candidate_id)
                ),
            )
        )
        completed = len(results) == len(input.items) and all(
            result.status is CandidateJudgementRunStatus.SUCCEEDED
            for result in results
        )
        return TheoryJudgementBatchResult(
            results=tuple(results),
            input_candidate_order=input_order,
            ranked_candidate_order=ranked_order,
            completion_basis=(
                MatchCompletionBasis.COMPLETE
                if completed
                else MatchCompletionBasis.PARTIAL
            ),
            retryable_candidate_ids=tuple(retryable_ids),
        )

    def draft(self, *, input: ResearchFrameworkDraftInput) -> ResearchFrameworkDraft:
        return self._invoke(
            capability=ModelCapabilityName.FRAMEWORK_DRAFT,
            task_id=input.theory_plan.task_id,
            phenomenon=input.theory_plan.phenomenon.phenomenon,
            input_evidence=cast(JsonObject, _to_jsonable(input)),
            call=lambda: self._provider.draft_framework(input=input),
        )

    def audit(self, *, framework: FrameworkVersionSnapshot) -> FrameworkAuditDraft:
        return self._invoke(
            capability=ModelCapabilityName.FRAMEWORK_AUDIT,
            task_id=framework.task_id,
            phenomenon=framework.input.theory_plan.phenomenon.phenomenon,
            input_evidence=cast(JsonObject, _to_jsonable(framework)),
            call=lambda: self._provider.audit_framework(framework=framework),
        )

    def _invoke(
        self,
        *,
        capability: ModelCapabilityName,
        task_id: UUID,
        phenomenon: str,
        input_evidence: JsonObject,
        call: Callable[[], ModelProviderResult[ResultT]],
        trace_id: UUID | None = None,
        request_id: UUID | None = None,
    ) -> ResultT:
        trace_id = trace_id or self._id_factory()
        request_id = request_id or self._id_factory()
        started_at = self._clock()
        descriptor = self._provider.descriptor
        scenario = self._scenario_for_phenomenon(phenomenon)
        try:
            with business_model_route_context(
                ModelRouteContext(
                    trace_id=trace_id,
                    request_id=request_id,
                    operation=capability.value,
                    task_id=task_id,
                    capability=capability.value,
                )
            ):
                result = call()
        except ModelProviderFailure as error:
            completed_at = self._clock()
            self._recorder.record(
                ModelInvocationRecord(
                    trace_id=trace_id,
                    request_id=request_id,
                    task_id=task_id,
                    contract_version=self._contract_version,
                    capability=capability,
                    provider=descriptor.provider,
                    model_version=descriptor.model_version,
                    capability_tier=descriptor.capability_tier,
                    demonstration=descriptor.demonstration,
                    scenario=error.scenario,
                    input_evidence=input_evidence,
                    output=None,
                    knowledge_release_id=error.knowledge_release_id,
                    degraded=True,
                    degradation_reason=str(error),
                    error_code=error.code,
                    started_at=started_at,
                    completed_at=completed_at,
                )
            )
            raise ModelInvocationError(
                code=error.code,
                message=str(error),
                trace_id=trace_id,
                request_id=request_id,
                provider=descriptor.provider,
            ) from error

        completed_at = self._clock()
        descriptor = result.selected_descriptor or descriptor
        output = _to_jsonable(result.output)
        if not isinstance(output, dict):
            raise TypeError("model provider output must serialize to an object")
        self._recorder.record(
            ModelInvocationRecord(
                trace_id=trace_id,
                request_id=request_id,
                task_id=task_id,
                contract_version=self._contract_version,
                capability=capability,
                provider=descriptor.provider,
                model_version=descriptor.model_version,
                capability_tier=descriptor.capability_tier,
                demonstration=descriptor.demonstration,
                scenario=scenario,
                input_evidence=input_evidence,
                output=output,
                knowledge_release_id=result.knowledge_release_id,
                degraded=result.degraded,
                degradation_reason=result.degradation_reason,
                error_code=None,
                started_at=started_at,
                completed_at=completed_at,
            )
        )
        return result.output

    def _scenario_for_phenomenon(self, phenomenon: str) -> ModelScenario:
        selector = getattr(self._provider, "scenario_for_phenomenon", None)
        if selector is None:
            return ModelScenario.SUCCESS
        return ModelScenario(selector(phenomenon))


def _judgement_rank(result: TheoryJudgementBatchItemResult | None) -> int:
    if result is None or result.judgement is None:
        return 4
    return {
        TheoryJudgementVerdict.APPLICABLE: 0,
        TheoryJudgementVerdict.CONDITIONAL: 1,
        TheoryJudgementVerdict.INSUFFICIENT: 2,
        TheoryJudgementVerdict.NOT_APPLICABLE: 3,
    }[result.judgement.verdict]

def _to_jsonable(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported model trace value: {type(value).__name__}")
