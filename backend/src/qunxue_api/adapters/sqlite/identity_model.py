from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from qunxue_api.adapters.sqlite.base import Base


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('member', 'admin')", name="ck_users_role"),
        CheckConstraint(
            "status IN ('active', 'disabled', 'deactivated')",
            name="ck_users_status",
        ),
        CheckConstraint("version >= 1", name="ck_users_version"),
        Index("ix_users_role_status", "role", "status"),
    )

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="member")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserSessionRow(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (Index("ix_user_sessions_token_digest", "token_digest", unique=True),)

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)


class RegistrationVerificationRow(Base):
    __tablename__ = "registration_verifications"
    __table_args__ = (
        CheckConstraint("attempts_remaining >= 0", name="ck_registration_verifications_attempts"),
    )

    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resend_available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts_remaining: Mapped[int] = mapped_column(Integer, nullable=False)
