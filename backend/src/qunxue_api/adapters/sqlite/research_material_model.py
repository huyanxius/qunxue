"""SQLite rows for user-owned research materials and immutable parses."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from qunxue_api.adapters.sqlite.base import Base


class ResearchMaterialRow(Base):
    __tablename__ = "research_materials"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "task_id",
            "idempotency_key",
            name="uq_research_materials_user_task_request",
        ),
        UniqueConstraint(
            "user_id",
            "task_id",
            "delete_idempotency_key",
            name="uq_research_materials_user_task_delete_request",
        ),
        Index("ix_research_materials_user_task_updated", "user_id", "task_id", "updated_at"),
        Index("ix_research_materials_task_status", "task_id", "status"),
    )

    material_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    delete_idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    material_format: Mapped[str] = mapped_column(String(32), nullable=False)
    material_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_parse_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    current_parse_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processing_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchMaterialBlobRow(Base):
    __tablename__ = "research_material_blobs"

    material_id: Mapped[str] = mapped_column(
        ForeignKey("research_materials.material_id", ondelete="CASCADE"),
        primary_key=True,
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class ResearchMaterialReparseRequestRow(Base):
    """Durable claim for one task-scoped reparse request."""

    __tablename__ = "research_material_reparse_requests"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "task_id",
            "idempotency_key",
            name="uq_research_material_reparse_request",
        ),
        UniqueConstraint(
            "parse_id",
            name="uq_research_material_reparse_parse_id",
        ),
    )

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"),
        primary_key=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    material_id: Mapped[str] = mapped_column(
        ForeignKey("research_materials.material_id", ondelete="CASCADE"),
        nullable=False,
    )
    parse_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ResearchMaterialIngestionJobRow(Base):
    """Durable local-worker queue for document parsing and FTS projection."""

    __tablename__ = "research_material_ingestion_jobs"
    __table_args__ = (
        UniqueConstraint("material_id", "parse_id", name="uq_material_ingestion_parse"),
        Index(
            "ix_material_ingestion_recovery",
            "ingestion_status",
            "available_at",
            "lease_expires_at",
        ),
    )

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    material_id: Mapped[str] = mapped_column(
        ForeignKey("research_materials.material_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    parse_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ingestion_status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchMaterialParseVersionRow(Base):
    __tablename__ = "research_material_parse_versions"
    __table_args__ = (
        UniqueConstraint(
            "material_id",
            "version",
            name="uq_research_material_parse_material_version",
        ),
        Index(
            "ix_research_material_parse_material_created",
            "material_id",
            "created_at",
        ),
    )

    parse_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    material_id: Mapped[str] = mapped_column(
        ForeignKey("research_materials.material_id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parser_name: Mapped[str] = mapped_column(String(128), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    structured_document: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchMaterialBlockRow(Base):
    __tablename__ = "research_material_blocks"
    __table_args__ = (
        UniqueConstraint(
            "parse_id",
            "ordinal",
            name="uq_research_material_block_parse_ordinal",
        ),
        Index(
            "ix_research_material_blocks_material_parse",
            "material_id",
            "parse_id",
            "ordinal",
        ),
    )

    parse_id: Mapped[str] = mapped_column(
        ForeignKey("research_material_parse_versions.parse_id", ondelete="CASCADE"),
        primary_key=True,
    )
    segment_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    material_id: Mapped[str] = mapped_column(
        ForeignKey("research_materials.material_id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    locator: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    embedding_vectors: Mapped[dict[str, list[float]]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
