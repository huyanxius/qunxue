"""Persist bounded self-service password recovery throttles."""

import sqlalchemy as sa
from alembic import op

revision = "20260928_0460"
down_revision = "20260912_0450"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "password_reset_rate_limits",
        sa.Column("scope_key", sa.String(80), primary_key=True),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer, nullable=False),
        sa.Column("next_allowed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("password_reset_rate_limits")
