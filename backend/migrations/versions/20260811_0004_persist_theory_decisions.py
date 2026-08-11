"""persist theory decisions and confirmed plans

Revision ID: 20260811_0004
Revises: 20260809_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0004"
down_revision: str | Sequence[str] | None = "20260809_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "theory_decision_sets",
        sa.Column("decision_set_id", sa.String(length=36), nullable=False),
        sa.Column("match_run_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["match_run_id"], ["match_runs.match_run_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("decision_set_id"),
    )
    op.create_index(
        "ix_theory_decision_sets_match",
        "theory_decision_sets",
        ["match_run_id", "recorded_at"],
        unique=False,
    )
    op.create_table(
        "theory_decision_requests",
        sa.Column("request_record_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=72), nullable=False),
        sa.Column("decision_set_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["decision_set_id"],
            ["theory_decision_sets.decision_set_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("request_record_id"),
        sa.UniqueConstraint("decision_set_id"),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_theory_decision_user_request",
        ),
    )
    op.create_table(
        "confirmed_theory_plans",
        sa.Column("theory_plan_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("match_run_id", sa.String(length=36), nullable=False),
        sa.Column("decision_set_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["match_run_id"], ["match_runs.match_run_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["decision_set_id"],
            ["theory_decision_sets.decision_set_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("theory_plan_id"),
        sa.UniqueConstraint("match_run_id"),
        sa.UniqueConstraint("decision_set_id"),
    )
    op.create_table(
        "deferred_theory_plans",
        sa.Column("match_run_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=4000), nullable=False),
        sa.Column("deferred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["match_run_id"], ["match_runs.match_run_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("match_run_id"),
    )


def downgrade() -> None:
    op.drop_table("deferred_theory_plans")
    op.drop_table("confirmed_theory_plans")
    op.drop_table("theory_decision_requests")
    op.drop_index("ix_theory_decision_sets_match", table_name="theory_decision_sets")
    op.drop_table("theory_decision_sets")
