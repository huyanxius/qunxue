"""add research task progress projection

Revision ID: 20260808_0003
Revises: 20260807_0002
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260808_0003"
down_revision: str | Sequence[str] | None = "20260807_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("research_tasks") as batch_op:
        batch_op.add_column(sa.Column("phenomenon_query_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("phenomenon_version", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("phenomenon_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("phenomenon_research_intent", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "adopted_theory_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column("current_phenomenon_candidate_id", sa.String(36), nullable=True)
        )
        batch_op.add_column(sa.Column("current_match_run_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("current_framework_id", sa.String(36), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("research_tasks") as batch_op:
        batch_op.drop_column("current_framework_id")
        batch_op.drop_column("current_match_run_id")
        batch_op.drop_column("current_phenomenon_candidate_id")
        batch_op.drop_column("adopted_theory_count")
        batch_op.drop_column("phenomenon_research_intent")
        batch_op.drop_column("phenomenon_summary")
        batch_op.drop_column("phenomenon_version")
        batch_op.drop_column("phenomenon_query_id")
