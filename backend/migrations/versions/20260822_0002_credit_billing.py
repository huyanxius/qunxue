"""add prepaid credits and token usage ledger

Revision ID: 20260822_0002
Revises: 20260822_0001
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_0002"
down_revision: str | Sequence[str] | None = "20260822_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "credit_accounts",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("balance", sa.Integer(), nullable=False),
        sa.Column("active_run_id", sa.String(length=36), nullable=True),
        sa.Column("active_run_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("balance >= 0", name="ck_credit_accounts_balance"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "credit_ledger",
        sa.Column("entry_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('signup_grant', 'usage')", name="ck_credit_ledger_kind"),
        sa.CheckConstraint("input_tokens >= 0", name="ck_credit_ledger_input_tokens"),
        sa.CheckConstraint("output_tokens >= 0", name="ck_credit_ledger_output_tokens"),
        sa.CheckConstraint("balance_after >= 0", name="ck_credit_ledger_balance_after"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("entry_id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index(
        "ix_credit_ledger_user_created",
        "credit_ledger",
        ["user_id", "created_at"],
    )
    op.execute(
        """
        INSERT INTO credit_accounts (
            user_id, balance, active_run_id, active_run_expires_at, created_at, updated_at
        )
        SELECT user_id, 1200, NULL, NULL, created_at, updated_at FROM users
        """
    )
    op.execute(
        """
        INSERT INTO credit_ledger (
            entry_id, user_id, run_id, kind, points, balance_after,
            input_tokens, output_tokens, model, created_at
        )
        SELECT user_id, user_id, NULL, 'signup_grant', 1200, 1200,
               0, 0, NULL, created_at
        FROM users
        """
    )


def downgrade() -> None:
    op.drop_index("ix_credit_ledger_user_created", table_name="credit_ledger")
    op.drop_table("credit_ledger")
    op.drop_table("credit_accounts")
