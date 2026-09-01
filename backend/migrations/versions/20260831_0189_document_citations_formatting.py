"""Persist research-document formatting profiles.

Revision ID: 20260831_0189
Revises: 20260831_0186
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0189"
down_revision: str | Sequence[str] | None = "20260831_0186"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_FORMATTING = (
    "'{\"template_id\":\"chinese-social-science\","
    "\"csl_style_id\":\"china-national-standard-gb-t-7714-2015-author-date\","
    "\"locale\":\"zh-CN\"}'"
)


def upgrade() -> None:
    op.add_column(
        "research_document_versions",
        sa.Column(
            "formatting",
            sa.JSON(),
            nullable=False,
            server_default=sa.text(DEFAULT_FORMATTING),
        ),
    )


def downgrade() -> None:
    op.drop_column("research_document_versions", "formatting")
