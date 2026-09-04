"""Persist immutable research-material snapshots on Agent runs."""

import sqlalchemy as sa
from alembic import op

revision = "20260904_0310"
down_revision = "20260904_0246"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column(
            "material_attachments",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        )
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "material_attachments")
