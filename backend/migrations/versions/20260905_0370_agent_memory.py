"""Persist scoped Agent memory, revision fences and recoverable learning jobs."""

import sqlalchemy as sa
from alembic import op

revision = "20260905_0370"
down_revision = "20260905_0360"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_memory_scopes",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("scope_key", sa.String(36), primary_key=True),
        sa.Column(
            "task_id", sa.String(36), sa.ForeignKey("research_tasks.task_id", ondelete="CASCADE")
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("use_memory", sa.Boolean(), nullable=False),
        sa.Column("learn_memory", sa.Boolean(), nullable=False),
        sa.Column("learn_after", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "agent_memories",
        sa.Column("memory_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("scope_key", sa.String(36), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_conversation_id", sa.String(36)),
        sa.Column("source_message_id", sa.String(36)),
        sa.Column("source_quote", sa.Text()),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id", "scope_key"],
            ["agent_memory_scopes.user_id", "agent_memory_scopes.scope_key"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", "scope_key", "key"),
    )
    op.create_table(
        "agent_memory_revisions",
        sa.Column(
            "memory_id",
            sa.String(36),
            sa.ForeignKey("agent_memories.memory_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
    )
    op.create_table(
        "agent_memory_requests",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("idempotency_key", sa.String(128), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "memory_id",
            sa.String(36),
            sa.ForeignKey("agent_memories.memory_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_table(
        "agent_memory_jobs",
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("agent_conversations.conversation_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("processed_sequence", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("retry_after", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("source_sequence", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(64)),
    )
    op.create_table(
        "agent_memory_usage",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("day", sa.String(10), primary_key=True),
        sa.Column("calls", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("budget_tokens", sa.Integer(), nullable=False),
    )


def downgrade():
    for name in (
        "agent_memory_usage",
        "agent_memory_jobs",
        "agent_memory_requests",
        "agent_memory_revisions",
        "agent_memories",
        "agent_memory_scopes",
    ):
        op.drop_table(name)
