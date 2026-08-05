"""create research tasks

Revision ID: 20260728_0001
Revises:
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_tasks",
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("phenomenon", sa.String(), nullable=False),
        sa.Column("research_intent", sa.String(), nullable=True),
        sa.Column("context", sa.String(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("task_id"),
    )


def downgrade() -> None:
    op.drop_table("research_tasks")
