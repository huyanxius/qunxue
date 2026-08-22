from datetime import datetime
from typing import Protocol
from uuid import UUID

from qunxue_api.modules.account_management.domain import ModelSecondaryUseAuthorization


class AccountRepository(Protocol):
    def get_account(self, user_id: UUID) -> dict[str, object] | None: ...

    def get_user_by_email(self, email: str) -> dict[str, object] | None: ...

    def get_password_hash(self, user_id: UUID) -> str | None: ...

    def begin_mutation(
        self,
        *,
        actor_key: str,
        idempotency_key: str,
        operation: str,
        request_hash: str,
        now: datetime,
    ) -> dict[str, object] | None: ...

    def complete_mutation(
        self,
        *,
        actor_key: str,
        idempotency_key: str,
        response: dict[str, object],
        now: datetime,
    ) -> None: ...

    def update_profile(
        self,
        *,
        user_id: UUID,
        display_name: str | None,
        expected_version: int,
        now: datetime,
    ) -> dict[str, object] | None: ...

    def update_preferences(
        self,
        *,
        user_id: UUID,
        values: dict[str, object],
        expected_version: int,
        now: datetime,
    ) -> dict[str, object] | None: ...

    def list_sessions(
        self,
        *,
        user_id: UUID,
        current_session_id: UUID,
        now: datetime,
    ) -> list[dict[str, object]]: ...

    def revoke_session(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        current_session_id: UUID,
        now: datetime,
        reason: str,
    ) -> bool: ...

    def change_password(
        self,
        *,
        user_id: UUID,
        password_hash: str,
        current_session_id: UUID | None,
        revoke_other_sessions: bool,
        now: datetime,
    ) -> int: ...

    def list_users(
        self,
        *,
        query: str | None,
        role: str | None,
        status: str | None,
        offset: int,
        limit: int,
        current_user_id: UUID,
    ) -> tuple[list[dict[str, object]], int]: ...

    def update_user_role(
        self,
        *,
        user_id: UUID,
        role: str,
        expected_version: int,
        now: datetime,
    ) -> dict[str, object] | None: ...

    def update_user_status(
        self,
        *,
        user_id: UUID,
        status: str,
        expected_version: int,
        now: datetime,
        reason: str,
    ) -> dict[str, object] | None: ...

    def count_active_admins(self) -> int: ...

    def is_provisioned_admin(self, user_id: UUID) -> bool: ...

    def create_password_reset(
        self,
        *,
        reset_id: UUID,
        user_id: UUID,
        token_digest: str,
        requested_by_user_id: UUID,
        now: datetime,
        expires_at: datetime,
    ) -> dict[str, object]: ...

    def consume_password_reset(
        self,
        *,
        token_digest: str,
        password_hash: str,
        now: datetime,
    ) -> UUID: ...

    def create_export(
        self,
        *,
        export_id: UUID,
        user_id: UUID,
        now: datetime,
        expires_at: datetime,
    ) -> dict[str, object]: ...

    def get_export(self, *, export_id: UUID, user_id: UUID) -> dict[str, object] | None: ...

    def get_export_payload(self, *, export_id: UUID, user_id: UUID) -> dict[str, object] | None: ...

    def deactivate_account(
        self,
        *,
        user_id: UUID,
        now: datetime,
        reason: str,
    ) -> None: ...

    def delete_account(self, *, user_id: UUID, now: datetime) -> None: ...

    def add_audit_event(
        self,
        *,
        actor_user_id: UUID | None,
        target_user_id: UUID | None,
        action: str,
        outcome: str,
        details: dict[str, object],
        now: datetime,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None: ...

    def list_audit_events(
        self,
        *,
        offset: int,
        limit: int,
    ) -> list[dict[str, object]]: ...

    def model_secondary_use_authorization(
        self,
        user_id: UUID,
    ) -> ModelSecondaryUseAuthorization: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str, password: str) -> bool: ...
