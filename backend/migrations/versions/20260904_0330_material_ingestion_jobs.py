"""Persist recoverable research-material ingestion jobs.

Revision ID: 20260904_0330
Revises: 20260904_0320
"""

import sqlalchemy as sa
from alembic import op

revision = "20260904_0330"
down_revision = "20260904_0320"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_material_ingestion_jobs",
        sa.Column("job_id", sa.String(length=36), primary_key=True),
        sa.Column(
            "material_id",
            sa.String(length=36),
            sa.ForeignKey("research_materials.material_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("parse_id", sa.String(length=36), nullable=False),
        sa.Column("ingestion_status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("material_id", "parse_id", name="uq_material_ingestion_parse"),
    )
    op.create_index(
        "ix_material_ingestion_recovery",
        "research_material_ingestion_jobs",
        ["ingestion_status", "available_at", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_material_ingestion_recovery",
        table_name="research_material_ingestion_jobs",
    )
    op.drop_table("research_material_ingestion_jobs")
