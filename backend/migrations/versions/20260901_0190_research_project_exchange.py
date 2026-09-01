"""Persist research-project exchange runs and append-only audit events."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0190"
down_revision: str | Sequence[str] | None = "20260901_0188"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_project_exchange_runs",
        sa.Column("exchange_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("format", sa.String(length=64), nullable=False),
        sa.Column("format_version", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column("loss_report", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "direction IN ('import', 'export')",
            name="ck_research_project_exchange_direction",
        ),
        sa.CheckConstraint(
            "status IN ('processing', 'completed', 'failed')",
            name="ck_research_project_exchange_status",
        ),
        sa.PrimaryKeyConstraint("exchange_id"),
        sa.UniqueConstraint(
            "user_id",
            "task_id",
            "direction",
            "idempotency_key",
            name="uq_research_project_exchange_idempotency",
        ),
    )
    op.create_index(
        "ix_research_project_exchange_task_created",
        "research_project_exchange_runs",
        ["user_id", "task_id", "created_at"],
    )
    op.create_table(
        "research_project_audit_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("object_id", sa.String(length=512), nullable=False),
        sa.Column("object_version", sa.String(length=128), nullable=True),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.String(length=512), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "actor_type IN ('user', 'agent', 'system')",
            name="ck_research_project_audit_actor_type",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_research_project_audit_task_occurred",
        "research_project_audit_events",
        ["user_id", "task_id", "occurred_at"],
    )
    op.create_index(
        "ix_research_project_audit_object",
        "research_project_audit_events",
        ["object_type", "object_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_project_audit_object",
        table_name="research_project_audit_events",
    )
    op.drop_index(
        "ix_research_project_audit_task_occurred",
        table_name="research_project_audit_events",
    )
    op.drop_table("research_project_audit_events")
    op.drop_index(
        "ix_research_project_exchange_task_created",
        table_name="research_project_exchange_runs",
    )
    op.drop_table("research_project_exchange_runs")
