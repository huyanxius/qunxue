from enum import StrEnum

from pydantic import BaseModel

from qunxue_api.modules.knowledge_catalog import (
    KnowledgeReleaseLevel,
    KnowledgeReviewStatus,
    SourceVerificationStatus,
)


class KnowledgeUseEligibilityResponse(BaseModel):
    browse_eligible: bool
    rag_eligible: bool
    training_candidate_eligible: bool
    match_eligible: bool
    review_record_ids: list[str]


class KnowledgeReleaseResponse(BaseModel):
    knowledge_release_id: str
    level: KnowledgeReleaseLevel
    content_hash: str


class KnowledgeEntrySummaryResponse(BaseModel):
    knowledge_id: str
    content_version: int
    title: str
    category: str
    dimension: str
    review_status: KnowledgeReviewStatus
    eligibility: KnowledgeUseEligibilityResponse


class KnowledgeEntryPageResponse(BaseModel):
    knowledge_release_id: str
    entries: list[KnowledgeEntrySummaryResponse]
    stable_order: list[str]
    next_cursor: str | None


class SourceRecordResponse(BaseModel):
    source_id: str
    source_type: str
    title: str
    authors_or_institution: list[str]
    year: int | None
    publication: str | None
    locator: str | None
    url: str | None
    verification_status: SourceVerificationStatus
    use_boundary: str


class KnowledgeRelationResponse(BaseModel):
    relation_id: str
    source_knowledge_id: str
    target_knowledge_id: str
    relation_type: str
    direction: str
    description: str
    evidence_source_ids: list[str]
    evidence_grade: str
    content_version: int
    review_status: KnowledgeReviewStatus


class TheoryProfileResponse(BaseModel):
    theory_id: str
    related_knowledge_ids: list[str]
    title: str
    core_propositions: list[str]
    applicable_phenomena: list[str]
    analysis_levels: list[str]
    prerequisites: list[str]
    exclusion_signals: list[str]
    observable_evidence: list[str]
    competing_or_complementary_theory_ids: list[str]
    source_ids: list[str]
    content_version: int
    review_status: KnowledgeReviewStatus
    match_eligible: bool


class KnowledgeEntryDetailResponse(BaseModel):
    knowledge_release_id: str
    knowledge_id: str
    content_version: int
    title: str
    category: str
    dimension: str
    review_status: KnowledgeReviewStatus
    eligibility: KnowledgeUseEligibilityResponse
    aliases: list[str]
    content: str
    sources: list[SourceRecordResponse]
    relations: list[KnowledgeRelationResponse]
    theory_profile: TheoryProfileResponse | None


class BuiltInCaseContentStatus(StrEnum):
    REVIEWED = "reviewed"
    DEMONSTRATION = "demonstration"


class BuiltInCaseResponse(BaseModel):
    case_id: str
    title: str
    summary: str
    phenomenon: str
    research_intent: str | None
    context: str | None
    content_status: BuiltInCaseContentStatus


class BuiltInCasePageResponse(BaseModel):
    knowledge_release_id: str
    cases: list[BuiltInCaseResponse]
    stable_order: list[str]
    next_cursor: str | None
