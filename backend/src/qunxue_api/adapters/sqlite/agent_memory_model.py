from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class MemoryScopeRow(Base):
    __tablename__ = "agent_memory_scopes"
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    scope_key: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    use_memory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    learn_memory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    learn_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MemoryRow(Base):
    __tablename__ = "agent_memories"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "scope_key"],
            ["agent_memory_scopes.user_id", "agent_memory_scopes.scope_key"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("user_id", "scope_key", "key"),
    )
    memory_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(36), nullable=False)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_conversation_id: Mapped[str | None] = mapped_column(String(36))
    source_message_id: Mapped[str | None] = mapped_column(String(36))
    source_quote: Mapped[str | None] = mapped_column(Text)
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class MemoryRevisionRow(Base):
    __tablename__ = "agent_memory_revisions"
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("agent_memories.memory_id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)


class MemoryRequestRow(Base):
    __tablename__ = "agent_memory_requests"
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("agent_memories.memory_id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)


class MemoryJobRow(Base):
    __tablename__ = "agent_memory_jobs"
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("agent_conversations.conversation_id", ondelete="CASCADE"), primary_key=True
    )
    # Conversation messages are zero-based; -1 means no message has been consumed.
    processed_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)
    last_error: Mapped[str | None] = mapped_column(String(64))


class MemoryUsageRow(Base):
    __tablename__ = "agent_memory_usage"
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    budget_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
