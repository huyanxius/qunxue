import json
from base64 import urlsafe_b64encode
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from hmac import new as hmac_new
from typing import TypeVar
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from qunxue_api.modules.account_management.domain import (
    SECONDARY_USE_POLICY_VERSION,
    ModelSecondaryUseAuthorization,
)
from qunxue_api.modules.account_management.errors import (
    AccountCapabilityUnavailable,
    AccountForbidden,
    AccountNotFound,
    InvalidConfirmation,
    InvalidCurrentPassword,
    LastAdministratorProtected,
    ProvisionedAdministratorProtected,
    StaleAccountVersion,
)
from qunxue_api.modules.account_management.ports import AccountRepository, PasswordHasher

_SENSITIVE_FIELDS = frozenset({"password", "current_password", "new_password", "token"})
_T = TypeVar("_T", bound=dict[str, object])


class AccountManagementService:
    def __init__(
        self,
        repository: AccountRepository,
        password_hasher: PasswordHasher,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], UUID] = uuid4,
        password_reset_signing_secret: str | None = None,
    ) -> None:
        self._repository = repository
        self._password_hasher = password_hasher
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory
        self._password_reset_signing_secret = (
            password_reset_signing_secret.encode("utf-8")
            if password_reset_signing_secret
            else None
        )

    def get_account(self, user_id: UUID) -> dict[str, object]:
        account = self._repository.get_account(user_id)
        if account is None:
            raise AccountNotFound
        return account

    def update_profile(
        self,
        *,
        user_id: UUID,
        display_name: str,
        expected_version: int,
        idempotency_key: str,
    ) -> dict[str, object]:
        normalized = display_name.strip() or None
        return self._mutate(
            actor_key=str(user_id),
            idempotency_key=idempotency_key,
            operation="account.profile.update",
            payload={"display_name": normalized, "expected_version": expected_version},
            action=lambda now: self._update_profile(
                user_id=user_id,
                display_name=normalized,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
                now=now,
            ),
        )

    def _update_profile(
        self,
        *,
        user_id: UUID,
        display_name: str | None,
        expected_version: int,
        idempotency_key: str,
        now: datetime,
    ) -> dict[str, object]:
        updated = self._repository.update_profile(
            user_id=user_id,
            display_name=display_name,
            expected_version=expected_version,
            now=now,
        )
        if updated is None:
            raise StaleAccountVersion
        self._audit(
            actor_user_id=user_id,
            target_user_id=user_id,
            action="profile.updated",
            details={"idempotency_key": idempotency_key},
            now=now,
        )
        return updated

    def update_preferences(
        self,
        *,
        user_id: UUID,
        locale: str,
        timezone: str,
        research_updates_enabled: bool,
        expected_version: int,
        idempotency_key: str,
    ) -> dict[str, object]:
        normalized_locale = locale.strip()
        normalized_timezone = timezone.strip()
        if normalized_locale not in {"zh-CN", "en-US"}:
            raise InvalidConfirmation("暂不支持该界面语言。")
        try:
            ZoneInfo(normalized_timezone)
        except ZoneInfoNotFoundError as error:
            raise InvalidConfirmation("请输入有效的 IANA 时区。") from error
        values: dict[str, object] = {
            "locale": normalized_locale,
            "timezone": normalized_timezone,
            "research_updates_enabled": research_updates_enabled,
        }
        return self._mutate(
            actor_key=str(user_id),
            idempotency_key=idempotency_key,
            operation="account.preferences.update",
            payload={**values, "expected_version": expected_version},
            action=lambda now: self._update_preferences(
                user_id=user_id,
                values=values,
                expected_version=expected_version,
                action="preferences.updated",
                idempotency_key=idempotency_key,
                now=now,
            ),
        )

    def update_model_data_authorization(
        self,
        *,
        user_id: UUID,
        allowed: bool,
        policy_version: str,
        expected_version: int,
        idempotency_key: str,
    ) -> dict[str, object]:
        if policy_version != SECONDARY_USE_POLICY_VERSION:
            raise InvalidConfirmation("授权说明已更新，请刷新后重新确认。")
        values: dict[str, object] = {
            "model_improvement_allowed": allowed,
            "consent_policy_version": policy_version,
            "consent_updated_at": self._clock(),
        }
        return self._mutate(
            actor_key=str(user_id),
            idempotency_key=idempotency_key,
            operation="account.model_secondary_use.update",
            payload={
                "allowed": allowed,
                "policy_version": policy_version,
                "expected_version": expected_version,
            },
            action=lambda now: self._update_preferences(
                user_id=user_id,
                values={**values, "consent_updated_at": now},
                expected_version=expected_version,
                action=(
                    "model_secondary_use.granted"
                    if allowed
                    else "model_secondary_use.withdrawn"
                ),
                idempotency_key=idempotency_key,
                now=now,
            ),
        )

    def _update_preferences(
        self,
        *,
        user_id: UUID,
        values: dict[str, object],
        expected_version: int,
        action: str,
        idempotency_key: str,
        now: datetime,
    ) -> dict[str, object]:
        updated = self._repository.update_preferences(
            user_id=user_id,
            values=values,
            expected_version=expected_version,
            now=now,
        )
        if updated is None:
            raise StaleAccountVersion
        self._audit(
            actor_user_id=user_id,
            target_user_id=user_id,
            action=action,
            details={"idempotency_key": idempotency_key},
            now=now,
        )
        return updated

    def model_secondary_use_authorization(
        self,
        user_id: UUID,
    ) -> ModelSecondaryUseAuthorization:
        return self._repository.model_secondary_use_authorization(user_id)

    def list_sessions(
        self,
        *,
        user_id: UUID,
        current_session_id: UUID,
    ) -> list[dict[str, object]]:
        return self._repository.list_sessions(
            user_id=user_id,
            current_session_id=current_session_id,
            now=self._clock(),
        )

    def revoke_session(
        self,
        *,
        user_id: UUID,
        current_session_id: UUID,
        session_id: UUID,
        idempotency_key: str,
    ) -> dict[str, object]:
        return self._mutate(
            actor_key=str(user_id),
            idempotency_key=idempotency_key,
            operation="account.session.revoke",
            payload={"session_id": str(session_id)},
            action=lambda now: self._revoke_session(
                user_id=user_id,
                current_session_id=current_session_id,
                session_id=session_id,
                idempotency_key=idempotency_key,
                now=now,
            ),
        )

    def _revoke_session(
        self,
        *,
        user_id: UUID,
        current_session_id: UUID,
        session_id: UUID,
        idempotency_key: str,
        now: datetime,
    ) -> dict[str, object]:
        revoked = self._repository.revoke_session(
            user_id=user_id,
            session_id=session_id,
            current_session_id=current_session_id,
            now=now,
            reason="user_revoked",
        )
        if not revoked:
            raise AccountNotFound
        self._audit(
            actor_user_id=user_id,
            target_user_id=user_id,
            action="session.revoked",
            details={"session_id": str(session_id), "idempotency_key": idempotency_key},
            now=now,
        )
        return {"session_id": str(session_id), "revoked": True}

    def change_password(
        self,
        *,
        user_id: UUID,
        current_session_id: UUID,
        current_password: str,
        new_password: str,
        revoke_other_sessions: bool,
        idempotency_key: str,
    ) -> dict[str, object]:
        return self._mutate(
            actor_key=str(user_id),
            idempotency_key=idempotency_key,
            operation="account.password.change",
            payload={
                "current_password": current_password,
                "new_password": new_password,
                "revoke_other_sessions": revoke_other_sessions,
            },
            action=lambda now: self._change_password(
                user_id=user_id,
                current_session_id=current_session_id,
                current_password=current_password,
                new_password=new_password,
                revoke_other_sessions=revoke_other_sessions,
                idempotency_key=idempotency_key,
                now=now,
            ),
        )

    def _change_password(
        self,
        *,
        user_id: UUID,
        current_session_id: UUID,
        current_password: str,
        new_password: str,
        revoke_other_sessions: bool,
        idempotency_key: str,
        now: datetime,
    ) -> dict[str, object]:
        stored = self._repository.get_password_hash(user_id)
        if stored is None or not self._password_hasher.verify(stored, current_password):
            raise InvalidCurrentPassword().with_denied_audit(
                action="password.change",
                actor_user_id=user_id,
                target_user_id=user_id,
                details={"reason": "current_password_mismatch"},
            )
        if self._password_hasher.verify(stored, new_password):
            raise InvalidConfirmation("新密码不能与当前密码相同。")
        revoked = self._repository.change_password(
            user_id=user_id,
            password_hash=self._password_hasher.hash(new_password),
            current_session_id=current_session_id,
            revoke_other_sessions=revoke_other_sessions,
            now=now,
        )
        self._audit(
            actor_user_id=user_id,
            target_user_id=user_id,
            action="password.changed",
            details={
                "revoked_session_count": revoked,
                "idempotency_key": idempotency_key,
            },
            now=now,
        )
        return {"revoked_session_count": revoked}

    def list_users(
        self,
        *,
        actor_user_id: UUID,
        query: str | None,
        role: str | None,
        account_status: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, object]:
        self._require_admin(actor_user_id)
        items, total = self._repository.list_users(
            query=query.strip() if query else None,
            role=role,
            status=account_status,
            offset=offset,
            limit=limit,
            current_user_id=actor_user_id,
        )
        return {
            "items": items,
            "total": total,
            "next_cursor": str(offset + limit) if offset + limit < total else None,
        }

    def update_user_role(
        self,
        *,
        actor_user_id: UUID,
        user_id: UUID,
        role: str,
        expected_version: int,
        reason: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        self._require_admin(actor_user_id)
        return self._mutate(
            actor_key=str(actor_user_id),
            idempotency_key=idempotency_key,
            operation="admin.user.role.update",
            payload={
                "user_id": str(user_id),
                "role": role,
                "expected_version": expected_version,
                "reason": reason,
            },
            action=lambda now: self._update_user_role(
                actor_user_id=actor_user_id,
                user_id=user_id,
                role=role,
                expected_version=expected_version,
                reason=reason,
                idempotency_key=idempotency_key,
                now=now,
            ),
        )

    def _update_user_role(
        self,
        *,
        actor_user_id: UUID,
        user_id: UUID,
        role: str,
        expected_version: int,
        reason: str,
        idempotency_key: str,
        now: datetime,
    ) -> dict[str, object]:
        target = self.get_account(user_id)
        if role != "admin" and self._repository.is_provisioned_admin(user_id):
            raise ProvisionedAdministratorProtected().with_denied_audit(
                action="user.role_changed",
                actor_user_id=actor_user_id,
                target_user_id=user_id,
                details={
                    "reason": "provisioned_administrator",
                    "requested_role": role,
                },
            )
        if (
            target["role"] == "admin"
            and role != "admin"
            and target["status"] == "active"
            and self._repository.count_active_admins() <= 1
        ):
            raise LastAdministratorProtected().with_denied_audit(
                action="user.role_changed",
                actor_user_id=actor_user_id,
                target_user_id=user_id,
                details={"reason": "last_active_administrator", "requested_role": role},
            )
        updated = self._repository.update_user_role(
            user_id=user_id,
            role=role,
            expected_version=expected_version,
            now=now,
        )
        if updated is None:
            raise StaleAccountVersion
        self._audit(
            actor_user_id=actor_user_id,
            target_user_id=user_id,
            action="user.role_changed",
            details={"role": role, "reason": reason, "idempotency_key": idempotency_key},
            now=now,
        )
        return updated

    def update_user_status(
        self,
        *,
        actor_user_id: UUID,
        user_id: UUID,
        account_status: str,
        expected_version: int,
        reason: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        self._require_admin(actor_user_id)
        return self._mutate(
            actor_key=str(actor_user_id),
            idempotency_key=idempotency_key,
            operation=f"admin.user.{account_status}",
            payload={
                "user_id": str(user_id),
                "status": account_status,
                "expected_version": expected_version,
                "reason": reason,
            },
            action=lambda now: self._update_user_status(
                actor_user_id=actor_user_id,
                user_id=user_id,
                account_status=account_status,
                expected_version=expected_version,
                reason=reason,
                idempotency_key=idempotency_key,
                now=now,
            ),
        )

    def _update_user_status(
        self,
        *,
        actor_user_id: UUID,
        user_id: UUID,
        account_status: str,
        expected_version: int,
        reason: str,
        idempotency_key: str,
        now: datetime,
    ) -> dict[str, object]:
        target = self.get_account(user_id)
        if account_status != "active" and self._repository.is_provisioned_admin(user_id):
            raise ProvisionedAdministratorProtected().with_denied_audit(
                action="user.disabled",
                actor_user_id=actor_user_id,
                target_user_id=user_id,
                details={
                    "reason": "provisioned_administrator",
                    "requested_status": account_status,
                },
            )
        if (
            target["role"] == "admin"
            and target["status"] == "active"
            and account_status != "active"
            and self._repository.count_active_admins() <= 1
        ):
            raise LastAdministratorProtected().with_denied_audit(
                action="user.enabled" if account_status == "active" else "user.disabled",
                actor_user_id=actor_user_id,
                target_user_id=user_id,
                details={
                    "reason": "last_active_administrator",
                    "requested_status": account_status,
                },
            )
        updated = self._repository.update_user_status(
            user_id=user_id,
            status=account_status,
            expected_version=expected_version,
            now=now,
            reason=reason,
        )
        if updated is None:
            raise StaleAccountVersion
        action = "user.enabled" if account_status == "active" else "user.disabled"
        self._audit(
            actor_user_id=actor_user_id,
            target_user_id=user_id,
            action=action,
            details={"reason": reason, "idempotency_key": idempotency_key},
            now=now,
        )
        return updated

    def create_password_reset(
        self,
        *,
        actor_user_id: UUID,
        user_id: UUID,
        idempotency_key: str,
    ) -> dict[str, object]:
        self._require_admin(actor_user_id)
        token = self._password_reset_token(
            actor_user_id=actor_user_id,
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        result = self._mutate(
            actor_key=str(actor_user_id),
            idempotency_key=idempotency_key,
            operation="admin.password_reset.issue",
            payload={"user_id": str(user_id)},
            action=lambda now: self._create_password_reset(
                actor_user_id=actor_user_id,
                user_id=user_id,
                token=token,
                idempotency_key=idempotency_key,
                now=now,
            ),
            sanitize_for_storage=lambda result: {**result, "reset_token": None},
        )
        return {**result, "reset_token": token}

    def _create_password_reset(
        self,
        *,
        actor_user_id: UUID,
        user_id: UUID,
        token: str,
        idempotency_key: str,
        now: datetime,
    ) -> dict[str, object]:
        self.get_account(user_id)
        result = self._repository.create_password_reset(
            reset_id=self._id_factory(),
            user_id=user_id,
            token_digest=self._digest(token),
            requested_by_user_id=actor_user_id,
            now=now,
            expires_at=now + timedelta(hours=1),
        )
        self._audit(
            actor_user_id=actor_user_id,
            target_user_id=user_id,
            action="password_reset.issued",
            details={"idempotency_key": idempotency_key},
            now=now,
        )
        return {**result, "reset_token": token}

    def consume_password_reset(
        self,
        *,
        token: str,
        new_password: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        digest = self._digest(token)
        return self._mutate(
            actor_key=f"password-reset:{digest}",
            idempotency_key=idempotency_key,
            operation="account.password_reset.consume",
            payload={"token": token, "new_password": new_password},
            action=lambda now: self._consume_password_reset(
                token_digest=digest,
                new_password=new_password,
                idempotency_key=idempotency_key,
                now=now,
            ),
        )

    def _consume_password_reset(
        self,
        *,
        token_digest: str,
        new_password: str,
        idempotency_key: str,
        now: datetime,
    ) -> dict[str, object]:
        user_id = self._repository.consume_password_reset(
            token_digest=token_digest,
            password_hash=self._password_hasher.hash(new_password),
            now=now,
        )
        self._audit(
            actor_user_id=user_id,
            target_user_id=user_id,
            action="password_reset.consumed",
            details={"idempotency_key": idempotency_key},
            now=now,
        )
        return {"password_reset": True}

    def create_export(
        self,
        *,
        user_id: UUID,
        idempotency_key: str,
    ) -> dict[str, object]:
        return self._mutate(
            actor_key=str(user_id),
            idempotency_key=idempotency_key,
            operation="account.data_export.create",
            payload={"format": "json"},
            action=lambda now: self._create_export(
                user_id=user_id,
                idempotency_key=idempotency_key,
                now=now,
            ),
        )

    def _create_export(
        self,
        *,
        user_id: UUID,
        idempotency_key: str,
        now: datetime,
    ) -> dict[str, object]:
        result = self._repository.create_export(
            export_id=self._id_factory(),
            user_id=user_id,
            now=now,
            expires_at=now + timedelta(days=7),
        )
        self._audit(
            actor_user_id=user_id,
            target_user_id=user_id,
            action="data_export.created",
            details={"idempotency_key": idempotency_key},
            now=now,
        )
        return result

    def get_export(self, *, user_id: UUID, export_id: UUID) -> dict[str, object]:
        result = self._repository.get_export(export_id=export_id, user_id=user_id)
        if result is None:
            raise AccountNotFound
        return result

    def get_export_payload(self, *, user_id: UUID, export_id: UUID) -> dict[str, object]:
        result = self._repository.get_export_payload(export_id=export_id, user_id=user_id)
        if result is None:
            raise AccountNotFound
        return result

    def deactivate_account(
        self,
        *,
        user_id: UUID,
        current_password: str,
        reason: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        return self._mutate(
            actor_key=str(user_id),
            idempotency_key=idempotency_key,
            operation="account.deactivate",
            payload={"current_password": current_password, "reason": reason},
            action=lambda now: self._deactivate_account(
                user_id=user_id,
                current_password=current_password,
                reason=reason,
                idempotency_key=idempotency_key,
                now=now,
            ),
        )

    def _deactivate_account(
        self,
        *,
        user_id: UUID,
        current_password: str,
        reason: str,
        idempotency_key: str,
        now: datetime,
    ) -> dict[str, object]:
        self._verify_password(
            user_id,
            current_password,
            action="account.deactivated",
            details={"reason": "current_password_mismatch"},
        )
        target = self.get_account(user_id)
        if self._repository.is_provisioned_admin(user_id):
            raise ProvisionedAdministratorProtected().with_denied_audit(
                action="account.deactivated",
                actor_user_id=user_id,
                target_user_id=user_id,
                details={"reason": "provisioned_administrator"},
            )
        if target["role"] == "admin" and self._repository.count_active_admins() <= 1:
            raise LastAdministratorProtected().with_denied_audit(
                action="account.deactivated",
                actor_user_id=user_id,
                target_user_id=user_id,
                details={"reason": "last_active_administrator"},
            )
        self._audit(
            actor_user_id=user_id,
            target_user_id=user_id,
            action="account.deactivated",
            details={"reason": reason, "idempotency_key": idempotency_key},
            now=now,
        )
        self._repository.deactivate_account(user_id=user_id, now=now, reason=reason)
        return {"recoverable": True, "recovery": "contact_an_administrator"}

    def delete_account(
        self,
        *,
        user_id: UUID,
        current_password: str,
        confirmation_email: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        return self._mutate(
            actor_key=str(user_id),
            idempotency_key=idempotency_key,
            operation="account.delete",
            payload={
                "current_password": current_password,
                "confirmation_email": confirmation_email,
            },
            action=lambda now: self._delete_account(
                user_id=user_id,
                current_password=current_password,
                confirmation_email=confirmation_email,
                idempotency_key=idempotency_key,
                now=now,
            ),
        )

    def _delete_account(
        self,
        *,
        user_id: UUID,
        current_password: str,
        confirmation_email: str,
        idempotency_key: str,
        now: datetime,
    ) -> dict[str, object]:
        self._verify_password(
            user_id,
            current_password,
            action="account.deleted",
            details={"reason": "current_password_mismatch"},
        )
        target = self.get_account(user_id)
        if str(target["email"]).casefold() != confirmation_email.strip().casefold():
            raise InvalidConfirmation(
                "请输入完整账户邮箱以确认永久删除。"
            ).with_denied_audit(
                action="account.deleted",
                actor_user_id=user_id,
                target_user_id=user_id,
                details={"reason": "confirmation_email_mismatch"},
            )
        if self._repository.is_provisioned_admin(user_id):
            raise ProvisionedAdministratorProtected().with_denied_audit(
                action="account.deleted",
                actor_user_id=user_id,
                target_user_id=user_id,
                details={"reason": "provisioned_administrator"},
            )
        if target["role"] == "admin" and self._repository.count_active_admins() <= 1:
            raise LastAdministratorProtected().with_denied_audit(
                action="account.deleted",
                actor_user_id=user_id,
                target_user_id=user_id,
                details={"reason": "last_active_administrator"},
            )
        self._audit(
            actor_user_id=user_id,
            target_user_id=user_id,
            action="account.deleted",
            details={"idempotency_key": idempotency_key, "irreversible": True},
            now=now,
        )
        self._repository.delete_account(user_id=user_id, now=now)
        return {"recoverable": False}

    def list_audit_events(
        self,
        *,
        actor_user_id: UUID,
        offset: int,
        limit: int,
    ) -> dict[str, object]:
        self._require_admin(actor_user_id)
        items = self._repository.list_audit_events(offset=offset, limit=limit + 1)
        has_more = len(items) > limit
        return {
            "items": items[:limit],
            "next_cursor": str(offset + limit) if has_more else None,
        }

    def require_admin_access(self, user_id: UUID) -> None:
        self._require_admin(user_id)

    def _require_admin(self, user_id: UUID) -> dict[str, object]:
        account = self.get_account(user_id)
        if account["role"] != "admin" or account["status"] != "active":
            raise AccountForbidden().with_denied_audit(
                action="admin.access",
                actor_user_id=user_id,
                target_user_id=None,
                details={},
            )
        return account

    def _verify_password(
        self,
        user_id: UUID,
        password: str,
        *,
        action: str,
        details: dict[str, object],
    ) -> None:
        stored = self._repository.get_password_hash(user_id)
        if stored is None or not self._password_hasher.verify(stored, password):
            raise InvalidCurrentPassword().with_denied_audit(
                action=action,
                actor_user_id=user_id,
                target_user_id=user_id,
                details=details,
            )

    def _mutate(
        self,
        *,
        actor_key: str,
        idempotency_key: str,
        operation: str,
        payload: dict[str, object],
        action: Callable[[datetime], _T],
        sanitize_for_storage: Callable[[_T], dict[str, object]] | None = None,
    ) -> _T:
        now = self._clock()
        request_hash = self._request_hash(operation, payload)
        replay = self._repository.begin_mutation(
            actor_key=actor_key,
            idempotency_key=idempotency_key,
            operation=operation,
            request_hash=request_hash,
            now=now,
        )
        if replay is not None:
            return replay  # type: ignore[return-value]
        result = action(now)
        stored = sanitize_for_storage(result) if sanitize_for_storage else result
        self._repository.complete_mutation(
            actor_key=actor_key,
            idempotency_key=idempotency_key,
            response=stored,
            now=now,
        )
        return result

    def _audit(
        self,
        *,
        actor_user_id: UUID | None,
        target_user_id: UUID | None,
        action: str,
        details: dict[str, object],
        now: datetime,
        outcome: str = "succeeded",
    ) -> None:
        self._repository.add_audit_event(
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            action=action,
            outcome=outcome,
            details=details,
            now=now,
        )

    @staticmethod
    def _request_hash(operation: str, payload: dict[str, object]) -> str:
        redacted = {
            key: (
                f"sha256:{sha256(str(value).encode('utf-8')).hexdigest()}"
                if key in _SENSITIVE_FIELDS
                else value
            )
            for key, value in payload.items()
        }
        canonical = json.dumps(
            {"operation": operation, "payload": redacted},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _digest(value: str) -> str:
        return sha256(value.encode("utf-8")).hexdigest()

    def _password_reset_token(
        self,
        *,
        actor_user_id: UUID,
        user_id: UUID,
        idempotency_key: str,
    ) -> str:
        secret = self._password_reset_signing_secret
        if secret is None:
            raise AccountCapabilityUnavailable(
                "密码重置签名密钥尚未配置，请联系部署负责人。"
            )
        message = (
            f"account-password-reset:{actor_user_id}:{user_id}:{idempotency_key}"
        ).encode()
        digest = hmac_new(secret, message, sha256).digest()
        return urlsafe_b64encode(digest).decode("ascii").rstrip("=")
