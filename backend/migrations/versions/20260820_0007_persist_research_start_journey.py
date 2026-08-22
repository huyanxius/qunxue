"""Persist Agent research-start proposals and task provenance."""

import sqlalchemy as sa
from alembic import op

revision = "20260820_0007"
down_revision = "20260820_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("research_tasks") as batch:
        batch.add_column(sa.Column("knowledge_release_id", sa.String(128), nullable=True))
        batch.add_column(sa.Column("conversation_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("source_turn_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("source_agent_run_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_research_tasks_conversation",
            "agent_conversations",
            ["conversation_id"],
            ["conversation_id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_research_tasks_agent_run",
            "agent_runs",
            ["source_agent_run_id"],
            ["run_id"],
            ondelete="SET NULL",
        )
        batch.create_unique_constraint(
            "uq_research_tasks_conversation",
            ["conversation_id"],
        )

    op.create_table(
        "research_start_proposals",
        sa.Column("proposal_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("source_run_id", sa.String(36), nullable=False),
        sa.Column("source_turn_id", sa.String(36), nullable=False),
        sa.Column("knowledge_release_id", sa.String(128), nullable=False),
        sa.Column("phenomenon", sa.String(10000), nullable=False),
        sa.Column("research_intent", sa.String(4000), nullable=True),
        sa.Column("context", sa.String(10000), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("confirmed_task_id", sa.String(36), nullable=True),
        sa.Column("confirmed_request_hash", sa.String(71), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["agent_conversations.conversation_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["source_run_id"], ["agent_runs.run_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["confirmed_task_id"], ["research_tasks.task_id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("proposal_id"),
        sa.UniqueConstraint("source_run_id", name="uq_research_start_proposal_source_run"),
        sa.UniqueConstraint("confirmed_task_id"),
    )
    op.create_index(
        "ix_research_start_proposals_user_id",
        "research_start_proposals",
        ["user_id"],
    )
    op.create_index(
        "ix_research_start_proposals_conversation_created",
        "research_start_proposals",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "research_start_confirmations",
        sa.Column("confirmation_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("proposal_id", sa.String(36), nullable=False),
        sa.Column("request_hash", sa.String(71), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["proposal_id"], ["research_start_proposals.proposal_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("confirmation_id"),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_research_start_confirmation_user_request",
        ),
    )


def downgrade() -> None:
    op.drop_table("research_start_confirmations")
    op.drop_index(
        "ix_research_start_proposals_conversation_created",
        table_name="research_start_proposals",
    )
    op.drop_index(
        "ix_research_start_proposals_user_id",
        table_name="research_start_proposals",
    )
    op.drop_table("research_start_proposals")
    with op.batch_alter_table("research_tasks") as batch:
        batch.drop_constraint("uq_research_tasks_conversation", type_="unique")
        batch.drop_constraint("fk_research_tasks_agent_run", type_="foreignkey")
        batch.drop_constraint("fk_research_tasks_conversation", type_="foreignkey")
        batch.drop_column("source_agent_run_id")
        batch.drop_column("source_turn_id")
        batch.drop_column("conversation_id")
        batch.drop_column("knowledge_release_id")
