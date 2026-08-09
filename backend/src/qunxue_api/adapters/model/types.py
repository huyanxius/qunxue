from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

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


class ModelCapabilityName(StrEnum):
    PHENOMENON_EXTRACTION = "phenomenon_extraction"
    CANDIDATE_JUDGEMENT_AND_RERANK = "candidate_judgement_and_rerank"
    FRAMEWORK_DRAFT = "framework_draft"
    FRAMEWORK_AUDIT = "framework_audit"


class ModelScenario(StrEnum):
    SUCCESS = "success"
    NO_RELIABLE_CANDIDATE = "no_reliable_candidate"
    TIMEOUT = "timeout"
    INSUFFICIENT_SOURCES = "insufficient_sources"
    USER_DEFERRED = "user_deferred"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    RATE_LIMITED = "rate_limited"
    INVALID_OUTPUT = "invalid_output"


@dataclass(frozen=True, slots=True)
class ModelProviderDescriptor:
    provider: str
    model_version: str
    capability_tier: str
    demonstration: bool


@dataclass(frozen=True, slots=True)
class ModelProviderResult[OutputT]:
    output: OutputT
    knowledge_release_id: str | None
    degraded: bool = False
    degradation_reason: str | None = None


class ModelProviderFailure(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        knowledge_release_id: str | None,
        scenario: ModelScenario,
    ) -> None:
        self.code = code
        self.knowledge_release_id = knowledge_release_id
        self.scenario = scenario
        super().__init__(message)


class ModelProvider(Protocol):
    @property
    def descriptor(self) -> ModelProviderDescriptor: ...

    def extract_phenomenon(
        self,
        *,
        raw_input: str,
        research_intent: str | None,
        context: str | None,
    ) -> ModelProviderResult[PhenomenonCandidateDraft]: ...

    def judge_candidate(
        self,
        *,
        input: TheoryJudgementInput,
    ) -> ModelProviderResult[TheoryJudgementDraft]: ...

    def draft_framework(
        self,
        *,
        input: ResearchFrameworkDraftInput,
    ) -> ModelProviderResult[ResearchFrameworkDraft]: ...

    def audit_framework(
        self,
        *,
        framework: FrameworkVersionSnapshot,
    ) -> ModelProviderResult[FrameworkAuditDraft]: ...


JsonObject = dict[str, object]


@dataclass(frozen=True, slots=True)
class ModelInvocationRecord:
    trace_id: UUID
    request_id: UUID
    task_id: UUID
    contract_version: str
    capability: ModelCapabilityName
    provider: str
    model_version: str
    capability_tier: str
    demonstration: bool
    scenario: ModelScenario
    input_evidence: JsonObject
    output: JsonObject | None
    knowledge_release_id: str | None
    degraded: bool
    degradation_reason: str | None
    error_code: str | None
    started_at: datetime
    completed_at: datetime


class ModelInvocationRecorder(Protocol):
    def record(self, invocation: ModelInvocationRecord) -> None: ...


class ModelInvocationError(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        trace_id: UUID,
        request_id: UUID,
        provider: str,
    ) -> None:
        self.code = code
        self.trace_id = trace_id
        self.request_id = request_id
        self.provider = provider
        self.recoverable = True
        super().__init__(message)
