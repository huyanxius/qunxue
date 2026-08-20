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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from qunxue_api.adapters.sqlite.base import Base


class AgentConversationRow(Base):
    __tablename__ = "agent_conversations"
    __table_args__ = (Index("ix_agent_conversations_user_updated", "user_id", "updated_at"),)

    conversation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    current_research_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="SET NULL"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentMessageRow(Base):
    __tablename__ = "agent_messages"
    __table_args__ = (
        Index("ix_agent_messages_conversation_sequence", "conversation_id", "sequence"),
    )

    message_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("agent_conversations.conversation_id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentRunRow(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_conversation_status", "conversation_id", "status"),
        Index("ix_agent_runs_turn_id", "turn_id"),
        Index(
            "uq_agent_runs_active_conversation",
            "conversation_id",
            unique=True,
            sqlite_where=text("status = 'running'"),
        ),
        UniqueConstraint("conversation_id", "idempotency_key"),
    )

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("agent_conversations.conversation_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    knowledge_release_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    usage: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    tool_summary: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
