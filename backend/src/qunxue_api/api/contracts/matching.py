from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from qunxue_api.api.contracts.common import ModelMetadata
from qunxue_api.modules.knowledge_catalog import SourceVerificationStatus
from qunxue_api.modules.theory_matching import (
    CandidateContentStatus,
    CandidateJudgementRunStatus,
    CandidateOrigin,
    MatchCompletionBasis,
    MatchRunStatus,
    TheoryDecisionAction,
    TheoryJudgementVerdict,
)


class MatchRunAction(StrEnum):
    RETRY_CANDIDATE = "retry_candidate"
    ACKNOWLEDGE_PARTIAL_COMPLETION = "acknowledge_partial_completion"
    CREATE_DECISION = "create_decision"
    REFRESH = "refresh"


class TheoryCandidateAction(StrEnum):
    RETRY = "retry"
    CREATE_DECISION = "create_decision"


class TheoryDecisionSetAction(StrEnum):
    CONFIRM_THEORY_PLAN = "confirm_theory_plan"
    CREATE_FRAMEWORK = "create_framework"


class TheoryPlanAction(StrEnum):
    CREATE_FRAMEWORK = "create_framework"


class EvidenceReferenceResponse(BaseModel):
    evidence_ref_id: str
    claim: str
    source_id: str | None
    verification_status: SourceVerificationStatus
    use_boundary: str


class RelatedTheoryResponse(BaseModel):
    theory_id: str
    title: str
    relation_explanation: str


class TheoryCandidateResponse(BaseModel):
    candidate_id: UUID
    version: int
    allowed_actions: list[TheoryCandidateAction]
    judgement_run_status: CandidateJudgementRunStatus
    knowledge_release_id: str
    knowledge_id: str | None
    theory_id: str | None
    seed_theory_id: str | None
    origin: CandidateOrigin
    content_status: CandidateContentStatus
    title: str
    problem_focus: str
    core_claims: list[str]
    analysis_levels: list[str]
    prerequisites: list[str]
    applicability_judgement: TheoryJudgementVerdict
    applicability_rationale: str
    supporting_evidence: list[EvidenceReferenceResponse]
    conflicting_evidence: list[EvidenceReferenceResponse]
    missing_evidence: list[str]
    requested_material: list[str]
    limitations: list[str]
    misuse_boundaries: list[str]
    competing_theories: list[RelatedTheoryResponse]
    complementary_theories: list[RelatedTheoryResponse]
    source_ids: list[str]
    formal_adoption_eligible: bool
    adoption_blockers: list[str]
    model: ModelMetadata


class MatchCandidatePageResponse(BaseModel):
    match_run_id: UUID
    version: int
    allowed_actions: list[MatchRunAction]
    knowledge_release_id: str
    candidates: list[TheoryCandidateResponse]
    stable_order: list[UUID]
    next_cursor: str | None


class MatchRunResponse(BaseModel):
    match_run_id: UUID
    task_id: UUID
    version: int
    status: MatchRunStatus
    allowed_actions: list[MatchRunAction]
    completion_basis: MatchCompletionBasis
    partial_completion_acknowledged: bool
    total_candidate_count: int
    completed_candidate_count: int
    failed_candidate_count: int
    phenomenon_query_id: UUID
    phenomenon_version: int
    knowledge_release_id: str
    candidate_page: MatchCandidatePageResponse
    model: ModelMetadata


class CreateMatchRunRequest(BaseModel):
    expected_task_version: int = Field(ge=1)
    phenomenon_query_id: UUID
    phenomenon_version: int = Field(ge=1)
    knowledge_release_id: str | None = None


class RetryMatchCandidateRequest(BaseModel):
    expected_match_run_version: int = Field(ge=1)
    expected_candidate_version: int = Field(ge=1)


class AcknowledgePartialMatchRequest(BaseModel):
    expected_version: int = Field(ge=1)
    acknowledged_candidate_ids: list[UUID]
    failed_candidate_ids: list[UUID]
    reason: str = Field(min_length=1, max_length=2_000)


class TheoryDecisionInput(BaseModel):
    candidate_id: UUID
    candidate_version: int = Field(ge=1)
    action: TheoryDecisionAction
    reason: str = Field(min_length=1, max_length=4_000)
    related_source_ids: list[str] = Field(default_factory=list)
    revised_applicability: str | None = None


class TheoryUseAssignmentInput(BaseModel):
    candidate_id: UUID
    role_code: str
    responsibility: str


class TheoryRelationInput(BaseModel):
    candidate_ids: list[UUID] = Field(min_length=2)
    relation_kind: str
    explanation: str
    premise_compatibility: str
    supporting_evidence: list[str]
    excluding_evidence: list[str]
    distinguishing_evidence: list[str]


class CreateTheoryDecisionsRequest(BaseModel):
    expected_match_run_version: int = Field(ge=1)
    completion_basis: MatchCompletionBasis
    decisions: list[TheoryDecisionInput] = Field(min_length=1)
    use_assignments: list[TheoryUseAssignmentInput]
    relations: list[TheoryRelationInput]


class TheoryDecisionRecordResponse(BaseModel):
    decision_id: UUID
    candidate_id: UUID
    candidate_version: int
    action: TheoryDecisionAction
    reason: str
    related_source_ids: list[str]
    revised_applicability: str | None
    recorded_at: datetime


class TheoryDecisionSetResponse(BaseModel):
    decision_set_id: UUID
    match_run_id: UUID
    version: int
    allowed_actions: list[TheoryDecisionSetAction]
    knowledge_release_id: str
    completion_basis: MatchCompletionBasis
    decisions: list[TheoryDecisionRecordResponse]
    use_assignments: list[TheoryUseAssignmentInput]
    relations: list[TheoryRelationInput]


class TheoryDecisionPageResponse(BaseModel):
    match_run_id: UUID
    version: int
    allowed_actions: list[TheoryDecisionSetAction]
    knowledge_release_id: str
    decision_sets: list[TheoryDecisionSetResponse]
    next_cursor: str | None


class ConfirmTheoryPlanRequest(BaseModel):
    expected_decision_set_version: int = Field(ge=1)


class ConfirmedTheoryPlanResponse(BaseModel):
    theory_plan_id: UUID
    task_id: UUID
    match_run_id: UUID
    decision_set_id: UUID
    version: int
    allowed_actions: list[TheoryPlanAction]
    phenomenon_query_id: UUID
    phenomenon_version: int
    knowledge_release_id: str
    adopted_candidate_ids: list[UUID]
    confirmed_at: datetime
