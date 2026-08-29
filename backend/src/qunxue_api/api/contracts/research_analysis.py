from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from qunxue_api.api.contracts.research_materials import ResearchMaterialLocatorResponse
from qunxue_api.modules.research_analysis import (
    AnalysisAnnotation,
    AnalysisAnnotationKind,
    AnalysisCode,
    AnalysisCodeStatus,
    AnalysisMemo,
    AnalysisMemoKind,
    AnalysisRecordStatus,
    CaseComparison,
    ComparisonFinding,
    ComparisonFindingKind,
    NextResearchStep,
)


class CreateAnalysisAnnotationRequest(BaseModel):
    material_id: UUID
    parse_id: UUID
    segment_id: str = Field(min_length=1, max_length=256)
    quote_start: int = Field(ge=0)
    quote_end: int = Field(gt=0)
    annotation_kind: AnalysisAnnotationKind
    case_label: str | None = Field(default=None, max_length=256)
    observed_at: str | None = Field(default=None, max_length=128)
    note: str = Field(min_length=1, max_length=20_000)
    reflection: str | None = Field(default=None, max_length=20_000)


class AnalysisAnnotationResponse(BaseModel):
    annotation_id: UUID
    task_id: UUID
    material_id: UUID
    parse_id: UUID
    segment_id: str
    segment_content_hash: str
    quote: str | None
    quote_hash: str
    quote_start: int
    quote_end: int
    locator: ResearchMaterialLocatorResponse
    annotation_kind: AnalysisAnnotationKind
    case_label: str | None
    observed_at: str | None
    note: str
    reflection: str | None
    created_at: datetime
    source_available: bool
    unavailable_reason: str | None

    @classmethod
    def from_domain(cls, value: AnalysisAnnotation) -> "AnalysisAnnotationResponse":
        return cls(
            annotation_id=value.annotation_id,
            task_id=value.task_id,
            material_id=value.material_id,
            parse_id=value.parse_id,
            segment_id=value.segment_id,
            segment_content_hash=value.segment_content_hash,
            quote=value.quote if value.source_available else None,
            quote_hash=value.quote_hash,
            quote_start=value.quote_start,
            quote_end=value.quote_end,
            locator=ResearchMaterialLocatorResponse.from_domain(value.locator),
            annotation_kind=value.annotation_kind,
            case_label=value.case_label,
            observed_at=value.observed_at,
            note=value.note,
            reflection=value.reflection,
            created_at=value.created_at,
            source_available=value.source_available,
            unavailable_reason=value.unavailable_reason,
        )


class CreateAnalysisCodeRequest(BaseModel):
    label: str = Field(min_length=1, max_length=256)
    definition: str = Field(min_length=1, max_length=20_000)
    annotation_ids: list[UUID] = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=20_000)


class DecideAnalysisRecordRequest(BaseModel):
    expected_version: int = Field(ge=1)
    decision: AnalysisRecordStatus
    reason: str = Field(min_length=1, max_length=20_000)


class AnalysisCodeResponse(BaseModel):
    code_id: UUID
    task_id: UUID
    label: str
    definition: str
    annotation_ids: list[UUID]
    rationale: str
    source: str
    status: AnalysisCodeStatus
    version: int
    created_at: datetime
    conversation_id: UUID | None
    agent_run_id: UUID | None
    agent_turn_id: UUID | None
    tool_call_id: str | None
    decided_at: datetime | None
    decision_reason: str | None

    @classmethod
    def from_domain(cls, value: AnalysisCode) -> "AnalysisCodeResponse":
        return cls(
            code_id=value.code_id,
            task_id=value.task_id,
            label=value.label,
            definition=value.definition,
            annotation_ids=list(value.annotation_ids),
            rationale=value.rationale,
            source=value.source,
            status=value.status,
            version=value.version,
            created_at=value.created_at,
            conversation_id=value.conversation_id,
            agent_run_id=value.agent_run_id,
            agent_turn_id=value.agent_turn_id,
            tool_call_id=value.tool_call_id,
            decided_at=value.decided_at,
            decision_reason=value.decision_reason,
        )


class CreateAnalysisMemoRequest(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    content: str = Field(min_length=1, max_length=100_000)
    memo_kind: AnalysisMemoKind
    annotation_ids: list[UUID] = Field(default_factory=list, max_length=200)
    code_ids: list[UUID] = Field(default_factory=list, max_length=200)


class AnalysisMemoResponse(BaseModel):
    memo_id: UUID
    task_id: UUID
    title: str
    content: str
    memo_kind: AnalysisMemoKind
    annotation_ids: list[UUID]
    code_ids: list[UUID]
    source: str
    status: AnalysisRecordStatus
    version: int
    created_at: datetime
    conversation_id: UUID | None
    agent_run_id: UUID | None
    agent_turn_id: UUID | None
    tool_call_id: str | None
    decided_at: datetime | None
    decision_reason: str | None

    @classmethod
    def from_domain(cls, value: AnalysisMemo) -> "AnalysisMemoResponse":
        return cls(
            memo_id=value.memo_id,
            task_id=value.task_id,
            title=value.title,
            content=value.content,
            memo_kind=value.memo_kind,
            annotation_ids=list(value.annotation_ids),
            code_ids=list(value.code_ids),
            source=value.source,
            status=value.status,
            version=value.version,
            created_at=value.created_at,
            conversation_id=value.conversation_id,
            agent_run_id=value.agent_run_id,
            agent_turn_id=value.agent_turn_id,
            tool_call_id=value.tool_call_id,
            decided_at=value.decided_at,
            decision_reason=value.decision_reason,
        )


class ComparisonFindingContract(BaseModel):
    kind: ComparisonFindingKind
    statement: str = Field(min_length=1, max_length=20_000)
    annotation_ids: list[UUID] = Field(default_factory=list, max_length=200)

    def to_domain(self) -> ComparisonFinding:
        return ComparisonFinding(
            kind=self.kind,
            statement=self.statement,
            annotation_ids=tuple(self.annotation_ids),
        )

    @classmethod
    def from_domain(cls, value: ComparisonFinding) -> "ComparisonFindingContract":
        return cls(
            kind=value.kind,
            statement=value.statement,
            annotation_ids=list(value.annotation_ids),
        )


class NextResearchStepContract(BaseModel):
    kind: str = Field(min_length=1, max_length=32)
    action: str = Field(min_length=1, max_length=20_000)
    priority: str = "medium"

    def to_domain(self) -> NextResearchStep:
        return NextResearchStep(kind=self.kind, action=self.action, priority=self.priority)

    @classmethod
    def from_domain(cls, value: NextResearchStep) -> "NextResearchStepContract":
        return cls(kind=value.kind, action=value.action, priority=value.priority)


class CreateCaseComparisonRequest(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    question: str = Field(min_length=1, max_length=20_000)
    case_labels: list[str] = Field(min_length=2, max_length=100)
    time_labels: list[str] = Field(default_factory=list, max_length=100)
    findings: list[ComparisonFindingContract] = Field(min_length=1, max_length=500)
    competing_explanations: list[str] = Field(default_factory=list, max_length=100)
    evidence_gaps: list[str] = Field(default_factory=list, max_length=100)
    next_steps: list[NextResearchStepContract] = Field(default_factory=list, max_length=100)
    theory_implication: str = Field(min_length=1, max_length=20_000)


class CaseComparisonResponse(BaseModel):
    comparison_id: UUID
    task_id: UUID
    title: str
    question: str
    case_labels: list[str]
    time_labels: list[str]
    findings: list[ComparisonFindingContract]
    competing_explanations: list[str]
    evidence_gaps: list[str]
    next_steps: list[NextResearchStepContract]
    theory_implication: str
    source: str
    status: AnalysisRecordStatus
    version: int
    created_at: datetime
    conversation_id: UUID | None
    agent_run_id: UUID | None
    agent_turn_id: UUID | None
    tool_call_id: str | None
    decided_at: datetime | None
    decision_reason: str | None

    @classmethod
    def from_domain(cls, value: CaseComparison) -> "CaseComparisonResponse":
        return cls(
            comparison_id=value.comparison_id,
            task_id=value.task_id,
            title=value.title,
            question=value.question,
            case_labels=list(value.case_labels),
            time_labels=list(value.time_labels),
            findings=[ComparisonFindingContract.from_domain(item) for item in value.findings],
            competing_explanations=list(value.competing_explanations),
            evidence_gaps=list(value.evidence_gaps),
            next_steps=[NextResearchStepContract.from_domain(item) for item in value.next_steps],
            theory_implication=value.theory_implication,
            source=value.source,
            status=value.status,
            version=value.version,
            created_at=value.created_at,
            conversation_id=value.conversation_id,
            agent_run_id=value.agent_run_id,
            agent_turn_id=value.agent_turn_id,
            tool_call_id=value.tool_call_id,
            decided_at=value.decided_at,
            decision_reason=value.decision_reason,
        )


class ResearchAnalysisSnapshotResponse(BaseModel):
    task_id: UUID
    annotations: list[AnalysisAnnotationResponse]
    codes: list[AnalysisCodeResponse]
    memos: list[AnalysisMemoResponse]
    comparisons: list[CaseComparisonResponse]
