"""add one-time credit redemption codes

Revision ID: 20260823_0001
Revises: 20260822_0002
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "20260823_0001"
down_revision: str | Sequence[str] | None = "20260822_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _credit_ledger_table(kind_check: str) -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(
        "credit_ledger",
        metadata,
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
        sa.CheckConstraint(kind_check, name="ck_credit_ledger_kind"),
        sa.CheckConstraint(
            "input_tokens >= 0",
            name="ck_credit_ledger_input_tokens",
        ),
        sa.CheckConstraint(
            "output_tokens >= 0",
            name="ck_credit_ledger_output_tokens",
        ),
        sa.CheckConstraint(
            "balance_after >= 0",
            name="ck_credit_ledger_balance_after",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("entry_id"),
        sa.UniqueConstraint("run_id"),
        sa.Index("ix_credit_ledger_user_created", "user_id", "created_at"),
    )


def _batch_copy_from(source: sa.Table):
    return op.batch_alter_table(
        "credit_ledger",
        copy_from=source if context.is_offline_mode() else None,
    )


def upgrade() -> None:
    with _batch_copy_from(
        _credit_ledger_table("kind IN ('signup_grant', 'usage')")
    ) as batch_op:
        batch_op.drop_constraint("ck_credit_ledger_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_credit_ledger_kind",
            "kind IN ('signup_grant', 'usage', 'redemption')",
        )
    op.create_table(
        "credit_redemption_codes",
        sa.Column("code_id", sa.String(length=36), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("batch_id", sa.String(length=128), nullable=False),
        sa.Column("code_index", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(redeemed_by_user_id IS NULL AND redeemed_at IS NULL) OR "
            "(redeemed_by_user_id IS NOT NULL AND redeemed_at IS NOT NULL)",
            name="ck_credit_redemption_codes_redeemed_pair",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.user_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["redeemed_by_user_id"],
            ["users.user_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("code_id"),
        sa.UniqueConstraint("code_hash", name="uq_credit_redemption_codes_code_hash"),
        sa.UniqueConstraint(
            "created_by_user_id",
            "batch_id",
            "code_index",
            name="uq_credit_redemption_codes_batch_index",
        ),
    )
    op.create_index(
        "ix_credit_redemption_codes_created",
        "credit_redemption_codes",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_credit_redemption_codes_created",
        table_name="credit_redemption_codes",
    )
    op.drop_table("credit_redemption_codes")
    with _batch_copy_from(
        _credit_ledger_table("kind IN ('signup_grant', 'usage', 'redemption')")
    ) as batch_op:
        batch_op.drop_constraint("ck_credit_ledger_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_credit_ledger_kind",
            "kind IN ('signup_grant', 'usage')",
        )
