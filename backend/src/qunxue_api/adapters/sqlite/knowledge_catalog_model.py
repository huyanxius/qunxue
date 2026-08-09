"""SQLite rows for immutable knowledge releases and their browse projection."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from qunxue_api.adapters.sqlite.base import Base


class KnowledgeReleaseRow(Base):
    __tablename__ = "knowledge_releases"
    __table_args__ = (Index("ix_knowledge_releases_current", "is_current", "level"),)

    knowledge_release_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(72), nullable=False, unique=True)
    build_config_version: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    built_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class KnowledgeEntryRevisionRow(Base):
    __tablename__ = "knowledge_entry_revisions"
    __table_args__ = (
        Index(
            "ix_knowledge_entry_revisions_release_browse",
            "knowledge_release_id",
            "browse_eligible",
            "knowledge_id",
        ),
        Index(
            "ix_knowledge_entry_revisions_release_dimension",
            "knowledge_release_id",
            "dimension_id",
        ),
    )

    knowledge_release_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_releases.knowledge_release_id", ondelete="CASCADE"),
        primary_key=True,
    )
    knowledge_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(72), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    category_id: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    category: Mapped[str | None] = mapped_column(String(512), nullable=True)
    dimension_id: Mapped[str] = mapped_column(String(16), nullable=False)
    dimension: Mapped[str] = mapped_column(String(64), nullable=False)
    directory_path: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False)
    browse_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rag_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    training_candidate_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    match_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    review_record_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(72), nullable=False)


class KnowledgeSourceRow(Base):
    __tablename__ = "knowledge_sources"

    knowledge_release_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_releases.knowledge_release_id", ondelete="CASCADE"),
        primary_key=True,
    )
    source_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    authors_or_institution: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publication: Mapped[str | None] = mapped_column(String(512), nullable=True)
    locator: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False)
    use_boundary: Mapped[str] = mapped_column(Text, nullable=False)


class KnowledgeRelationRow(Base):
    __tablename__ = "knowledge_relations"

    knowledge_release_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_releases.knowledge_release_id", ondelete="CASCADE"),
        primary_key=True,
    )
    relation_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    source_knowledge_id: Mapped[str] = mapped_column(String(128), nullable=False)
    target_knowledge_id: Mapped[str] = mapped_column(String(128), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_source_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_grade: Mapped[str] = mapped_column(String(32), nullable=False)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False)


class KnowledgeTheoryProfileRow(Base):
    __tablename__ = "knowledge_theory_profiles"

    knowledge_release_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_releases.knowledge_release_id", ondelete="CASCADE"),
        primary_key=True,
    )
    theory_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    related_knowledge_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    core_propositions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    applicable_phenomena: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    analysis_levels: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    prerequisites: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    exclusion_signals: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    observable_evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    competing_or_complementary_theory_ids: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
    )
    source_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False)
    match_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)


class KnowledgeEntryReviewRow(Base):
    __tablename__ = "knowledge_entry_reviews"

    knowledge_release_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_releases.knowledge_release_id", ondelete="CASCADE"),
        primary_key=True,
    )
    review_record_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    knowledge_id: Mapped[str] = mapped_column(String(128), nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
