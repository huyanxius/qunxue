from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from qunxue_api.adapters.sqlite.base import Base


class MatchRunRow(Base):
    __tablename__ = "match_runs"
    __table_args__ = (Index("ix_match_runs_task", "task_id", "match_run_id"),)

    match_run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    model_provider: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_capability: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model_degraded: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    model_knowledge_release_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    contract_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TheoryMatchingRequestRow(Base):
    __tablename__ = "theory_matching_requests"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_theory_matching_user_request",
        ),
    )

    request_record_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(72), nullable=False)
    match_run_id: Mapped[str] = mapped_column(
        ForeignKey("match_runs.match_run_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TheoryDecisionSetRow(Base):
    __tablename__ = "theory_decision_sets"
    __table_args__ = (
        UniqueConstraint("match_run_id", name="uq_theory_decision_sets_match_run"),
    )

    decision_set_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    match_run_id: Mapped[str] = mapped_column(
        ForeignKey("match_runs.match_run_id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(72), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConfirmedTheoryPlanRow(Base):
    __tablename__ = "confirmed_theory_plans"

    theory_plan_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), nullable=False, index=True
    )
    match_run_id: Mapped[str] = mapped_column(
        ForeignKey("match_runs.match_run_id", ondelete="CASCADE"), nullable=False
    )
    decision_set_id: Mapped[str] = mapped_column(
        ForeignKey("theory_decision_sets.decision_set_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    adopted_candidate_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(72), nullable=True)
