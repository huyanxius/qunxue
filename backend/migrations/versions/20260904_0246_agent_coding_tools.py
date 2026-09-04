"""Persist approval-gated Agent coding plans and audit events."""

import sqlalchemy as sa
from alembic import op

revision = "20260904_0246"
down_revision = "20260903_0191"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_analysis_coding_plans",
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("agent_run_id", sa.String(length=36), nullable=True),
        sa.Column("agent_turn_id", sa.String(length=36), nullable=True),
        sa.Column("tool_call_id", sa.String(length=512), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('candidate', 'applied', 'partially_applied', 'rejected', 'revoked')",
            name="ck_research_analysis_coding_plans_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("plan_id"),
    )
    op.create_index(
        "ix_research_analysis_coding_plans_owner_created",
        "research_analysis_coding_plans",
        ["user_id", "task_id", "created_at"],
    )
    op.create_table(
        "research_analysis_audit_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("actor", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("entity_kind", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=True),
        sa.Column("item_id", sa.String(length=36), nullable=True),
        sa.Column("annotation_id", sa.String(length=36), nullable=True),
        sa.Column("code_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=512), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_research_analysis_audit_owner_created",
        "research_analysis_audit_events",
        ["user_id", "task_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_analysis_audit_owner_created", table_name="research_analysis_audit_events"
    )
    op.drop_table("research_analysis_audit_events")
    op.drop_index(
        "ix_research_analysis_coding_plans_owner_created",
        table_name="research_analysis_coding_plans",
    )
    op.drop_table("research_analysis_coding_plans")
