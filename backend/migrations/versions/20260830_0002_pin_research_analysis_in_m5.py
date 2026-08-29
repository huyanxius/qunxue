"""Pin confirmed qualitative analysis to each M5 document version."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0002"
down_revision: str | Sequence[str] | None = "20260830_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_document_versions",
        sa.Column("analysis_handoff", sa.JSON(), nullable=True),
    )
    op.add_column(
        "research_document_proposals",
        sa.Column("analysis_handoff", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("research_document_proposals", "analysis_handoff")
    op.drop_column("research_document_versions", "analysis_handoff")
