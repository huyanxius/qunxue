from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from qunxue_api.modules.theory_matching import ConfirmedTheoryPlanSnapshot


class AuditOverallStatus(StrEnum):
    PASS = "pass"
    REVISE = "revise"
    INSUFFICIENT = "insufficient"


class AuditResolutionAction(StrEnum):
    HANDLED = "handled"
    OVERRIDDEN = "overridden"
    ACCEPT = "handled"
    OVERRIDE = "overridden"


class AuditFindingType(StrEnum):
    CONCEPT_ALIGNMENT = "concept_alignment"
    EVIDENCE = "evidence"
    INFERENCE = "inference"
    METHOD = "method"
    ETHICS = "ethics"
    SCOPE = "scope"


class AuditFindingSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


class FrameworkReviewRunStatus(StrEnum):
    REQUESTED = "requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class MethodIntentSnapshot:
    method_kind: str | None
    constraints: tuple[str, ...]
    source: str


@dataclass(frozen=True, slots=True)
class ResearchFrameworkDraftInput:
    """框架生成的完整交接物；生成器不得凭 ID 回查理论或现象正文。"""

    theory_plan: ConfirmedTheoryPlanSnapshot
    original_research_question: str
    confirmed_research_question: str
    question_adjustment_reason: str | None
    research_object: str
    analysis_unit: str | None
    context: str | None
    method_intent: MethodIntentSnapshot


@dataclass(frozen=True, slots=True)
class ConceptMappingDraft:
    candidate_id: UUID
    theory_concept: str
    meaning_in_study: str
    empirical_indicators: tuple[str, ...]
    unresolved_questions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FrameworkEvidenceRequirementDraft:
    requirement_id: str
    related_candidate_ids: tuple[UUID, ...]
    purpose: str
    required_material: str
    supporting_signal: str
    excluding_signal: str
    distinguishing_signal: str | None
    current_gap: str | None


@dataclass(frozen=True, slots=True)
class InferenceLinkDraft:
    from_ref: str
    to_ref: str
    relation: str
    rationale: str
    unresolved: bool


@dataclass(frozen=True, slots=True)
class MethodPlanDraft:
    method_kind: str
    rationale: str
    material_plan: tuple[str, ...]
    analysis_plan: tuple[str, ...]
    integration_points: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResearchFrameworkDraft:
    """模型或规则产出的草稿；确认权仍属于框架工作流。"""

    concept_mappings: tuple[ConceptMappingDraft, ...]
    evidence_requirements: tuple[FrameworkEvidenceRequirementDraft, ...]
    inference_links: tuple[InferenceLinkDraft, ...]
    alternative_explanations: tuple[str, ...]
    method_plan: MethodPlanDraft | None
    scope_and_limitations: tuple[str, ...]
    unresolved_items: tuple[str, ...]
    next_actions: tuple[str, ...]
    ethical_boundaries: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FrameworkVersionSnapshot:
    framework_id: UUID
    task_id: UUID
    version: int
    input: ResearchFrameworkDraftInput
    draft: ResearchFrameworkDraft
    revision_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class AuditFindingDraft:
    """模型输出不分配 finding ID；该 ID 由框架模块保存时生成。"""

    summary: str
    reason: str
    impact: str
    recommendation: str
    blocking: bool
    finding_type: AuditFindingType = AuditFindingType.SCOPE
    severity: AuditFindingSeverity = AuditFindingSeverity.WARNING


@dataclass(frozen=True, slots=True)
class FrameworkAuditDraft:
    overall_status: AuditOverallStatus
    findings: tuple[AuditFindingDraft, ...]


@dataclass(frozen=True, slots=True)
class AuditFindingSnapshot:
    finding_id: UUID
    summary: str
    reason: str
    impact: str
    recommendation: str
    blocking: bool
    finding_type: AuditFindingType = AuditFindingType.SCOPE
    severity: AuditFindingSeverity = AuditFindingSeverity.WARNING


@dataclass(frozen=True, slots=True)
class FrameworkAuditSnapshot:
    audit_id: UUID
    framework_id: UUID
    framework_version: int
    overall_status: AuditOverallStatus
    findings: tuple[AuditFindingSnapshot, ...]


@dataclass(frozen=True, slots=True)
class FrameworkReviewRunSnapshot:
    review_run_id: UUID
    framework_id: UUID
    framework_version: int
    trace_id: UUID
    idempotency_key: str
    version: int
    status: FrameworkReviewRunStatus
    audit: FrameworkAuditSnapshot | None
    revision_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class AuditResolution:
    finding_id: UUID
    action: AuditResolutionAction
    reason: str


@dataclass(frozen=True, slots=True)
class ConfirmedFrameworkSnapshot:
    framework: FrameworkVersionSnapshot
    audit: FrameworkAuditSnapshot
    resolutions: tuple[AuditResolution, ...]
    confirmed_at: datetime


class ResearchFrameworkDrafter(Protocol):
    """草拟能力只读取完整输入快照，且不能确认自己的输出。"""

    def draft(
        self,
        *,
        input: ResearchFrameworkDraftInput,
    ) -> ResearchFrameworkDraft: ...


class ResearchFrameworkAuditor(Protocol):
    """专业审校看到完整框架，但无权替用户处理或确认发现。"""

    def audit(
        self,
        *,
        framework: FrameworkVersionSnapshot,
    ) -> FrameworkAuditDraft: ...


class ResearchFrameworkWorkflow(Protocol):
    def create_draft(
        self,
        *,
        input: ResearchFrameworkDraftInput,
    ) -> FrameworkVersionSnapshot: ...

    def get(self, framework_id: UUID) -> FrameworkVersionSnapshot: ...

    def revise(
        self,
        *,
        framework_id: UUID,
        expected_version: int,
        audit_id: UUID,
        revised_draft: ResearchFrameworkDraft,
        resolutions: tuple[AuditResolution, ...],
        revision_reason: str,
    ) -> FrameworkVersionSnapshot:
        """Save a new version; a REVISE result cannot be confirmed in place."""
        ...

    def start_review(
        self,
        *,
        framework_id: UUID,
        expected_version: int,
    ) -> FrameworkReviewRunSnapshot: ...

    def get_review_run(
        self,
        review_run_id: UUID,
    ) -> FrameworkReviewRunSnapshot: ...

    def get_audit(self, audit_id: UUID) -> FrameworkAuditSnapshot: ...

    def confirm(
        self,
        *,
        framework_id: UUID,
        expected_version: int,
        audit_id: UUID,
        resolutions: tuple[AuditResolution, ...],
    ) -> ConfirmedFrameworkSnapshot: ...
