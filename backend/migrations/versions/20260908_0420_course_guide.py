"""Remember dismissal of role-specific course guidance."""

import sqlalchemy as sa
from alembic import op

revision = "20260908_0420"
down_revision = "20260908_0410"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "course_profiles",
        sa.Column("guide_dismissed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("course_profiles", "guide_dismissed")
