"""add identity and research task ownership

Revision ID: 20260807_0002
Revises: 20260728_0001
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260807_0002"
down_revision: str | Sequence[str] | None = "20260728_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAMING_CONVENTION = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
_V1_METADATA = sa.MetaData(naming_convention=_NAMING_CONVENTION)
_RESEARCH_TASKS_V1 = sa.Table(
    "research_tasks",
    _V1_METADATA,
    sa.Column("task_id", sa.String(length=36), primary_key=True),
    sa.Column("entry_type", sa.String(length=32), nullable=False),
    sa.Column("status", sa.String(length=32), nullable=False),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("idempotency_key", sa.String(length=128), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("idempotency_key"),
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "user_sessions",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index(
        "ix_user_sessions_token_digest",
        "user_sessions",
        ["token_digest"],
        unique=True,
    )

    with op.batch_alter_table(
        "research_tasks",
        naming_convention=_NAMING_CONVENTION,
        copy_from=_RESEARCH_TASKS_V1,
    ) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.String(length=36), nullable=True))
        batch_op.drop_constraint("uq_research_tasks_idempotency_key", type_="unique")
        batch_op.create_foreign_key(
            "fk_research_tasks_user_id_users",
            "users",
            ["user_id"],
            ["user_id"],
            ondelete="CASCADE",
        )
        batch_op.create_unique_constraint(
            "uq_research_tasks_user_request",
            ["user_id", "idempotency_key"],
        )
        batch_op.create_index(
            "ix_research_tasks_user_updated",
            ["user_id", "updated_at"],
        )


def downgrade() -> None:
    with op.batch_alter_table("research_tasks") as batch_op:
        batch_op.drop_index("ix_research_tasks_user_updated")
        batch_op.drop_constraint("uq_research_tasks_user_request", type_="unique")
        batch_op.drop_constraint("fk_research_tasks_user_id_users", type_="foreignkey")
        batch_op.drop_column("user_id")
        batch_op.create_unique_constraint(
            "uq_research_tasks_idempotency_key",
            ["idempotency_key"],
        )

    op.drop_index("ix_user_sessions_token_digest", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_table("users")
