"""Persist Agent provenance for case-comparison candidates."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0003"
down_revision: str | Sequence[str] | None = "20260830_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_analysis_comparisons",
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "research_analysis_comparisons",
        sa.Column("agent_run_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "research_analysis_comparisons",
        sa.Column("agent_turn_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "research_analysis_comparisons",
        sa.Column("tool_call_id", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("research_analysis_comparisons", "tool_call_id")
    op.drop_column("research_analysis_comparisons", "agent_turn_id")
    op.drop_column("research_analysis_comparisons", "agent_run_id")
    op.drop_column("research_analysis_comparisons", "conversation_id")
