from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from qunxue_api.api.contracts.research_method import MethodPlanResponse
from qunxue_api.modules.research_framework import (
    ResearchDocumentEvidenceSourceKind,
    ResearchDocumentProposalKind,
    ResearchDocumentProposalStatus,
    ResearchDocumentSectionStatus,
    ResearchDocumentStatus,
)


class ResearchDocumentEvidenceRefContract(BaseModel):
    evidence_ref_id: str = Field(min_length=1, max_length=256)
    source_id: str = Field(min_length=1, max_length=256)
    knowledge_release_id: str | None = Field(default=None, min_length=1, max_length=128)
    source_kind: ResearchDocumentEvidenceSourceKind = (
        ResearchDocumentEvidenceSourceKind.PUBLIC_KNOWLEDGE
    )
    annotation_id: UUID | None = None
    material_id: UUID | None = None
    parse_id: UUID | None = None
    segment_id: str | None = Field(default=None, min_length=1, max_length=256)
    locator: dict[str, object] | None = None


class ResearchAnalysisHandoffContract(BaseModel):
    schema_version: Literal["research-analysis-v1"]
    task_id: UUID
    content_hash: str
    annotations: list[dict[str, object]]
    codes: list[dict[str, object]]
    memos: list[dict[str, object]]
    comparisons: list[dict[str, object]]
    unavailable_annotation_ids: list[UUID]


class ResearchDocumentSectionContract(BaseModel):
    section_id: str = Field(min_length=1, max_length=128)
    key: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1, max_length=100_000)
    status: ResearchDocumentSectionStatus
    evidence_refs: list[ResearchDocumentEvidenceRefContract] = Field(default_factory=list)


class CreateResearchDocumentRequest(BaseModel):
    theory_plan_id: UUID
    title: str = Field(min_length=1, max_length=512)
    sections: list[ResearchDocumentSectionContract] = Field(min_length=1, max_length=32)


class UpdateResearchDocumentRequest(BaseModel):
    expected_version: int = Field(ge=1)
    sections: list[ResearchDocumentSectionContract] = Field(min_length=1, max_length=32)
    change_summary: str = Field(min_length=1, max_length=2_000)
    source: Literal["user_edit"]


class RestoreResearchDocumentRequest(BaseModel):
    source_version: int = Field(ge=1)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2_000)


class ConfirmResearchDocumentRequest(BaseModel):
    expected_version: int = Field(ge=1)


class AcceptResearchDocumentProposalRequest(BaseModel):
    expected_document_version: int | None = Field(default=None, ge=1)


class RejectResearchDocumentProposalRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2_000)


class ResearchDocumentResponse(BaseModel):
    document_id: UUID
    task_id: UUID
    theory_plan_id: UUID
    knowledge_release_id: str
    revision_id: UUID
    version: int
    title: str
    sections: list[ResearchDocumentSectionContract]
    status: ResearchDocumentStatus
    change_summary: str
    actor: str
    restored_from_version: int | None
    created_at: datetime
    confirmed_at: datetime | None
    research_analysis: ResearchAnalysisHandoffContract | None


class ResearchDocumentVersionListResponse(BaseModel):
    document_id: UUID
    items: list[ResearchDocumentResponse]


class ResearchDocumentListResponse(BaseModel):
    task_id: UUID
    items: list[ResearchDocumentResponse]


class ResearchDocumentProposalResponse(BaseModel):
    proposal_id: UUID
    kind: ResearchDocumentProposalKind
    status: ResearchDocumentProposalStatus
    user_id: UUID
    conversation_id: UUID
    agent_run_id: UUID
    model_provider: str | None
    model_name: str | None
    task_id: UUID
    theory_plan_id: UUID
    knowledge_release_id: str
    title: str
    proposed_sections: list[ResearchDocumentSectionContract]
    rationale: str
    document_id: UUID | None
    base_document_version: int | None
    target_section_id: str | None
    decision_reason: str | None
    result_document_id: UUID | None
    result_document_version: int | None
    requires_user_approval: bool
    created_at: datetime
    decided_at: datetime | None
    research_analysis: ResearchAnalysisHandoffContract | None


class ResearchDocumentProposalAcceptanceResponse(BaseModel):
    proposal: ResearchDocumentProposalResponse
    document: ResearchDocumentResponse


class ResearchDocumentProposalListResponse(BaseModel):
    document_id: UUID
    items: list[ResearchDocumentProposalResponse]


class ResearchTaskDocumentProposalListResponse(BaseModel):
    task_id: UUID
    items: list[ResearchDocumentProposalResponse]


class ResearchDocumentCompletionCheckResponse(BaseModel):
    code: str
    label: str
    passed: bool
    detail: str


class ResearchDocumentCompletionGateResponse(BaseModel):
    document_id: UUID
    version: int
    ready: bool
    pending_proposal_count: int
    blockers: list[str]
    checks: list[ResearchDocumentCompletionCheckResponse]


class ResearchDocumentExportManifest(BaseModel):
    """Versioned, machine-readable audit package for one formal M5 delivery."""

    schema_version: Literal["research-delivery-v2"]
    phenomenon: dict[str, object]
    knowledge_release: dict[str, object]
    model: dict[str, object] | None
    theory_candidates: list[dict[str, object]]
    theory_decisions: list[dict[str, object]]
    theory_assignments: list[dict[str, object]]
    theory_relations: list[dict[str, object]]
    evidence: list[dict[str, object]]
    research_analysis: ResearchAnalysisHandoffContract | None
    method_plan: MethodPlanResponse | None
    agent_proposals: list[dict[str, object]]
    document_versions: list[dict[str, object]]
    formal_document: dict[str, object]


class ResearchDocumentExportResponse(BaseModel):
    document_id: UUID
    task_id: UUID
    theory_plan_id: UUID
    knowledge_release_id: str
    version: int
    filename: str
    media_type: Literal["text/markdown"]
    markdown: str
    manifest: ResearchDocumentExportManifest
