"""persist registration email verifications

Revision ID: 20260823_0002
Revises: 20260823_0001
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260823_0002"
down_revision: str | Sequence[str] | None = "20260823_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "registration_verifications",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("code_hash", sa.String(length=512), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resend_available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts_remaining", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "attempts_remaining >= 0",
            name="ck_registration_verifications_attempts",
        ),
        sa.PrimaryKeyConstraint("email"),
    )


def downgrade() -> None:
    op.drop_table("registration_verifications")
