from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from qunxue_api.adapters.sqlite.base import Base


class CreditAccountRow(Base):
    __tablename__ = "credit_accounts"
    __table_args__ = (CheckConstraint("balance >= 0", name="ck_credit_accounts_balance"),)

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    balance: Mapped[int] = mapped_column(Integer, nullable=False)
    active_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    active_run_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CreditLedgerRow(Base):
    __tablename__ = "credit_ledger"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('signup_grant', 'usage', 'redemption')",
            name="ck_credit_ledger_kind",
        ),
        CheckConstraint("input_tokens >= 0", name="ck_credit_ledger_input_tokens"),
        CheckConstraint("output_tokens >= 0", name="ck_credit_ledger_output_tokens"),
        CheckConstraint("balance_after >= 0", name="ck_credit_ledger_balance_after"),
        Index("ix_credit_ledger_user_created", "user_id", "created_at"),
    )

    entry_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CreditRedemptionCodeRow(Base):
    __tablename__ = "credit_redemption_codes"
    __table_args__ = (
        CheckConstraint(
            "(redeemed_by_user_id IS NULL AND redeemed_at IS NULL) OR "
            "(redeemed_by_user_id IS NOT NULL AND redeemed_at IS NOT NULL)",
            name="ck_credit_redemption_codes_redeemed_pair",
        ),
        UniqueConstraint(
            "created_by_user_id",
            "batch_id",
            "code_index",
            name="uq_credit_redemption_codes_batch_index",
        ),
        Index("ix_credit_redemption_codes_created", "created_at"),
    )

    code_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    batch_id: Mapped[str] = mapped_column(String(128), nullable=False)
    code_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=True,
    )
    redeemed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
