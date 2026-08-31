"""Add unified research-entry metadata to ResearchTask."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0002"
down_revision: str | Sequence[str] | None = "20260831_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("research_tasks") as batch:
        batch.add_column(
            sa.Column(
                "entry_mode",
                sa.String(32),
                nullable=False,
                server_default="legacy",
            )
        )
        batch.add_column(
            sa.Column(
                "lifecycle_status",
                sa.String(32),
                nullable=False,
                server_default="in_progress",
            )
        )
        batch.add_column(
            sa.Column(
                "project_title",
                sa.String(300),
                nullable=False,
                server_default="未命名研究",
            )
        )
        batch.add_column(sa.Column("project_stage", sa.String(120), nullable=True))
        batch.add_column(sa.Column("method_orientation", sa.String(300), nullable=True))
        batch.add_column(sa.Column("last_central_tool", sa.String(32), nullable=True))

    op.execute(
        """
        UPDATE research_tasks
        SET project_title = COALESCE(
            NULLIF(TRIM(phenomenon_summary), ''),
            NULLIF(TRIM(seed_theory_name), ''),
            '未命名研究'
        )
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("research_tasks") as batch:
        batch.drop_column("last_central_tool")
        batch.drop_column("method_orientation")
        batch.drop_column("project_stage")
        batch.drop_column("project_title")
        batch.drop_column("lifecycle_status")
        batch.drop_column("entry_mode")
