from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from typing import TypeVar, cast
from uuid import UUID, uuid4

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
    TheoryJudgementDraft,
    TheoryJudgementInput,
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

    def judge(self, *, input: TheoryJudgementInput) -> TheoryJudgementDraft:
        input_evidence: JsonObject = {
            "phenomenon": _to_jsonable(input.phenomenon),
            "candidate": _to_jsonable(input.candidate),
            "comparison_candidate_theory_ids": [
                candidate.theory_id for candidate in input.comparison_candidates
            ],
            "evidence_ref_ids": [
                evidence.evidence_ref_id for evidence in input.evidence_items
            ],
            "evidence": _to_jsonable(input.evidence_items),
        }
        return self._invoke(
            capability=ModelCapabilityName.CANDIDATE_JUDGEMENT_AND_RERANK,
            task_id=input.phenomenon.task_id,
            phenomenon=input.phenomenon.phenomenon,
            input_evidence=input_evidence,
            call=lambda: self._provider.judge_candidate(input=input),
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
    ) -> ResultT:
        trace_id = self._id_factory()
        request_id = self._id_factory()
        started_at = self._clock()
        descriptor = self._provider.descriptor
        scenario = self._scenario_for_phenomenon(phenomenon)
        try:
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
