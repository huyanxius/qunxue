"""persist research cycle projections

Revision ID: 20260901_0188
Revises: 20260831_0189
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0188"
down_revision: str | None = "20260831_0189"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_cycle_snapshots",
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=72), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "version"),
        sa.UniqueConstraint(
            "task_id", "content_hash", name="uq_research_cycle_task_content"
        ),
    )
    op.create_index(
        "ix_research_cycle_task_version",
        "research_cycle_snapshots",
        ["task_id", "version"],
    )


def downgrade() -> None:
    op.drop_index("ix_research_cycle_task_version", table_name="research_cycle_snapshots")
    op.drop_table("research_cycle_snapshots")
