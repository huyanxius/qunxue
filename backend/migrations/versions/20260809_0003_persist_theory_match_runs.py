"""persist theory matching runs and application idempotency

Revision ID: 20260809_0003
Revises: 20260809_0002
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260809_0003"
down_revision: str | Sequence[str] | None = "20260809_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "match_runs",
        sa.Column("match_run_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("model_provider", sa.String(length=128), nullable=True),
        sa.Column("model_version", sa.String(length=128), nullable=True),
        sa.Column("model_capability", sa.String(length=32), nullable=True),
        sa.Column("model_degraded", sa.Boolean(), nullable=True),
        sa.Column("model_knowledge_release_id", sa.String(length=128), nullable=True),
        sa.Column("trace_id", sa.String(length=36), nullable=True),
        sa.Column("request_id", sa.String(length=36), nullable=True),
        sa.Column("contract_version", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["research_tasks.task_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("match_run_id"),
    )
    op.create_index("ix_match_runs_task", "match_runs", ["task_id", "match_run_id"])
    op.create_table(
        "theory_matching_requests",
        sa.Column("request_record_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=72), nullable=False),
        sa.Column("match_run_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["match_run_id"],
            ["match_runs.match_run_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("request_record_id"),
        sa.UniqueConstraint("match_run_id"),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_theory_matching_user_request",
        ),
    )


def downgrade() -> None:
    op.drop_table("theory_matching_requests")
    op.drop_index("ix_match_runs_task", table_name="match_runs")
    op.drop_table("match_runs")
