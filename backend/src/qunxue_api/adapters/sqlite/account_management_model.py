from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
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


class AccountSystemStateRow(Base):
    __tablename__ = "account_system_state"
    __table_args__ = (
        CheckConstraint("singleton_id = 1", name="ck_account_system_state_singleton"),
        CheckConstraint("lock_version >= 1", name="ck_account_system_state_lock_version"),
    )

    singleton_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    initial_admin_provisioned: Mapped[bool] = mapped_column(Boolean, nullable=False)
    provisioned_admin_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False)


class UserPreferenceRow(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_user_preferences_version"),
    )

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    locale: Mapped[str] = mapped_column(String(16), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    research_updates_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    model_improvement_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    consent_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    consent_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AccountMutationRequestRow(Base):
    __tablename__ = "account_mutation_requests"
    __table_args__ = (
        UniqueConstraint(
            "actor_key",
            "idempotency_key",
            name="uq_account_mutation_actor_key",
        ),
        CheckConstraint(
            "status IN ('processing', 'completed')",
            name="ck_account_mutation_status",
        ),
        Index("ix_account_mutation_created", "created_at"),
    )

    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_key: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    response: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AccountPasswordResetRow(Base):
    __tablename__ = "account_password_resets"
    __table_args__ = (Index("ix_account_password_resets_user", "user_id", "created_at"),)

    reset_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    requested_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PersonalDataExportRow(Base):
    __tablename__ = "personal_data_exports"
    __table_args__ = (
        CheckConstraint("status IN ('ready', 'failed')", name="ck_personal_data_exports_status"),
        CheckConstraint("format = 'json'", name="ck_personal_data_exports_format"),
        Index("ix_personal_data_exports_user_created", "user_id", "created_at"),
    )

    export_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AccountAuditEventRow(Base):
    __tablename__ = "account_audit_events"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('succeeded', 'denied', 'failed')",
            name="ck_account_audit_events_outcome",
        ),
        Index("ix_account_audit_created", "created_at"),
        Index("ix_account_audit_target", "target_user_id", "created_at"),
    )

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    target_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    target_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
