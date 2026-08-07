from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
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
    current_match_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    current_framework_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
