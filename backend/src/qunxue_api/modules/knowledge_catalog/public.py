from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class RetrievalPipelineUnavailable(RuntimeError):
    """A required retrieval dependency failed; callers must not fabricate evidence."""


class KnowledgeReleaseLevel(StrEnum):
    WORKING = "working"
    PREVIEW = "preview"
    FINAL = "final"


class KnowledgeReviewStatus(StrEnum):
    DRAFT = "draft"
    PENDING = "pending"
    PRE_REVIEW_COMPLETED = "pre_review_completed"
    REVIEWED = "reviewed"
    RETIRED = "retired"


class KnowledgeUsePurpose(StrEnum):
    BROWSE = "browse"
    RAG = "rag"
    TRAINING_CANDIDATE = "training_candidate"
    MATCH = "match"


class SourceVerificationStatus(StrEnum):
    VERIFIED = "verified"
    SYSTEM_SUMMARY = "system_summary"
    PENDING = "pending"


class KnowledgeDirectoryNodeType(StrEnum):
    CATEGORY = "category"
    DIMENSION = "dimension"


@dataclass(frozen=True, slots=True)
class KnowledgeDirectoryNodeSnapshot:
    """One stable segment of an entry's catalog path."""

    node_id: str
    node_type: KnowledgeDirectoryNodeType
    title: str


@dataclass(frozen=True, slots=True)
class KnowledgeUseEligibility:
    """展示、检索、训练候选和正式匹配是四个独立准入结论。"""

    browse_eligible: bool
    rag_eligible: bool
    training_candidate_eligible: bool
    match_eligible: bool
    review_record_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KnowledgeReleaseRef:
    knowledge_release_id: str
    level: KnowledgeReleaseLevel
    content_hash: str


@dataclass(frozen=True, slots=True)
class KnowledgeReleaseManifest:
    release: KnowledgeReleaseRef
    knowledge_ids: tuple[str, ...]
    relation_candidate_ids: tuple[str, ...]
    relation_ids: tuple[str, ...]
    structural_connection_count: int
    theory_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    review_record_ids: tuple[str, ...]
    artifact_hashes: tuple[tuple[str, str], ...]
    built_at: datetime


@dataclass(frozen=True, slots=True)
class KnowledgeEntrySummary:
    knowledge_id: str
    content_version: int
    title: str
    category_id: str
    category: str
    dimension_id: str
    dimension: str
    directory_path: tuple[KnowledgeDirectoryNodeSnapshot, ...]
    review_status: KnowledgeReviewStatus
    eligibility: KnowledgeUseEligibility


@dataclass(frozen=True, slots=True)
class KnowledgeEntryPage:
    release: KnowledgeReleaseRef
    entries: tuple[KnowledgeEntrySummary, ...]
    total_count: int
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class KnowledgeDirectoryFacetSnapshot:
    """One release-bound directory node with its browsable descendant count."""

    node_id: str
    node_type: KnowledgeDirectoryNodeType
    title: str
    parent_node_id: str | None
    entry_count: int


@dataclass(frozen=True, slots=True)
class KnowledgeDirectorySummary:
    release: KnowledgeReleaseRef
    nodes: tuple[KnowledgeDirectoryFacetSnapshot, ...]


@dataclass(frozen=True, slots=True)
class SourceRecordSnapshot:
    source_id: str
    source_type: str
    title: str
    authors_or_institution: tuple[str, ...]
    year: int | None
    publication: str | None
    locator: str | None
    url: str | None
    verification_status: SourceVerificationStatus
    use_boundary: str


@dataclass(frozen=True, slots=True)
class KnowledgeRelationSnapshot:
    relation_id: str
    source_knowledge_id: str
    target_knowledge_id: str
    relation_type: str
    direction: str
    description: str
    evidence_source_ids: tuple[str, ...]
    evidence_grade: str
    content_version: int
    review_status: KnowledgeReviewStatus


@dataclass(frozen=True, slots=True)
class StructuralConnectionSnapshot:
    """Release-bound projection of one directory containment fact."""

    connection_id: str
    source_node_id: str
    source_node_type: str
    source_title: str
    target_node_id: str
    target_node_type: str
    target_title: str
    connection_type: str
    direction: str


@dataclass(frozen=True, slots=True)
class StructuralConnectionPage:
    release: KnowledgeReleaseRef
    connections: tuple[StructuralConnectionSnapshot, ...]
    total_count: int
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class RelationCandidateSnapshot:
    """Algorithm discovery data; pending candidates are not reviewed relations."""

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
    review_status: KnowledgeReviewStatus
    review_record_id: str | None


@dataclass(frozen=True, slots=True)
class RelationCandidatePage:
    release: KnowledgeReleaseRef
    candidates: tuple[RelationCandidateSnapshot, ...]
    total_count: int
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class KnowledgeRelationPage:
    release: KnowledgeReleaseRef
    relations: tuple[KnowledgeRelationSnapshot, ...]
    total_count: int
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class TheoryProfileSnapshot:
    """知识模块审核后的理论事实；不包含某次任务里的适用性判断。"""

    theory_id: str
    related_knowledge_ids: tuple[str, ...]
    title: str
    core_propositions: tuple[str, ...]
    applicable_phenomena: tuple[str, ...]
    analysis_levels: tuple[str, ...]
    prerequisites: tuple[str, ...]
    exclusion_signals: tuple[str, ...]
    observable_evidence: tuple[str, ...]
    competing_or_complementary_theory_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    content_version: int
    review_status: KnowledgeReviewStatus
    match_eligible: bool


@dataclass(frozen=True, slots=True)
class KnowledgeEntryDetail:
    release: KnowledgeReleaseRef
    summary: KnowledgeEntrySummary
    aliases: tuple[str, ...]
    content: str
    sources: tuple[SourceRecordSnapshot, ...]
    relations: tuple[KnowledgeRelationSnapshot, ...]
    theory_profile: TheoryProfileSnapshot | None


class KnowledgeCatalog(Protocol):
    """浏览与下游消费知识时唯一可见的版本化只读接口。"""

    def current_release(
        self,
        *,
        purpose: KnowledgeUsePurpose,
    ) -> KnowledgeReleaseRef: ...

    def browse(
        self,
        *,
        release_id: str,
        query: str | None,
        category: str | None,
        category_id: str | None,
        dimension_id: str | None,
        cursor: str | None,
        limit: int,
    ) -> KnowledgeEntryPage: ...

    def get_entry(
        self,
        *,
        knowledge_id: str,
        release_id: str,
    ) -> KnowledgeEntryDetail: ...

    def list_rag_entries(
        self,
        *,
        release_id: str,
    ) -> tuple[KnowledgeEntryDetail, ...]:
        """Return every RAG-eligible entry from exactly one release."""
        ...

    def get_directory(self, *, release_id: str) -> KnowledgeDirectorySummary: ...

    def get_theory_profile(
        self,
        *,
        theory_id: str,
        release_id: str,
    ) -> TheoryProfileSnapshot: ...

    def get_sources(
        self,
        *,
        source_ids: tuple[str, ...],
        release_id: str,
    ) -> tuple[SourceRecordSnapshot, ...]: ...

    def list_match_profiles(
        self,
        *,
        release_id: str,
    ) -> tuple[TheoryProfileSnapshot, ...]:
        """Return only fully audited profiles from one immutable final release."""
        ...

    def list_connections(
        self,
        *,
        release_id: str,
        source_node_id: str | None,
        cursor: str | None,
        limit: int,
    ) -> StructuralConnectionPage: ...

    def list_relation_candidates(
        self,
        *,
        release_id: str,
        knowledge_id: str | None,
        cursor: str | None,
        limit: int,
    ) -> RelationCandidatePage: ...

    def list_relations(
        self,
        *,
        release_id: str,
        knowledge_id: str | None,
        cursor: str | None,
        limit: int,
    ) -> KnowledgeRelationPage: ...


class KnowledgeReleasePublisher(Protocol):
    """Install an externally pre-reviewed artifact; never manufacture review state."""

    def install_pre_reviewed_bundle(
        self, bundle_path: Path
    ) -> KnowledgeReleaseManifest: ...

    def get_manifest(self, release_id: str) -> KnowledgeReleaseManifest: ...
