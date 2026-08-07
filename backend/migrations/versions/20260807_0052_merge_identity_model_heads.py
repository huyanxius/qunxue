"""merge identity and model invocation migration heads

Revision ID: 20260807_0052
Revises: 20260807_0002, 20260807_0051
Create Date: 2026-08-07
"""

from collections.abc import Sequence

revision: str = "20260807_0052"
down_revision: str | Sequence[str] | None = (
    "20260807_0002",
    "20260807_0051",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
