"""SQLite rows for professional organization and ethics metadata."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from qunxue_api.adapters.sqlite.base import Base


class MaterialBatchRow(Base):
    __tablename__ = "research_material_batches"
    __table_args__ = (
        UniqueConstraint("user_id", "task_id", "name", name="uq_material_batch_task_name"),
        Index("ix_material_batches_task_created", "user_id", "task_id", "created_at"),
    )

    batch_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MaterialCollectionRow(Base):
    __tablename__ = "research_material_collections"
    __table_args__ = (
        UniqueConstraint("user_id", "task_id", "name", name="uq_material_collection_task_name"),
        Index("ix_material_collections_task_created", "user_id", "task_id", "created_at"),
    )

    collection_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_collection_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_material_collections.collection_id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MaterialArchiveProfileRow(Base):
    __tablename__ = "research_material_archive_profiles"
    __table_args__ = (
        Index("ix_material_profiles_task_stage", "user_id", "task_id", "stage"),
        Index(
            "ix_material_profiles_task_policy",
            "user_id",
            "task_id",
            "model_processing_scope",
        ),
    )

    material_id: Mapped[str] = mapped_column(
        ForeignKey("research_materials.material_id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    research_role: Mapped[str] = mapped_column(String(64), nullable=False)
    specific_type: Mapped[str] = mapped_column(String(96), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_material_batches.batch_id", ondelete="SET NULL"), nullable=True
    )
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    collection_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    sensitivity: Mapped[str] = mapped_column(String(32), nullable=False)
    consent_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    deidentification_status: Mapped[str] = mapped_column(String(32), nullable=False)
    model_processing_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LiteratureEntryRow(Base):
    __tablename__ = "research_literature_entries"
    __table_args__ = (
        Index("ix_literature_task_title", "user_id", "task_id", "title"),
        Index("ix_literature_task_doi", "user_id", "task_id", "doi"),
    )

    literature_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    item_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    doi: Mapped[str | None] = mapped_column(String(300), nullable=True)
    csl_data: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    attachment_material_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    collection_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ResearchCaseRow(Base):
    __tablename__ = "research_cases"
    __table_args__ = (
        UniqueConstraint("user_id", "task_id", "name", name="uq_research_case_task_name"),
        Index("ix_research_cases_task_created", "user_id", "task_id", "created_at"),
    )

    case_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    attributes: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    material_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MaterialRelationRow(Base):
    __tablename__ = "research_material_relations"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "task_id",
            "source_material_id",
            "target_material_id",
            "relation_type",
            name="uq_material_relation_identity",
        ),
        Index(
            "ix_material_relations_task_source",
            "user_id",
            "task_id",
            "source_material_id",
        ),
    )

    relation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_material_id: Mapped[str] = mapped_column(
        ForeignKey("research_materials.material_id", ondelete="CASCADE"), nullable=False
    )
    target_material_id: Mapped[str] = mapped_column(
        ForeignKey("research_materials.material_id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
