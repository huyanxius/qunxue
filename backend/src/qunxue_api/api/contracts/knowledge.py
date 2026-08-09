from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from qunxue_api.modules.knowledge_catalog import (
    KnowledgeDirectoryNodeType,
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


class KnowledgeDirectoryNodeResponse(BaseModel):
    node_id: str
    node_type: KnowledgeDirectoryNodeType
    title: str


class KnowledgeEntrySummaryResponse(BaseModel):
    knowledge_id: str
    content_version: int
    title: str
    category_id: str
    category: str
    dimension_id: str
    dimension: str
    directory_path: list[KnowledgeDirectoryNodeResponse]
    review_status: KnowledgeReviewStatus
    eligibility: KnowledgeUseEligibilityResponse


class KnowledgeEntryPageResponse(BaseModel):
    knowledge_release_id: str
    entries: list[KnowledgeEntrySummaryResponse]
    stable_order: list[str]
    total_count: int
    next_cursor: str | None


class KnowledgeDirectoryFacetResponse(BaseModel):
    node_id: str
    node_type: KnowledgeDirectoryNodeType
    title: str
    parent_node_id: str | None
    entry_count: int


class KnowledgeDirectorySummaryResponse(BaseModel):
    knowledge_release_id: str
    nodes: list[KnowledgeDirectoryFacetResponse]


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
    review_status: Literal[KnowledgeReviewStatus.REVIEWED]


class StructuralConnectionResponse(BaseModel):
    connection_kind: Literal["structure"]
    connection_id: str
    source_node_id: str
    source_node_type: str
    source_title: str
    target_node_id: str
    target_node_type: str
    target_title: str
    connection_type: Literal["contains"]
    direction: Literal["outbound"]


class StructuralConnectionPageResponse(BaseModel):
    knowledge_release_id: str
    connections: list[StructuralConnectionResponse]
    stable_order: list[str]
    total_count: int
    next_cursor: str | None


class RelationCandidateResponse(BaseModel):
    candidate_id: str
    source_knowledge_id: str
    target_knowledge_id: str
    suggested_relation_type: str
    direction: str
    evidence_excerpt: str
    evidence_locator: str
    evidence_source_id: str
    source_content_version: int
    target_content_version: int
    producer: str
    producer_config_version: str
    score: float | None
    trigger_reason: str
    review_status: Literal[KnowledgeReviewStatus.PENDING]
    review_record_id: str | None


class RelationCandidatePageResponse(BaseModel):
    knowledge_release_id: str
    candidates: list[RelationCandidateResponse]
    stable_order: list[str]
    total_count: int
    next_cursor: str | None


class KnowledgeRelationPageResponse(BaseModel):
    knowledge_release_id: str
    relations: list[KnowledgeRelationResponse]
    stable_order: list[str]
    total_count: int
    next_cursor: str | None


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
    category_id: str
    category: str
    dimension_id: str
    dimension: str
    directory_path: list[KnowledgeDirectoryNodeResponse]
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
