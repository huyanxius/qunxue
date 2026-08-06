from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from qunxue_api.api.contracts.common import ModelMetadata
from qunxue_api.modules.research_framework import (
    AuditFindingSeverity,
    AuditFindingType,
    AuditOverallStatus,
    FrameworkReviewRunStatus,
)
from qunxue_api.modules.research_framework import (
    AuditResolutionAction as DomainAuditResolutionAction,
)


class FrameworkStatus(StrEnum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    REVISION_REQUIRED = "revision_required"
    READY_TO_CONFIRM = "ready_to_confirm"
    CONFIRMED = "confirmed"


class FrameworkAction(StrEnum):
    UPDATE = "update"
    START_REVIEW = "start_review"
    SUBMIT_AUDIT_RESOLUTIONS = "submit_audit_resolutions"
    CONFIRM = "confirm"
    EXPORT = "export"


class FrameworkReviewAction(StrEnum):
    REFRESH = "refresh"
    SUBMIT_AUDIT_RESOLUTIONS = "submit_audit_resolutions"
    REVISE_FRAMEWORK = "revise_framework"
    CONFIRM_FRAMEWORK = "confirm_framework"


class AuditResolutionAction(StrEnum):
    HANDLED = DomainAuditResolutionAction.HANDLED.value
    OVERRIDDEN = DomainAuditResolutionAction.OVERRIDDEN.value


class MethodIntentContract(BaseModel):
    method_kind: str | None
    constraints: list[str]
    source: str


class CreateFrameworkRequest(BaseModel):
    expected_task_version: int = Field(ge=1)
    theory_plan_id: UUID
    theory_plan_version: int = Field(ge=1)
    original_research_question: str
    confirmed_research_question: str
    question_adjustment_reason: str | None = None
    research_object: str
    analysis_unit: str | None = None
    context: str | None = None
    method_intent: MethodIntentContract


class ConceptMappingContract(BaseModel):
    candidate_id: UUID
    theory_concept: str
    meaning_in_study: str
    empirical_indicators: list[str]
    unresolved_questions: list[str]


class FrameworkEvidenceRequirementContract(BaseModel):
    requirement_id: str
    related_candidate_ids: list[UUID]
    purpose: str
    required_material: str
    supporting_signal: str
    excluding_signal: str
    distinguishing_signal: str | None
    current_gap: str | None


class InferenceLinkContract(BaseModel):
    from_ref: str
    to_ref: str
    relation: str
    rationale: str
    unresolved: bool


class MethodPlanContract(BaseModel):
    method_kind: str
    rationale: str
    material_plan: list[str]
    analysis_plan: list[str]
    integration_points: list[str]


class FrameworkDraftContract(BaseModel):
    concept_mappings: list[ConceptMappingContract]
    evidence_requirements: list[FrameworkEvidenceRequirementContract]
    inference_links: list[InferenceLinkContract]
    alternative_explanations: list[str]
    method_plan: MethodPlanContract | None
    scope_and_limitations: list[str]
    ethical_boundaries: list[str]
    unresolved_items: list[str]
    next_actions: list[str]


class FrameworkInputResponse(BaseModel):
    theory_plan_id: UUID
    theory_plan_version: int
    original_research_question: str
    confirmed_research_question: str
    question_adjustment_reason: str | None
    research_object: str
    analysis_unit: str | None
    context: str | None
    method_intent: MethodIntentContract


class FrameworkResponse(BaseModel):
    framework_id: UUID
    task_id: UUID
    revision_id: UUID
    version: int
    status: FrameworkStatus
    allowed_actions: list[FrameworkAction]
    knowledge_release_id: str
    input: FrameworkInputResponse
    draft: FrameworkDraftContract
    unresolved_blocking_audit: bool
    model: ModelMetadata | None


class UpdateFrameworkRequest(BaseModel):
    expected_revision_id: UUID
    expected_version: int = Field(ge=1)
    draft: FrameworkDraftContract
    revision_reason: str = Field(min_length=1, max_length=4_000)


class StartFrameworkReviewRequest(BaseModel):
    expected_revision_id: UUID
    expected_version: int = Field(ge=1)


class AuditFindingResponse(BaseModel):
    finding_id: UUID
    finding_type: AuditFindingType
    severity: AuditFindingSeverity
    summary: str
    reason: str
    impact: str
    recommendation: str
    blocking: bool


class FrameworkAuditResponse(BaseModel):
    audit_id: UUID
    framework_id: UUID
    revision_id: UUID
    framework_version: int
    overall_status: AuditOverallStatus
    findings: list[AuditFindingResponse]
    unresolved_blocking: bool
    contract_version: str


class FrameworkReviewResponse(BaseModel):
    review_run_id: UUID
    framework_id: UUID
    revision_id: UUID
    version: int
    status: FrameworkReviewRunStatus
    allowed_actions: list[FrameworkReviewAction]
    knowledge_release_id: str
    audit: FrameworkAuditResponse | None
    model: ModelMetadata
    contract_version: str


class AuditResolutionInput(BaseModel):
    finding_id: UUID
    action: AuditResolutionAction
    reason: str = Field(min_length=1, max_length=4_000)


class SubmitAuditResolutionsRequest(BaseModel):
    expected_revision_id: UUID
    expected_version: int = Field(ge=1)
    audit_id: UUID
    resolutions: list[AuditResolutionInput] = Field(min_length=1)


class AuditResolutionSetResponse(BaseModel):
    resolution_set_id: UUID
    framework_id: UUID
    revision_id: UUID
    version: int
    allowed_actions: list[FrameworkAction]
    knowledge_release_id: str
    resolutions: list[AuditResolutionInput]
    unresolved_blocking: bool


class ConfirmFrameworkRequest(BaseModel):
    expected_revision_id: UUID
    expected_version: int = Field(ge=1)
    audit_id: UUID
    resolution_set_id: UUID | None = None


class ConfirmedFrameworkResponse(BaseModel):
    framework_id: UUID
    task_id: UUID
    revision_id: UUID
    version: int
    status: Literal["confirmed"]
    allowed_actions: list[FrameworkAction]
    knowledge_release_id: str
    draft: FrameworkDraftContract
    audit: FrameworkAuditResponse
    resolutions: list[AuditResolutionInput]
    confirmed_at: datetime
    contract_version: str


class FormalFrameworkExportResponse(BaseModel):
    framework_id: UUID
    task_id: UUID
    revision_id: UUID
    version: int
    allowed_actions: list[FrameworkAction]
    framework_status: Literal["confirmed"]
    knowledge_release_id: str
    filename: str
    media_type: Literal["text/markdown"]
    markdown: str
    confirmed_at: datetime
    contract_version: str
