"""Persist approval-gated, versioned research method plans."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0001"
down_revision: str | Sequence[str] | None = "20260830_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("research_tasks", sa.Column("current_method_plan_id", sa.String(length=36), nullable=True))
    op.add_column(
        "research_tasks",
        sa.Column("current_method_plan_status", sa.String(length=32), nullable=True),
    )
    op.create_table(
        "research_method_plan_identities",
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id"),
        sa.UniqueConstraint("plan_id"),
    )
    op.create_table(
        "research_method_plan_versions",
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("framework_id", sa.String(length=36), nullable=False),
        sa.Column("framework_version", sa.Integer(), nullable=False),
        sa.Column("theory_plan_id", sa.String(length=36), nullable=False),
        sa.Column("theory_plan_version", sa.Integer(), nullable=False),
        sa.Column("method_kind", sa.String(length=32), nullable=False),
        sa.Column("decision_source", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("research_question", sa.Text(), nullable=False),
        sa.Column("theory_summary", sa.Text(), nullable=False),
        sa.Column("material_constraints", sa.JSON(), nullable=False),
        sa.Column("ethical_constraints", sa.JSON(), nullable=False),
        sa.Column("theory_concepts", sa.JSON(), nullable=False),
        sa.Column("evidence_ref_ids", sa.JSON(), nullable=False),
        sa.Column("knowledge_release_id", sa.String(length=128), nullable=True),
        sa.Column("shared_context", sa.JSON(), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("reviews", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("restored_from_version", sa.Integer(), nullable=True),
        sa.Column("stale_reason", sa.Text(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("plan_id", "version"),
        sa.UniqueConstraint("revision_id"),
    )
    op.create_index(
        "ix_research_method_plan_versions_task",
        "research_method_plan_versions",
        ["task_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_column("research_tasks", "current_method_plan_status")
    op.drop_column("research_tasks", "current_method_plan_id")
    op.drop_index("ix_research_method_plan_versions_task", table_name="research_method_plan_versions")
    op.drop_table("research_method_plan_versions")
    op.drop_table("research_method_plan_identities")
