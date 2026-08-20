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


class ResearchDocumentProposalRow(Base):
    __tablename__ = "research_document_proposals"
    __table_args__ = (
        Index("ix_research_document_proposals_user_status", "user_id", "status"),
        Index("ix_research_document_proposals_document", "document_id", "created_at"),
        UniqueConstraint(
            "agent_run_id",
            "document_id",
            "base_document_version",
            "target_section_id",
            name="uq_research_document_proposal_agent_target",
        ),
    )

    proposal_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("agent_conversations.conversation_id", ondelete="CASCADE"), nullable=False
    )
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.run_id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), nullable=False
    )
    theory_plan_id: Mapped[str] = mapped_column(
        ForeignKey("confirmed_theory_plans.theory_plan_id", ondelete="CASCADE"),
        nullable=False,
    )
    knowledge_release_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    proposed_sections: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(72), nullable=False)
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    base_document_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_section_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    result_document_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
