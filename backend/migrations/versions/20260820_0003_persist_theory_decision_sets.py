"""persist user theory decisions for the M4 to M5 handoff"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260820_0003"
down_revision: str | Sequence[str] | None = "20260818_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_tasks",
        sa.Column("current_theory_plan_id", sa.String(length=36), nullable=True),
    )
    op.create_table(
        "theory_decision_sets",
        sa.Column("decision_set_id", sa.String(length=36), nullable=False),
        sa.Column("match_run_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("request_hash", sa.String(length=72), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["match_run_id"], ["match_runs.match_run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("decision_set_id"),
        sa.UniqueConstraint("match_run_id", name="uq_theory_decision_sets_match_run"),
    )
    op.create_table(
        "confirmed_theory_plans",
        sa.Column("theory_plan_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("match_run_id", sa.String(length=36), nullable=False),
        sa.Column("decision_set_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("adopted_candidate_ids", sa.JSON(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("request_hash", sa.String(length=72), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["match_run_id"], ["match_runs.match_run_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["decision_set_id"],
            ["theory_decision_sets.decision_set_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("theory_plan_id"),
        sa.UniqueConstraint("decision_set_id"),
    )
    op.create_index(
        "ix_confirmed_theory_plans_task_id",
        "confirmed_theory_plans",
        ["task_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_confirmed_theory_plans_task_id", table_name="confirmed_theory_plans")
    op.drop_table("confirmed_theory_plans")
    op.drop_table("theory_decision_sets")
    op.drop_column("research_tasks", "current_theory_plan_id")
