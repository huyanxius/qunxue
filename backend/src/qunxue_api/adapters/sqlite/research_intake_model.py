from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from qunxue_api.adapters.sqlite.base import Base


class ResearchTaskRow(Base):
    __tablename__ = "research_tasks"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_research_tasks_user_request"),
        Index("ix_research_tasks_user_updated", "user_id", "updated_at"),
    )

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # 旧迁移留下的孤立任务没有归属，保持不可见；所有新任务必须由服务写入 user_id。
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=True,
    )
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    seed_theory_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    seed_theory_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    phenomenon_query_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    phenomenon_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phenomenon_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    phenomenon_research_intent: Mapped[str | None] = mapped_column(Text, nullable=True)
    adopted_theory_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    current_phenomenon_candidate_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )
    current_material_intake_run_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )
    current_match_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    current_theory_plan_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    current_framework_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PhenomenonStateRow(Base):
    """One current candidate chain per task; confirmed content is retained in-place."""

    __tablename__ = "phenomenon_states"

    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), primary_key=True
    )
    input_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    input_version: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_id: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)
    candidate_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    phenomenon: Mapped[str] = mapped_column(String(10000), nullable=False)
    research_intent: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    context: Mapped[str | None] = mapped_column(String(10000), nullable=True)
    source_ref_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_refs: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    missing_information: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source_traceability: Mapped[str] = mapped_column(String(32), nullable=False)
    content_origin: Mapped[str] = mapped_column(String(32), nullable=False)
    model_provider: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_capability: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model_degraded: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    knowledge_release_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    contract_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phenomenon_query_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PhenomenonCandidateVersionRow(Base):
    """Append-only candidate content; the state row only points at the latest version."""

    __tablename__ = "phenomenon_candidate_versions"
    __table_args__ = (
        Index("ix_phenomenon_candidate_versions_task", "task_id", "candidate_id"),
    )

    candidate_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    phenomenon: Mapped[str] = mapped_column(String(10000), nullable=False)
    research_intent: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    context: Mapped[str | None] = mapped_column(String(10000), nullable=True)
    source_ref_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_refs: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    missing_information: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source_traceability: Mapped[str] = mapped_column(String(32), nullable=False)
    content_origin: Mapped[str] = mapped_column(String(32), nullable=False)
    model_provider: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    model_capability: Mapped[str] = mapped_column(String(32), nullable=False)
    model_degraded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    knowledge_release_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PhenomenonExampleRow(Base):
    __tablename__ = "phenomenon_examples"

    example_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    phenomenon: Mapped[str] = mapped_column(String(10000), nullable=False)
    research_intent: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    context: Mapped[str | None] = mapped_column(String(10000), nullable=True)


class MaterialIntakeRunRow(Base):
    __tablename__ = "material_intake_runs"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "idempotency_key",
            name="uq_material_intake_task_request",
        ),
    )

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    processing_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
