"""Persist course role and recoverable organization/index jobs."""

import sqlalchemy as sa
from alembic import op

revision = "20260908_0410"
down_revision = "20260908_0400"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "course_profiles",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.user_id"), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
    )
    for stage in ("knowledge", "index"):
        op.add_column(
            "shared_documents",
            sa.Column(f"{stage}_status", sa.String(16), nullable=False, server_default="queued"),
        )
        op.add_column("shared_documents", sa.Column(f"{stage}_error", sa.Text()))
    op.add_column("shared_documents", sa.Column("knowledge", sa.JSON()))
    op.add_column("shared_documents", sa.Column("job_token", sa.String(36)))
    op.add_column("shared_documents", sa.Column("job_started_at", sa.DateTime(timezone=True)))


def downgrade():
    for name in (
        "job_started_at",
        "job_token",
        "knowledge",
        "index_error",
        "index_status",
        "knowledge_error",
        "knowledge_status",
    ):
        op.drop_column("shared_documents", name)
    op.drop_table("course_profiles")
