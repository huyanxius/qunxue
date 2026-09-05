"""Keep interrupted Agent requests and fence worker leases."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_0380"
down_revision = "20260905_0370"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_runs", sa.Column("request_snapshot", sa.JSON(), nullable=False, server_default="{}")
    )
    op.add_column(
        "agent_runs", sa.Column("partial_answer", sa.Text(), nullable=False, server_default="")
    )
    op.add_column("agent_runs", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "agent_runs",
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "agent_runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("agent_runs", sa.Column("lease_token", sa.String(36), nullable=True))
    op.execute("UPDATE agent_runs SET updated_at = COALESCE(completed_at, started_at)")


def downgrade():
    for name in (
        "lease_token",
        "lease_expires_at",
        "cancel_requested",
        "updated_at",
        "partial_answer",
        "request_snapshot",
    ):
        op.drop_column("agent_runs", name)
