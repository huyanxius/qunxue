from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from qunxue_api.adapters.sqlite.base import Base


class ResearchDocumentVersionRow(Base):
    __tablename__ = "research_document_versions"
    __table_args__ = (
        Index("ix_research_document_versions_task", "task_id", "document_id"),
        UniqueConstraint("revision_id"),
    )

    document_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), nullable=False
    )
    theory_plan_id: Mapped[str] = mapped_column(
        ForeignKey("confirmed_theory_plans.theory_plan_id", ondelete="CASCADE"),
        nullable=False,
    )
    knowledge_release_id: Mapped[str] = mapped_column(String(128), nullable=False)
    revision_id: Mapped[str] = mapped_column(String(36), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    sections: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    analysis_handoff: Mapped[dict[str, object] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    change_summary: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    restored_from_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchDocumentIdentityRow(Base):
    """Stable task/plan identity; historical duplicate documents remain auditable."""

    __tablename__ = "research_document_identities"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            name="uq_research_document_identity_document",
        ),
    )

    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"),
        primary_key=True,
    )
    theory_plan_id: Mapped[str] = mapped_column(
        ForeignKey("confirmed_theory_plans.theory_plan_id", ondelete="CASCADE"),
        primary_key=True,
    )
    document_id: Mapped[str] = mapped_column(String(36), nullable=False)


class ResearchDocumentMutationRequestRow(Base):
    __tablename__ = "research_document_mutation_requests"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_research_document_mutation_user_key",
        ),
    )

    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(72), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    result_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    result_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
