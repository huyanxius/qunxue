"""Persist Agent research-start proposals and task provenance."""

from collections.abc import Iterator
from contextlib import contextmanager

import sqlalchemy as sa
from alembic import op

revision = "20260820_0007"
down_revision = "20260820_0006"
branch_labels = None
depends_on = None


@contextmanager
def _sqlite_batch_foreign_keys_disabled() -> Iterator[None]:
    """Prevent SQLite batch table swaps from cascading into dependent rows."""

    migration_context = op.get_context()
    if migration_context.dialect.name != "sqlite":
        yield
        return
    with migration_context.autocommit_block():
        op.execute(sa.text("PRAGMA foreign_keys=OFF"))
    try:
        yield
    finally:
        with migration_context.autocommit_block():
            op.execute(sa.text("PRAGMA foreign_keys=ON"))


def upgrade() -> None:
    columns = (
        sa.Column("knowledge_release_id", sa.String(128), nullable=True),
        sa.Column("conversation_id", sa.String(36), nullable=True),
        sa.Column("source_turn_id", sa.String(36), nullable=True),
        sa.Column("source_agent_run_id", sa.String(36), nullable=True),
    )
    if op.get_bind().dialect.name == "sqlite":
        # Rebuilding research_tasks would cascade-delete existing M4/M5 rows.
        # SQLite can add these nullable columns in place; the unique index keeps
        # the cross-process conversation binding invariant without data loss.
        for column in columns:
            op.add_column("research_tasks", column)
        op.create_index(
            "uq_research_tasks_conversation",
            "research_tasks",
            ["conversation_id"],
            unique=True,
        )
    else:
        with op.batch_alter_table("research_tasks") as batch:
            for column in columns:
                batch.add_column(column)
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
    if op.get_bind().dialect.name == "sqlite":
        op.drop_index("uq_research_tasks_conversation", table_name="research_tasks")
        with _sqlite_batch_foreign_keys_disabled(), op.batch_alter_table(
            "research_tasks"
        ) as batch:
            batch.drop_column("source_agent_run_id")
            batch.drop_column("source_turn_id")
            batch.drop_column("conversation_id")
            batch.drop_column("knowledge_release_id")
    else:
        with op.batch_alter_table("research_tasks") as batch:
            batch.drop_constraint("uq_research_tasks_conversation", type_="unique")
            batch.drop_constraint("fk_research_tasks_agent_run", type_="foreignkey")
            batch.drop_constraint("fk_research_tasks_conversation", type_="foreignkey")
            batch.drop_column("source_agent_run_id")
            batch.drop_column("source_turn_id")
            batch.drop_column("conversation_id")
            batch.drop_column("knowledge_release_id")
