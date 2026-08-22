"""add account settings, lifecycle, and administrator storage

Revision ID: 20260822_0001
Revises: 20260820_0005
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_0001"
down_revision: str | Sequence[str] | None = "20260820_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(length=16), nullable=True))
    op.add_column("users", sa.Column("status", sa.String(length=16), nullable=True))
    op.add_column("users", sa.Column("version", sa.Integer(), nullable=True))
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE users
        SET role = 'member',
            status = 'active',
            version = 1,
            last_login_at = created_at
        """
    )
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("role", existing_type=sa.String(length=16), nullable=False)
        batch_op.alter_column("status", existing_type=sa.String(length=16), nullable=False)
        batch_op.alter_column("version", existing_type=sa.Integer(), nullable=False)
        batch_op.create_check_constraint("ck_users_role", "role IN ('member', 'admin')")
        batch_op.create_check_constraint(
            "ck_users_status",
            "status IN ('active', 'disabled', 'deactivated')",
        )
        batch_op.create_check_constraint("ck_users_version", "version >= 1")
        batch_op.create_index("ix_users_role_status", ["role", "status"])

    op.add_column(
        "user_sessions",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_sessions",
        sa.Column("user_agent", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "user_sessions",
        sa.Column("ip_address", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "user_sessions",
        sa.Column("revoked_reason", sa.String(length=64), nullable=True),
    )
    op.execute("UPDATE user_sessions SET last_seen_at = created_at")

    op.create_table(
        "account_system_state",
        sa.Column("singleton_id", sa.Integer(), nullable=False),
        sa.Column("initial_admin_provisioned", sa.Boolean(), nullable=False),
        sa.Column("provisioned_admin_user_id", sa.String(length=36), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.CheckConstraint("singleton_id = 1", name="ck_account_system_state_singleton"),
        sa.CheckConstraint("lock_version >= 1", name="ck_account_system_state_lock_version"),
        sa.ForeignKeyConstraint(
            ["provisioned_admin_user_id"],
            ["users.user_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("singleton_id"),
    )
    op.execute(
        """
        INSERT INTO account_system_state (
            singleton_id, initial_admin_provisioned,
            provisioned_admin_user_id, lock_version
        )
        VALUES (1, 0, NULL, 1)
        """
    )

    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("research_updates_enabled", sa.Boolean(), nullable=False),
        sa.Column("model_improvement_allowed", sa.Boolean(), nullable=False),
        sa.Column("consent_policy_version", sa.String(length=64), nullable=False),
        sa.Column("consent_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_user_preferences_version"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.execute(
        """
        INSERT INTO user_preferences (
            user_id, locale, timezone, research_updates_enabled,
            model_improvement_allowed, consent_policy_version,
            consent_updated_at, version, updated_at
        )
        SELECT user_id, 'zh-CN', 'Asia/Shanghai', 1,
               0, '2026-08-secondary-use-v1', NULL, 1, updated_at
        FROM users
        """
    )

    op.create_table(
        "account_mutation_requests",
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("actor_key", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("response", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('processing', 'completed')",
            name="ck_account_mutation_status",
        ),
        sa.PrimaryKeyConstraint("request_id"),
        sa.UniqueConstraint(
            "actor_key",
            "idempotency_key",
            name="uq_account_mutation_actor_key",
        ),
    )
    op.create_index(
        "ix_account_mutation_created",
        "account_mutation_requests",
        ["created_at"],
    )

    op.create_table(
        "account_password_resets",
        sa.Column("reset_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.user_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("reset_id"),
        sa.UniqueConstraint("token_digest"),
    )
    op.create_index(
        "ix_account_password_resets_user",
        "account_password_resets",
        ["user_id", "created_at"],
    )

    op.create_table(
        "personal_data_exports",
        sa.Column("export_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('ready', 'failed')",
            name="ck_personal_data_exports_status",
        ),
        sa.CheckConstraint("format = 'json'", name="ck_personal_data_exports_format"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("export_id"),
    )
    op.create_index(
        "ix_personal_data_exports_user_created",
        "personal_data_exports",
        ["user_id", "created_at"],
    )

    op.create_table(
        "account_audit_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("target_user_id", sa.String(length=36), nullable=True),
        sa.Column("actor_email", sa.String(length=320), nullable=True),
        sa.Column("target_email", sa.String(length=320), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('succeeded', 'denied', 'failed')",
            name="ck_account_audit_events_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.user_id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"],
            ["users.user_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_account_audit_created", "account_audit_events", ["created_at"])
    op.create_index(
        "ix_account_audit_target",
        "account_audit_events",
        ["target_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_account_audit_target", table_name="account_audit_events")
    op.drop_index("ix_account_audit_created", table_name="account_audit_events")
    op.drop_table("account_audit_events")
    op.drop_index(
        "ix_personal_data_exports_user_created",
        table_name="personal_data_exports",
    )
    op.drop_table("personal_data_exports")
    op.drop_index(
        "ix_account_password_resets_user",
        table_name="account_password_resets",
    )
    op.drop_table("account_password_resets")
    op.drop_index("ix_account_mutation_created", table_name="account_mutation_requests")
    op.drop_table("account_mutation_requests")
    op.drop_table("user_preferences")
    op.drop_table("account_system_state")

    with op.batch_alter_table("user_sessions") as batch_op:
        batch_op.drop_column("revoked_reason")
        batch_op.drop_column("ip_address")
        batch_op.drop_column("user_agent")
        batch_op.drop_column("last_seen_at")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_role_status")
        batch_op.drop_constraint("ck_users_version", type_="check")
        batch_op.drop_constraint("ck_users_status", type_="check")
        batch_op.drop_constraint("ck_users_role", type_="check")
        batch_op.drop_column("deactivated_at")
        batch_op.drop_column("last_login_at")
        batch_op.drop_column("version")
        batch_op.drop_column("status")
        batch_op.drop_column("role")
