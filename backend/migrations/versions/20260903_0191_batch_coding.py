"""Persist full-material qualitative coding batches."""

import sqlalchemy as sa
from alembic import op

revision = "20260903_0191"
down_revision = "20260901_0190"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_batch_coding_runs",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("material_id", sa.String(length=36), nullable=False),
        sa.Column("parse_id", sa.String(length=36), nullable=False),
        sa.Column("parse_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("total_segments", sa.Integer(), nullable=False),
        sa.Column("processed_segments", sa.Integer(), nullable=False),
        sa.Column("annotation_ids", sa.JSON(), nullable=False),
        sa.Column("code_ids", sa.JSON(), nullable=False),
        sa.Column("low_confidence_segments", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('queued', 'processing', 'completed', 'failed')", name="ck_research_batch_coding_status"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["research_materials.material_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id"),
        sa.UniqueConstraint("user_id", "task_id", "material_id", "idempotency_key", name="uq_research_batch_coding_idempotency"),
    )
    op.create_index("ix_research_batch_coding_owner_created", "research_batch_coding_runs", ["user_id", "task_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_research_batch_coding_owner_created", table_name="research_batch_coding_runs")
    op.drop_table("research_batch_coding_runs")
