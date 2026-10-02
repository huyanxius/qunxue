"""Frontier persistence, separate tables and provenance from stable knowledge."""

from sqlalchemy import (
    DDL,
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from qunxue_api.adapters.sqlite.base import Base


class FrontierSourceRow(Base):
    __tablename__ = "frontier_sources"
    source_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    adapter_type: Mapped[str] = mapped_column(String(80))
    base_url: Mapped[str] = mapped_column(Text)
    schedule_hours: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(80))
    cursor: Mapped[str | None] = mapped_column(Text)
    last_success_at: Mapped[str | None] = mapped_column(String(40))
    last_error: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict] = mapped_column(JSON)


class FrontierItemRow(Base):
    __tablename__ = "frontier_items"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_frontier_source_external"),
        Index("ix_frontier_doi", "doi"),
        Index("ix_frontier_title_author", "title_author_key"),
        Index("ix_frontier_body_hash", "body_hash"),
    )
    item_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("frontier_sources.source_id"))
    external_id: Mapped[str] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(Text)
    doi: Mapped[str | None] = mapped_column(String(300))
    title_author_key: Mapped[str] = mapped_column(String(64))
    body_hash: Mapped[str | None] = mapped_column(String(64))
    canonical_study_id: Mapped[str] = mapped_column(String(160), index=True)
    dedupe_level: Mapped[str] = mapped_column(String(40))
    original_item_id: Mapped[str | None] = mapped_column(String(160))


class FrontierSnapshotRow(Base):
    __tablename__ = "frontier_snapshots"
    __table_args__ = (UniqueConstraint("item_id", "content_hash", name="uq_frontier_snapshot"),)
    snapshot_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("frontier_items.item_id"))
    source_id: Mapped[str] = mapped_column(ForeignKey("frontier_sources.source_id"))
    content_hash: Mapped[str] = mapped_column(String(64))
    scope: Mapped[str] = mapped_column(String(80))
    fetched_at: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)


class FrontierRecordRow(Base):
    __tablename__ = "frontier_records"
    __table_args__ = (
        UniqueConstraint("item_id", "version", name="uq_frontier_record_version"),
        Index(
            "ix_frontier_browse_date_id", "is_current", "read_browse", "read_sort_date", "record_id"
        ),
        Index("ix_frontier_browse_available", "is_current", "read_browse", "read_available_on"),
    )
    record_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("frontier_items.item_id"))
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("frontier_snapshots.snapshot_id"))
    source_id: Mapped[str] = mapped_column(ForeignKey("frontier_sources.source_id"))
    canonical_study_id: Mapped[str] = mapped_column(String(160), index=True)
    version: Mapped[int] = mapped_column(Integer)
    verification_status: Mapped[str] = mapped_column(String(40))
    rag_eligible: Mapped[bool] = mapped_column(Boolean)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    structured_json: Mapped[dict] = mapped_column(JSON)
    read_browse: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    read_available_on: Mapped[str | None] = mapped_column(String(10))
    read_topic_available_on: Mapped[str | None] = mapped_column(String(10))
    read_display_date: Mapped[str] = mapped_column(String(40), default="", nullable=True)
    read_sort_date: Mapped[str] = mapped_column(String(40), default="", nullable=True)
    read_publication_day: Mapped[str | None] = mapped_column(String(10))
    read_stream: Mapped[str] = mapped_column(String(20), default="research", nullable=True)
    read_topic_keys: Mapped[list] = mapped_column(JSON, default=list, nullable=True)
    read_lexical_text: Mapped[str] = mapped_column(Text, default="", nullable=True)
    read_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=True)


class FrontierClaimRow(Base):
    __tablename__ = "frontier_claims"
    claim_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    record_id: Mapped[str] = mapped_column(ForeignKey("frontier_records.record_id"), index=True)
    claim_text: Mapped[str] = mapped_column(Text)
    evidence_block_ids: Mapped[list] = mapped_column(JSON)
    verifier_status: Mapped[str] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(Text)


class FrontierJobRow(Base):
    __tablename__ = "frontier_jobs"
    __table_args__ = (Index("ix_frontier_jobs_ready", "status", "next_run_at"),)
    job_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    stage: Mapped[str] = mapped_column(String(40))
    object_id: Mapped[str] = mapped_column(String(200))
    idempotency_key: Mapped[str] = mapped_column(String(500), unique=True)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    next_run_at: Mapped[float] = mapped_column(Float, default=0)
    lease_until: Mapped[float | None] = mapped_column(Float)
    lease_token: Mapped[str | None] = mapped_column(String(80))
    error: Mapped[str | None] = mapped_column(Text)


class FrontierIndexRow(Base):
    __tablename__ = "frontier_index"
    record_id: Mapped[str] = mapped_column(
        ForeignKey("frontier_records.record_id"), primary_key=True
    )
    content_hash: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(40))
    lexical_text: Mapped[str] = mapped_column(Text)
    embedding_status: Mapped[str] = mapped_column(String(40), default="not_configured")


class FrontierTopicRunRow(Base):
    __tablename__ = "frontier_topic_runs"
    run_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    as_of: Mapped[str] = mapped_column(String(10))
    input_hash: Mapped[str] = mapped_column(String(64))
    method: Mapped[str] = mapped_column(String(80))
    payload: Mapped[list] = mapped_column(JSON)


class FrontierReviewRow(Base):
    __tablename__ = "frontier_reviews"
    review_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("frontier_snapshots.snapshot_id"))
    job_id: Mapped[str] = mapped_column(ForeignKey("frontier_jobs.job_id"), unique=True)
    status: Mapped[str] = mapped_column(String(40))
    extracted: Mapped[dict] = mapped_column(JSON)
    verdicts: Mapped[list] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)


class FrontierEditorialBriefRow(Base):
    __tablename__ = "frontier_editorial_briefs"
    brief_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    topic_key: Mapped[str] = mapped_column(String(80))
    stream: Mapped[str] = mapped_column(String(20))
    basis_content_hash: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)


class FrontierEmbeddingCacheRow(Base):
    __tablename__ = "frontier_embedding_cache"
    model: Mapped[str] = mapped_column(String(200), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(40), primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    vector: Mapped[list] = mapped_column(JSON)


class FrontierVectorRow(Base):
    __tablename__ = "frontier_vectors"
    chunk_id: Mapped[str] = mapped_column(String(250), primary_key=True)
    record_id: Mapped[str] = mapped_column(ForeignKey("frontier_records.record_id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(200))
    schema_version: Mapped[str] = mapped_column(String(40))
    content_hash: Mapped[str] = mapped_column(String(64))
    vector: Mapped[list] = mapped_column(JSON)


class FrontierRevisionRow(Base):
    __tablename__ = "frontier_revision"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)


@event.listens_for(FrontierRecordRow, "before_insert")
@event.listens_for(FrontierRecordRow, "before_update")
def refresh_read_projection(_mapper, _connection, row):
    from qunxue_api.modules.frontier_knowledge import read_projection

    for key, value in read_projection(row.structured_json).items():
        setattr(row, key, value)


# A persistent revision works across API/worker processes and raw SQL writes.
# It is changed in the writer's transaction, including import/update/withdrawal.
FRONTIER_REVISION_TABLES = (
    "frontier_records",
    "frontier_sources",
    "frontier_editorial_briefs",
    "frontier_topic_runs",
)
for _table in FRONTIER_REVISION_TABLES:
    for _operation in ("INSERT", "UPDATE", "DELETE"):
        event.listen(
            Base.metadata.tables[_table],
            "after_create",
            DDL(f"""CREATE TRIGGER IF NOT EXISTS {_table}_revision_{_operation.lower()}
                AFTER {_operation} ON {_table} BEGIN
                INSERT INTO frontier_revision (id, revision) VALUES (1, 1)
                ON CONFLICT(id) DO UPDATE SET revision = revision + 1;
                END"""),
        )
