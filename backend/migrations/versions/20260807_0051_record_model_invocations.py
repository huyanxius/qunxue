"""record model invocations

Revision ID: 20260807_0051
Revises: 20260728_0001
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260807_0051"
down_revision: str | Sequence[str] | None = "20260728_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_invocations",
        sa.Column("trace_id", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("contract_version", sa.String(length=64), nullable=False),
        sa.Column("capability", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("capability_tier", sa.String(length=32), nullable=False),
        sa.Column("demonstration", sa.Boolean(), nullable=False),
        sa.Column("scenario", sa.String(length=64), nullable=False),
        sa.Column("input_evidence", sa.JSON(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("knowledge_release_id", sa.String(length=128), nullable=True),
        sa.Column("degraded", sa.Boolean(), nullable=False),
        sa.Column("degradation_reason", sa.String(length=1000), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("trace_id"),
        sa.UniqueConstraint("request_id"),
    )
    op.create_index(
        "ix_model_invocations_task_id",
        "model_invocations",
        ["task_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_model_invocations_task_id", table_name="model_invocations")
    op.drop_table("model_invocations")
