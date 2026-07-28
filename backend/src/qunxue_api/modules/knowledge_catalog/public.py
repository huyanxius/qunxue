from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class KnowledgeReleaseLevel(StrEnum):
    WORKING = "working"
    PREVIEW = "preview"
    FINAL = "final"


class KnowledgeReviewStatus(StrEnum):
    DRAFT = "draft"
    PENDING = "pending"
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
    relation_ids: tuple[str, ...]
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
    category: str
    dimension: str
    review_status: KnowledgeReviewStatus
    eligibility: KnowledgeUseEligibility


@dataclass(frozen=True, slots=True)
class KnowledgeEntryPage:
    release: KnowledgeReleaseRef
    entries: tuple[KnowledgeEntrySummary, ...]
    next_cursor: str | None


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
    algorithm_weight: float | None
    algorithm_config_version: str | None
    content_version: int
    review_status: KnowledgeReviewStatus


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


@dataclass(frozen=True, slots=True)
class KnowledgePublicationRequest:
    """发布器只接收已审核对象清单，不替代审核或补写缺失内容。"""

    level: KnowledgeReleaseLevel
    knowledge_ids: tuple[str, ...]
    relation_ids: tuple[str, ...]
    theory_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    review_record_ids: tuple[str, ...]
    build_config_version: str


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
        cursor: str | None,
    ) -> KnowledgeEntryPage: ...

    def get_entry(
        self,
        *,
        knowledge_id: str,
        release_id: str,
    ) -> KnowledgeEntryDetail: ...

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


class KnowledgeReleasePublisher(Protocol):
    """写侧发布能力与用户浏览分离；适配器负责持久化和产物构建。"""

    def publish(
        self,
        *,
        request: KnowledgePublicationRequest,
    ) -> KnowledgeReleaseManifest: ...

    def get_manifest(self, release_id: str) -> KnowledgeReleaseManifest: ...
