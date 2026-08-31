from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from qunxue_api.modules.research_method import (
    MethodKind,
    MethodPlanReview,
    MethodPlanSnapshot,
    MethodPlanStatus,
)


class MethodPlanSectionContract(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1, max_length=100_000)
    source: str = Field(pattern="^(system|user)$")


class MethodPlanReviewContract(BaseModel):
    review_id: UUID
    note: str
    blocking: bool
    created_at: datetime
    resolved_at: datetime | None = None


class MethodPlanEvidenceRefContract(BaseModel):
    evidence_ref_id: str
    source_id: str
    source_kind: str
    knowledge_release_id: str | None = None
    annotation_id: str | None = None
    material_id: str | None = None
    parse_id: str | None = None
    segment_id: str | None = None
    locator: str | None = None


class MethodPlanContextItemContract(BaseModel):
    key: str
    title: str
    content: str
    evidence_refs: list[MethodPlanEvidenceRefContract]


class CreateMethodPlanRequest(BaseModel):
    framework_id: UUID
    theory_plan_id: UUID
    method_kind: MethodKind


class UpdateMethodPlanRequest(BaseModel):
    expected_version: int = Field(ge=1)
    method_kind: MethodKind
    rationale: str = Field(min_length=1, max_length=20_000)
    change_summary: str = Field(min_length=1, max_length=2_000)
    sections: list[MethodPlanSectionContract] = Field(min_length=1, max_length=32)


class ReviewMethodPlanRequest(BaseModel):
    expected_version: int = Field(ge=1)
    note: str = Field(min_length=1, max_length=20_000)
    blocking: bool = False


class ResolveMethodPlanReviewRequest(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2_000)


class ConfirmMethodPlanRequest(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2_000)


class RestoreMethodPlanRequest(BaseModel):
    source_version: int = Field(ge=1)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2_000)


class MethodPlanResponse(BaseModel):
    plan_id: UUID
    task_id: UUID
    framework_id: UUID
    framework_version: int
    theory_plan_id: UUID
    theory_plan_version: int
    method_kind: MethodKind
    decision_source: str
    rationale: str
    research_question: str
    theory_summary: str
    material_constraints: list[str]
    ethical_constraints: list[str]
    theory_concepts: list[str]
    evidence_ref_ids: list[str]
    knowledge_release_id: str | None
    shared_context: list[MethodPlanContextItemContract]
    sections: list[MethodPlanSectionContract]
    reviews: list[MethodPlanReviewContract]
    status: MethodPlanStatus
    version: int
    revision_id: UUID
    change_summary: str
    actor: str
    created_at: datetime
    restored_from_version: int | None
    stale_reason: str | None
    confirmed_at: datetime | None

    @classmethod
    def from_domain(cls, value: MethodPlanSnapshot) -> "MethodPlanResponse":
        return cls(
            plan_id=value.plan_id,
            task_id=value.task_id,
            framework_id=value.framework_id,
            framework_version=value.framework_version,
            theory_plan_id=value.theory_plan_id,
            theory_plan_version=value.theory_plan_version,
            method_kind=value.method_kind,
            decision_source=value.decision_source,
            rationale=value.rationale,
            research_question=value.research_question,
            theory_summary=value.theory_summary,
            material_constraints=list(value.shared_constraints.material_constraints),
            ethical_constraints=list(value.shared_constraints.ethical_constraints),
            theory_concepts=list(value.shared_constraints.theory_concepts),
            evidence_ref_ids=list(value.shared_constraints.evidence_ref_ids),
            knowledge_release_id=value.shared_constraints.knowledge_release_id,
            shared_context=[
                MethodPlanContextItemContract(
                    key=item.key,
                    title=item.title,
                    content=item.content,
                    evidence_refs=[
                        MethodPlanEvidenceRefContract(
                            evidence_ref_id=ref.evidence_ref_id,
                            source_id=ref.source_id,
                            source_kind=ref.source_kind,
                            knowledge_release_id=ref.knowledge_release_id,
                            annotation_id=ref.annotation_id,
                            material_id=ref.material_id,
                            parse_id=ref.parse_id,
                            segment_id=ref.segment_id,
                            locator=ref.locator,
                        )
                        for ref in item.evidence_refs
                    ],
                )
                for item in value.shared_context
            ],
            sections=[
                MethodPlanSectionContract(
                    key=item.key, title=item.title, content=item.content, source=item.source
                )
                for item in value.sections
            ],
            reviews=[MethodPlanReviewContract(**_review_payload(item)) for item in value.reviews],
            status=value.status,
            version=value.version,
            revision_id=value.revision_id,
            change_summary=value.change_summary,
            actor=value.actor,
            created_at=value.created_at,
            restored_from_version=value.restored_from_version,
            stale_reason=value.stale_reason,
            confirmed_at=value.confirmed_at,
        )


class MethodPlanVersionListResponse(BaseModel):
    plan_id: UUID
    items: list[MethodPlanResponse]


def _review_payload(value: MethodPlanReview) -> dict[str, object]:
    return {
        "review_id": value.review_id,
        "note": value.note,
        "blocking": value.blocking,
        "created_at": value.created_at,
        "resolved_at": value.resolved_at,
    }
