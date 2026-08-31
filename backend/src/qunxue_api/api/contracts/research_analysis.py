from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from qunxue_api.api.contracts.research_materials import ResearchMaterialLocatorResponse
from qunxue_api.modules.research_analysis import (
    AnalysisAnnotation,
    AnalysisAnnotationKind,
    AnalysisCaseProfile,
    AnalysisCode,
    AnalysisCodeStatus,
    AnalysisMemo,
    AnalysisMemoKind,
    AnalysisMemoLink,
    AnalysisRecordStatus,
    AnalysisTheme,
    CaseComparison,
    CaseThemeMatrixCell,
    CodebookEntry,
    CodebookLifecycle,
    ComparisonFinding,
    ComparisonFindingKind,
    MatrixSubjectKind,
    MemoTargetKind,
    MethodPresetSelection,
    NextResearchStep,
    QualitativeMethod,
    QualitativeMethodPreset,
    QualitativeWorkspaceSnapshot,
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
    workspace: "QualitativeWorkspaceSnapshotResponse"
    method_presets: list["QualitativeMethodPresetResponse"]


class ConfigureCodebookEntryRequest(BaseModel):
    expected_version: int | None = Field(default=None, ge=1)
    inclusion_rules: list[str] = Field(min_length=1, max_length=100)
    exclusion_rules: list[str] = Field(min_length=1, max_length=100)
    parent_code_id: UUID | None = None
    positive_example_annotation_ids: list[UUID] = Field(min_length=1, max_length=100)
    negative_example_annotation_ids: list[UUID] = Field(min_length=1, max_length=100)


class TransitionCodebookEntryRequest(BaseModel):
    expected_version: int = Field(ge=1)
    lifecycle: CodebookLifecycle
    related_code_ids: list[UUID] = Field(default_factory=list, max_length=100)
    reason: str = Field(min_length=1, max_length=20_000)


class CodebookEntryResponse(BaseModel):
    code_id: UUID
    inclusion_rules: list[str]
    exclusion_rules: list[str]
    parent_code_id: UUID | None
    positive_example_annotation_ids: list[UUID]
    negative_example_annotation_ids: list[UUID]
    lifecycle: CodebookLifecycle
    related_code_ids: list[UUID]
    version: int
    updated_at: datetime
    revision_reason: str

    @classmethod
    def from_domain(cls, value: CodebookEntry) -> "CodebookEntryResponse":
        return cls(
            code_id=value.code_id,
            inclusion_rules=list(value.inclusion_rules),
            exclusion_rules=list(value.exclusion_rules),
            parent_code_id=value.parent_code_id,
            positive_example_annotation_ids=list(value.positive_example_annotation_ids),
            negative_example_annotation_ids=list(value.negative_example_annotation_ids),
            lifecycle=value.lifecycle,
            related_code_ids=list(value.related_code_ids),
            version=value.version,
            updated_at=value.updated_at,
            revision_reason=value.revision_reason,
        )


class CreateAnalysisThemeRequest(BaseModel):
    label: str = Field(min_length=1, max_length=512)
    central_concept: str = Field(min_length=1, max_length=20_000)
    code_ids: list[UUID] = Field(min_length=1, max_length=200)
    annotation_ids: list[UUID] = Field(min_length=1, max_length=500)


class AnalysisThemeResponse(BaseModel):
    theme_id: UUID
    label: str
    central_concept: str
    code_ids: list[UUID]
    annotation_ids: list[UUID]
    source: str
    status: AnalysisRecordStatus
    version: int
    created_at: datetime
    decided_at: datetime | None
    decision_reason: str | None

    @classmethod
    def from_domain(cls, value: AnalysisTheme) -> "AnalysisThemeResponse":
        return cls(
            theme_id=value.theme_id,
            label=value.label,
            central_concept=value.central_concept,
            code_ids=list(value.code_ids),
            annotation_ids=list(value.annotation_ids),
            source=value.source,
            status=value.status,
            version=value.version,
            created_at=value.created_at,
            decided_at=value.decided_at,
            decision_reason=value.decision_reason,
        )


class CreateAnalysisMemoLinkRequest(BaseModel):
    memo_id: UUID
    target_kind: MemoTargetKind
    target_ref: str = Field(min_length=1, max_length=512)
    annotation_ids: list[UUID] = Field(min_length=1, max_length=200)


class AnalysisMemoLinkResponse(BaseModel):
    link_id: UUID
    memo_id: UUID
    target_kind: MemoTargetKind
    target_ref: str
    annotation_ids: list[UUID]
    created_at: datetime

    @classmethod
    def from_domain(cls, value: AnalysisMemoLink) -> "AnalysisMemoLinkResponse":
        return cls(
            link_id=value.link_id,
            memo_id=value.memo_id,
            target_kind=value.target_kind,
            target_ref=value.target_ref,
            annotation_ids=list(value.annotation_ids),
            created_at=value.created_at,
        )


class AnalysisCaseAttributeContract(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=512)


class SaveAnalysisCaseProfileRequest(BaseModel):
    expected_version: int | None = Field(default=None, ge=1)
    case_ref: str = Field(min_length=1, max_length=512)
    display_label: str = Field(min_length=1, max_length=512)
    attributes: list[AnalysisCaseAttributeContract] = Field(default_factory=list, max_length=100)
    summary: str = Field(min_length=1, max_length=100_000)
    annotation_ids: list[UUID] = Field(min_length=1, max_length=500)
    memo_ids: list[UUID] = Field(default_factory=list, max_length=200)


class AnalysisCaseProfileResponse(BaseModel):
    profile_id: UUID
    case_ref: str
    display_label: str
    attributes: list[AnalysisCaseAttributeContract]
    summary: str
    annotation_ids: list[UUID]
    memo_ids: list[UUID]
    version: int
    updated_at: datetime

    @classmethod
    def from_domain(cls, value: AnalysisCaseProfile) -> "AnalysisCaseProfileResponse":
        return cls(
            profile_id=value.profile_id,
            case_ref=value.case_ref,
            display_label=value.display_label,
            attributes=[
                AnalysisCaseAttributeContract(name=name, value=attribute_value)
                for name, attribute_value in value.attributes
            ],
            summary=value.summary,
            annotation_ids=list(value.annotation_ids),
            memo_ids=list(value.memo_ids),
            version=value.version,
            updated_at=value.updated_at,
        )


class SaveCaseThemeMatrixCellRequest(BaseModel):
    expected_version: int | None = Field(default=None, ge=1)
    case_profile_id: UUID
    subject_kind: MatrixSubjectKind
    subject_id: UUID
    summary: str = Field(min_length=1, max_length=100_000)
    annotation_ids: list[UUID] = Field(min_length=1, max_length=500)
    memo_ids: list[UUID] = Field(default_factory=list, max_length=200)
    finding_kinds: list[ComparisonFindingKind] = Field(default_factory=list, max_length=10)


class CaseThemeMatrixCellResponse(BaseModel):
    cell_id: UUID
    case_profile_id: UUID
    subject_kind: MatrixSubjectKind
    subject_id: UUID
    summary: str
    annotation_ids: list[UUID]
    memo_ids: list[UUID]
    finding_kinds: list[ComparisonFindingKind]
    version: int
    updated_at: datetime

    @classmethod
    def from_domain(cls, value: CaseThemeMatrixCell) -> "CaseThemeMatrixCellResponse":
        return cls(
            cell_id=value.cell_id,
            case_profile_id=value.case_profile_id,
            subject_kind=value.subject_kind,
            subject_id=value.subject_id,
            summary=value.summary,
            annotation_ids=list(value.annotation_ids),
            memo_ids=list(value.memo_ids),
            finding_kinds=list(value.finding_kinds),
            version=value.version,
            updated_at=value.updated_at,
        )


class SetQualitativeMethodRequest(BaseModel):
    method: QualitativeMethod
    expected_version: int | None = Field(default=None, ge=1)


class MethodPresetSelectionResponse(BaseModel):
    method: QualitativeMethod
    version: int
    updated_at: datetime

    @classmethod
    def from_domain(cls, value: MethodPresetSelection) -> "MethodPresetSelectionResponse":
        return cls(method=value.method, version=value.version, updated_at=value.updated_at)


class QualitativeMethodPresetResponse(BaseModel):
    method: QualitativeMethod
    label: str
    primary_view: str
    matrix_axes: list[str]
    prompts: str
    guardrails: str

    @classmethod
    def from_domain(cls, value: QualitativeMethodPreset) -> "QualitativeMethodPresetResponse":
        return cls(
            method=value.method,
            label=value.label,
            primary_view=value.primary_view,
            matrix_axes=list(value.matrix_axes),
            prompts=value.prompts,
            guardrails=value.guardrails,
        )


class QualitativeWorkspaceSnapshotResponse(BaseModel):
    schema_version: str
    content_hash: str
    method_preset: MethodPresetSelectionResponse
    codebook_entries: list[CodebookEntryResponse]
    memo_links: list[AnalysisMemoLinkResponse]
    case_profiles: list[AnalysisCaseProfileResponse]
    formal_themes: list[AnalysisThemeResponse]
    candidate_themes: list[AnalysisThemeResponse]
    matrix_cells: list[CaseThemeMatrixCellResponse]

    @classmethod
    def from_domain(
        cls, value: QualitativeWorkspaceSnapshot
    ) -> "QualitativeWorkspaceSnapshotResponse":
        return cls(
            schema_version=value.schema_version,
            content_hash=value.content_hash,
            method_preset=MethodPresetSelectionResponse.from_domain(value.method_preset),
            codebook_entries=[
                CodebookEntryResponse.from_domain(item) for item in value.codebook_entries
            ],
            memo_links=[AnalysisMemoLinkResponse.from_domain(item) for item in value.memo_links],
            case_profiles=[
                AnalysisCaseProfileResponse.from_domain(item) for item in value.case_profiles
            ],
            formal_themes=[AnalysisThemeResponse.from_domain(item) for item in value.formal_themes],
            candidate_themes=[
                AnalysisThemeResponse.from_domain(item) for item in value.candidate_themes
            ],
            matrix_cells=[
                CaseThemeMatrixCellResponse.from_domain(item) for item in value.matrix_cells
            ],
        )
