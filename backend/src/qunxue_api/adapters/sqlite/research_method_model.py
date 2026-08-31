from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from qunxue_api.adapters.sqlite.base import Base


class ResearchMethodPlanIdentityRow(Base):
    __tablename__ = "research_method_plan_identities"
    __table_args__ = (UniqueConstraint("plan_id"),)

    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), primary_key=True
    )
    plan_id: Mapped[str] = mapped_column(String(36), nullable=False)


class ResearchMethodPlanVersionRow(Base):
    __tablename__ = "research_method_plan_versions"
    __table_args__ = (
        Index("ix_research_method_plan_versions_task", "task_id", "created_at"),
        UniqueConstraint("revision_id"),
    )

    plan_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), nullable=False
    )
    framework_id: Mapped[str] = mapped_column(String(36), nullable=False)
    framework_version: Mapped[int] = mapped_column(Integer, nullable=False)
    theory_plan_id: Mapped[str] = mapped_column(String(36), nullable=False)
    theory_plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    method_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    decision_source: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    research_question: Mapped[str] = mapped_column(Text, nullable=False)
    theory_summary: Mapped[str] = mapped_column(Text, nullable=False)
    material_constraints: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    ethical_constraints: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    theory_concepts: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_ref_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    knowledge_release_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    shared_context: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    sections: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False)
    reviews: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    revision_id: Mapped[str] = mapped_column(String(36), nullable=False)
    change_summary: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    restored_from_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stale_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
