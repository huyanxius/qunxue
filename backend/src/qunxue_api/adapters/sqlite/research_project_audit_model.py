from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from qunxue_api.adapters.sqlite.base import Base


class ResearchProjectExchangeRunRow(Base):
    __tablename__ = "research_project_exchange_runs"
    __table_args__ = (
        CheckConstraint(
            "direction IN ('import', 'export')",
            name="ck_research_project_exchange_direction",
        ),
        CheckConstraint(
            "status IN ('processing', 'completed', 'failed')",
            name="ck_research_project_exchange_status",
        ),
        UniqueConstraint(
            "user_id",
            "task_id",
            "direction",
            "idempotency_key",
            name="uq_research_project_exchange_idempotency",
        ),
        Index("ix_research_project_exchange_task_created", "user_id", "task_id", "created_at"),
    )

    exchange_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    format: Mapped[str] = mapped_column(String(64), nullable=False)
    format_version: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    artifact_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    loss_report: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ResearchProjectAuditEventRow(Base):
    __tablename__ = "research_project_audit_events"
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('user', 'agent', 'system')",
            name="ck_research_project_audit_actor_type",
        ),
        Index("ix_research_project_audit_task_occurred", "user_id", "task_id", "occurred_at"),
        Index("ix_research_project_audit_object", "object_type", "object_id", "occurred_at"),
    )

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str] = mapped_column(String(512), nullable=False)
    object_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
