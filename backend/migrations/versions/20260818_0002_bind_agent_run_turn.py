"""bind completed Agent runs to their persisted turn

Revision ID: 20260818_0002
Revises: 20260818_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_0002"
down_revision: str | Sequence[str] | None = "20260818_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("turn_id", sa.String(length=36), nullable=True),
    )
    op.create_index("ix_agent_runs_turn_id", "agent_runs", ["turn_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_runs_turn_id", table_name="agent_runs")
    op.drop_column("agent_runs", "turn_id")
