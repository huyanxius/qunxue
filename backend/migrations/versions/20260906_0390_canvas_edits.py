"""Persist researcher edits without replacing Agent evidence or conversation traces."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_0390"
down_revision = "20260906_0380"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_conversations",
        sa.Column("canvas_edits", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "agent_conversations",
        sa.Column("canvas_edit_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("agent_conversations", "canvas_edit_version")
    op.drop_column("agent_conversations", "canvas_edits")
