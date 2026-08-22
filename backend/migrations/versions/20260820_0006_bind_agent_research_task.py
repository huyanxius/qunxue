"""Bind an Agent conversation to its current research task."""

import sqlalchemy as sa
from alembic import context, op

revision = "20260820_0006"
down_revision = "20260820_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        op.add_column(
            "agent_conversations",
            sa.Column(
                "current_research_task_id",
                sa.String(36),
                nullable=True,
            ),
        )
        return
    with op.batch_alter_table("agent_conversations") as batch:
        batch.add_column(sa.Column("current_research_task_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_agent_conversations_research_task",
            "research_tasks",
            ["current_research_task_id"],
            ["task_id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    if context.is_offline_mode():
        op.drop_column("agent_conversations", "current_research_task_id")
        return
    with op.batch_alter_table("agent_conversations") as batch:
        batch.drop_constraint("fk_agent_conversations_research_task", type_="foreignkey")
        batch.drop_column("current_research_task_id")
