"""Persist course teaching settings and scoped classroom activities."""

import sqlalchemy as sa
from alembic import op

revision = "20260912_0440"
down_revision = "20260908_0430"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "course_teaching_settings",
        sa.Column("course_id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "teaching_activities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("course_id", sa.String(36), nullable=False),
        sa.Column("owner_user_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_teaching_activities_course_id", "teaching_activities", ["course_id"])
    op.create_index(
        "ix_teaching_activities_owner_user_id", "teaching_activities", ["owner_user_id"]
    )


def downgrade():
    op.drop_table("teaching_activities")
    op.drop_table("course_teaching_settings")
