"""persist immutable research document versions"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260820_0004"
down_revision: str | Sequence[str] | None = "20260820_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_document_versions",
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("theory_plan_id", sa.String(length=36), nullable=False),
        sa.Column("knowledge_release_id", sa.String(length=128), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("restored_from_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["theory_plan_id"],
            ["confirmed_theory_plans.theory_plan_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("document_id", "version"),
        sa.UniqueConstraint("revision_id"),
    )
    op.create_index(
        "ix_research_document_versions_task",
        "research_document_versions",
        ["task_id", "document_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_document_versions_task",
        table_name="research_document_versions",
    )
    op.drop_table("research_document_versions")
