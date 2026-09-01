from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from qunxue_api.adapters.sqlite.base import Base


class ResearchCycleSnapshotRow(Base):
    __tablename__ = "research_cycle_snapshots"
    __table_args__ = (
        UniqueConstraint("task_id", "content_hash", name="uq_research_cycle_task_content"),
        Index("ix_research_cycle_task_version", "task_id", "version"),
    )

    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(72), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
