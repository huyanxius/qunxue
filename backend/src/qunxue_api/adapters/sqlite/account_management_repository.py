from collections import deque
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import MetaData, delete, func, or_, select, tuple_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.account_management_model import (
    AccountAuditEventRow,
    AccountMutationRequestRow,
    AccountPasswordResetRow,
    AccountSystemStateRow,
    PersonalDataExportRow,
    UserPreferenceRow,
)
from qunxue_api.adapters.sqlite.identity_model import UserRow, UserSessionRow
from qunxue_api.adapters.sqlite.model_invocation_model import ModelInvocationRow
from qunxue_api.adapters.sqlite.research_intake_model import ResearchTaskRow
from qunxue_api.modules.account_management import (
    ExpiredAccountToken,
    IdempotencyConflict,
    InvalidPasswordReset,
    ModelSecondaryUseAuthorization,
)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return _as_utc(value).isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


class SqliteAccountRepository:
    def __init__(self, session: Session) -> None:
        self._db = session

    def get_account(self, user_id: UUID) -> dict[str, object] | None:
        row = self._db.get(UserRow, str(user_id))
        if row is None:
            return None
        preference = self._db.get(UserPreferenceRow, str(user_id))
        if preference is None:
            raise RuntimeError("account preferences are missing")
        return {
            **self._account(row, preference),
            "is_protected_admin": self.is_provisioned_admin(user_id),
        }

    def get_user_by_email(self, email: str) -> dict[str, object] | None:
        row = self._db.scalar(select(UserRow).where(UserRow.email == email))
        if row is None:
            return None
        preference = self._db.get(UserPreferenceRow, row.user_id)
        if preference is None:
            raise RuntimeError("account preferences are missing")
        return {
            **self._account(row, preference),
            "is_protected_admin": self.is_provisioned_admin(UUID(row.user_id)),
        }

    def get_password_hash(self, user_id: UUID) -> str | None:
        return self._db.scalar(
            select(UserRow.password_hash).where(UserRow.user_id == str(user_id))
        )

    def begin_mutation(
        self,
        *,
        actor_key: str,
        idempotency_key: str,
        operation: str,
        request_hash: str,
        now: datetime,
    ) -> dict[str, object] | None:
        existing = self._mutation(actor_key, idempotency_key)
        if existing is not None:
            return self._replay(existing, operation, request_hash)

        try:
            with self._db.begin_nested():
                self._db.add(
                    AccountMutationRequestRow(
                        request_id=str(uuid4()),
                        actor_key=actor_key,
                        idempotency_key=idempotency_key,
                        operation=operation,
                        request_hash=request_hash,
                        status="processing",
                        response=None,
                        created_at=now,
                        completed_at=None,
                    )
                )
                self._db.flush()
        except IntegrityError:
            existing = self._mutation(actor_key, idempotency_key)
            if existing is None:
                raise
            return self._replay(existing, operation, request_hash)
        return None

    def complete_mutation(
        self,
        *,
        actor_key: str,
        idempotency_key: str,
        response: dict[str, object],
        now: datetime,
    ) -> None:
        self._db.execute(
            update(AccountMutationRequestRow)
            .where(
                AccountMutationRequestRow.actor_key == actor_key,
                AccountMutationRequestRow.idempotency_key == idempotency_key,
            )
            .values(
                status="completed",
                response=_json_safe(response),
                completed_at=now,
            )
        )

    def _mutation(
        self,
        actor_key: str,
        idempotency_key: str,
    ) -> AccountMutationRequestRow | None:
        return self._db.scalar(
            select(AccountMutationRequestRow).where(
                AccountMutationRequestRow.actor_key == actor_key,
                AccountMutationRequestRow.idempotency_key == idempotency_key,
            )
        )

    @staticmethod
    def _replay(
        row: AccountMutationRequestRow,
        operation: str,
        request_hash: str,
    ) -> dict[str, object]:
        if row.operation != operation or row.request_hash != request_hash:
            raise IdempotencyConflict
        if row.status != "completed" or row.response is None:
            raise IdempotencyConflict
        return dict(row.response)

    def update_profile(
        self,
        *,
        user_id: UUID,
        display_name: str | None,
        expected_version: int,
        now: datetime,
    ) -> dict[str, object] | None:
        changed = self._db.execute(
            update(UserRow)
            .where(
                UserRow.user_id == str(user_id),
                UserRow.version == expected_version,
            )
            .values(
                display_name=display_name,
                version=UserRow.version + 1,
                updated_at=now,
            )
        )
        if changed.rowcount != 1:
            return None
        self._db.flush()
        return self.get_account(user_id)

    def update_preferences(
        self,
        *,
        user_id: UUID,
        values: dict[str, object],
        expected_version: int,
        now: datetime,
    ) -> dict[str, object] | None:
        changed = self._db.execute(
            update(UserPreferenceRow)
            .where(
                UserPreferenceRow.user_id == str(user_id),
                UserPreferenceRow.version == expected_version,
            )
            .values(**values, version=UserPreferenceRow.version + 1, updated_at=now)
        )
        if changed.rowcount != 1:
            return None
        self._db.flush()
        row = self._db.get(UserPreferenceRow, str(user_id))
        if row is None:
            return None
        return self._preference(row)

    def list_sessions(
        self,
        *,
        user_id: UUID,
        current_session_id: UUID,
        now: datetime,
    ) -> list[dict[str, object]]:
        rows = self._db.scalars(
            select(UserSessionRow)
            .where(
                UserSessionRow.user_id == str(user_id),
                UserSessionRow.revoked_at.is_(None),
                UserSessionRow.expires_at > now,
            )
            .order_by(UserSessionRow.last_seen_at.desc(), UserSessionRow.created_at.desc())
        ).all()
        return [self._session(row, current_session_id) for row in rows]

    def revoke_session(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        current_session_id: UUID,
        now: datetime,
        reason: str,
    ) -> bool:
        del current_session_id
        changed = self._db.execute(
            update(UserSessionRow)
            .where(
                UserSessionRow.session_id == str(session_id),
                UserSessionRow.user_id == str(user_id),
                UserSessionRow.revoked_at.is_(None),
            )
            .values(
                revoked_at=now,
                revoked_reason=reason,
                version=UserSessionRow.version + 1,
            )
        )
        return changed.rowcount == 1

    def change_password(
        self,
        *,
        user_id: UUID,
        password_hash: str,
        current_session_id: UUID | None,
        revoke_other_sessions: bool,
        now: datetime,
    ) -> int:
        changed = self._db.execute(
            update(UserRow)
            .where(UserRow.user_id == str(user_id))
            .values(
                password_hash=password_hash,
                version=UserRow.version + 1,
                updated_at=now,
            )
        )
        if changed.rowcount != 1:
            raise RuntimeError("account disappeared while changing password")
        if not revoke_other_sessions:
            return 0
        predicates = [
            UserSessionRow.user_id == str(user_id),
            UserSessionRow.revoked_at.is_(None),
        ]
        if current_session_id is not None:
            predicates.append(UserSessionRow.session_id != str(current_session_id))
        revoked = self._db.execute(
            update(UserSessionRow)
            .where(*predicates)
            .values(
                revoked_at=now,
                revoked_reason="password_changed",
                version=UserSessionRow.version + 1,
            )
        )
        return int(revoked.rowcount or 0)

    def list_users(
        self,
        *,
        query: str | None,
        role: str | None,
        status: str | None,
        offset: int,
        limit: int,
        current_user_id: UUID,
    ) -> tuple[list[dict[str, object]], int]:
        filters = []
        if query:
            pattern = f"%{query.casefold()}%"
            filters.append(
                or_(
                    func.lower(UserRow.email).like(pattern),
                    func.lower(func.coalesce(UserRow.display_name, "")).like(pattern),
                )
            )
        if role:
            filters.append(UserRow.role == role)
        if status:
            filters.append(UserRow.status == status)
        total = int(
            self._db.scalar(select(func.count()).select_from(UserRow).where(*filters)) or 0
        )
        rows = self._db.scalars(
            select(UserRow)
            .where(*filters)
            .order_by(UserRow.created_at.desc(), UserRow.user_id)
            .offset(offset)
            .limit(limit)
        ).all()
        protected_user_id = self._provisioned_admin_user_id()
        return [
            self._directory_user(row, current_user_id, protected_user_id)
            for row in rows
        ], total

    def update_user_role(
        self,
        *,
        user_id: UUID,
        role: str,
        expected_version: int,
        now: datetime,
    ) -> dict[str, object] | None:
        changed = self._db.execute(
            update(UserRow)
            .where(
                UserRow.user_id == str(user_id),
                UserRow.version == expected_version,
            )
            .values(role=role, version=UserRow.version + 1, updated_at=now)
        )
        if changed.rowcount != 1:
            return None
        row = self._db.get(UserRow, str(user_id))
        return (
            self._directory_user(row, None, self._provisioned_admin_user_id())
            if row is not None
            else None
        )

    def update_user_status(
        self,
        *,
        user_id: UUID,
        status: str,
        expected_version: int,
        now: datetime,
        reason: str,
    ) -> dict[str, object] | None:
        changed = self._db.execute(
            update(UserRow)
            .where(
                UserRow.user_id == str(user_id),
                UserRow.version == expected_version,
            )
            .values(
                status=status,
                deactivated_at=now if status == "deactivated" else None,
                version=UserRow.version + 1,
                updated_at=now,
            )
        )
        if changed.rowcount != 1:
            return None
        if status != "active":
            self._db.execute(
                update(UserSessionRow)
                .where(
                    UserSessionRow.user_id == str(user_id),
                    UserSessionRow.revoked_at.is_(None),
                )
                .values(
                    revoked_at=now,
                    revoked_reason=reason[:64] or "account_disabled",
                    version=UserSessionRow.version + 1,
                )
            )
        row = self._db.get(UserRow, str(user_id))
        return (
            self._directory_user(row, None, self._provisioned_admin_user_id())
            if row is not None
            else None
        )

    def count_active_admins(self) -> int:
        # The harmless version bump acquires the SQLite write lock before the
        # count, so concurrent demotions cannot both observe the same last pair.
        self._db.execute(
            update(AccountSystemStateRow)
            .where(AccountSystemStateRow.singleton_id == 1)
            .values(lock_version=AccountSystemStateRow.lock_version + 1)
        )
        return int(
            self._db.scalar(
                select(func.count())
                .select_from(UserRow)
                .where(UserRow.role == "admin", UserRow.status == "active")
            )
            or 0
        )

    def lock_initial_admin_provisioning(self) -> UUID | None:
        self._db.execute(
            update(AccountSystemStateRow)
            .where(AccountSystemStateRow.singleton_id == 1)
            .values(lock_version=AccountSystemStateRow.lock_version + 1)
        )
        state = self._db.get(AccountSystemStateRow, 1)
        if state is None:
            raise RuntimeError("account system state is missing")
        if not state.initial_admin_provisioned:
            return None
        if state.provisioned_admin_user_id is None:
            raise RuntimeError("the provisioned administrator account is missing")
        return UUID(state.provisioned_admin_user_id)

    def provision_initial_admin(
        self,
        *,
        user_id: UUID,
        password_hash: str,
        now: datetime,
    ) -> dict[str, object]:
        changed = self._db.execute(
            update(UserRow)
            .where(
                UserRow.user_id == str(user_id),
                UserRow.status == "active",
            )
            .values(
                role="admin",
                status="active",
                password_hash=password_hash,
                deactivated_at=None,
                version=UserRow.version + 1,
                updated_at=now,
            )
        )
        if changed.rowcount != 1:
            raise RuntimeError("the initial administrator account is unavailable")
        state_changed = self._db.execute(
            update(AccountSystemStateRow)
            .where(
                AccountSystemStateRow.singleton_id == 1,
                AccountSystemStateRow.initial_admin_provisioned.is_(False),
            )
            .values(
                initial_admin_provisioned=True,
                provisioned_admin_user_id=str(user_id),
            )
        )
        if state_changed.rowcount != 1:
            raise RuntimeError("the initial administrator was provisioned concurrently")
        self._db.flush()
        account = self.get_account(user_id)
        if account is None:
            raise RuntimeError("the initial administrator account disappeared")
        return account

    def is_provisioned_admin(self, user_id: UUID) -> bool:
        return self._provisioned_admin_user_id() == str(user_id)

    def _provisioned_admin_user_id(self) -> str | None:
        state = self._db.get(AccountSystemStateRow, 1)
        if state is None or not state.initial_admin_provisioned:
            return None
        return state.provisioned_admin_user_id

    def create_password_reset(
        self,
        *,
        reset_id: UUID,
        user_id: UUID,
        token_digest: str,
        requested_by_user_id: UUID,
        now: datetime,
        expires_at: datetime,
    ) -> dict[str, object]:
        if self._db.get(UserRow, str(user_id)) is None:
            raise InvalidPasswordReset
        self._db.execute(
            update(AccountPasswordResetRow)
            .where(
                AccountPasswordResetRow.user_id == str(user_id),
                AccountPasswordResetRow.used_at.is_(None),
            )
            .values(used_at=now)
        )
        row = AccountPasswordResetRow(
            reset_id=str(reset_id),
            user_id=str(user_id),
            token_digest=token_digest,
            requested_by_user_id=str(requested_by_user_id),
            created_at=now,
            expires_at=expires_at,
            used_at=None,
        )
        self._db.add(row)
        self._db.flush()
        return {
            "reset_id": row.reset_id,
            "user_id": row.user_id,
            "expires_at": row.expires_at,
        }

    def consume_password_reset(
        self,
        *,
        token_digest: str,
        password_hash: str,
        now: datetime,
    ) -> UUID:
        row = self._db.scalar(
            select(AccountPasswordResetRow).where(
                AccountPasswordResetRow.token_digest == token_digest
            )
        )
        if row is None or row.used_at is not None:
            raise InvalidPasswordReset
        if _as_utc(row.expires_at) <= now:
            raise ExpiredAccountToken
        row.used_at = now
        user_id = UUID(row.user_id)
        self.change_password(
            user_id=user_id,
            password_hash=password_hash,
            current_session_id=None,
            revoke_other_sessions=True,
            now=now,
        )
        return user_id

    def create_export(
        self,
        *,
        export_id: UUID,
        user_id: UUID,
        now: datetime,
        expires_at: datetime,
    ) -> dict[str, object]:
        payload = self._personal_snapshot(user_id=user_id, exported_at=now)
        row = PersonalDataExportRow(
            export_id=str(export_id),
            user_id=str(user_id),
            status="ready",
            format="json",
            payload=payload,
            created_at=now,
            expires_at=expires_at,
        )
        self._db.add(row)
        self._db.flush()
        return self._export(row)

    def get_export(self, *, export_id: UUID, user_id: UUID) -> dict[str, object] | None:
        row = self._db.scalar(
            select(PersonalDataExportRow).where(
                PersonalDataExportRow.export_id == str(export_id),
                PersonalDataExportRow.user_id == str(user_id),
            )
        )
        return self._export(row) if row is not None else None

    def get_export_payload(
        self,
        *,
        export_id: UUID,
        user_id: UUID,
    ) -> dict[str, object] | None:
        row = self._db.scalar(
            select(PersonalDataExportRow).where(
                PersonalDataExportRow.export_id == str(export_id),
                PersonalDataExportRow.user_id == str(user_id),
            )
        )
        if row is None or row.status != "ready":
            return None
        if _as_utc(row.expires_at) <= datetime.now(UTC):
            return None
        return dict(row.payload)

    def deactivate_account(
        self,
        *,
        user_id: UUID,
        now: datetime,
        reason: str,
    ) -> None:
        updated = self.update_user_status(
            user_id=user_id,
            status="deactivated",
            expected_version=int(
                self._db.scalar(
                    select(UserRow.version).where(UserRow.user_id == str(user_id))
                )
                or 0
            ),
            now=now,
            reason=reason,
        )
        if updated is None:
            raise RuntimeError("account disappeared while deactivating")

    def delete_account(self, *, user_id: UUID, now: datetime) -> None:
        user_key = str(user_id)
        task_ids = list(
            self._db.scalars(
                select(ResearchTaskRow.task_id).where(ResearchTaskRow.user_id == user_key)
            )
        )
        if task_ids:
            self._db.execute(
                delete(ModelInvocationRow).where(ModelInvocationRow.task_id.in_(task_ids))
            )
        self._db.execute(
            delete(AccountMutationRequestRow).where(
                AccountMutationRequestRow.actor_key == user_key
            )
        )
        audits = self._db.scalars(
            select(AccountAuditEventRow).where(
                or_(
                    AccountAuditEventRow.actor_user_id == user_key,
                    AccountAuditEventRow.target_user_id == user_key,
                )
            )
        ).all()
        for audit in audits:
            if audit.actor_user_id == user_key:
                audit.actor_email = "[deleted]"
            if audit.target_user_id == user_key:
                audit.target_email = "[deleted]"
            audit.details = {"subject_deleted": True, "redacted_at": now.isoformat()}
            audit.ip_address = None
            audit.user_agent = None
        self._db.execute(delete(UserRow).where(UserRow.user_id == user_key))
        self._db.flush()

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
    ) -> None:
        actor = self._db.get(UserRow, str(actor_user_id)) if actor_user_id else None
        target = self._db.get(UserRow, str(target_user_id)) if target_user_id else None
        self._db.add(
            AccountAuditEventRow(
                event_id=str(uuid4()),
                actor_user_id=str(actor_user_id) if actor_user_id else None,
                target_user_id=str(target_user_id) if target_user_id else None,
                actor_email=actor.email if actor else None,
                target_email=target.email if target else None,
                action=action,
                outcome=outcome,
                details=_json_safe(details),
                ip_address=ip_address,
                user_agent=user_agent,
                created_at=now,
            )
        )
        self._db.flush()

    def list_audit_events(
        self,
        *,
        offset: int,
        limit: int,
    ) -> list[dict[str, object]]:
        rows = self._db.scalars(
            select(AccountAuditEventRow)
            .order_by(AccountAuditEventRow.created_at.desc(), AccountAuditEventRow.event_id)
            .offset(offset)
            .limit(limit)
        ).all()
        return [self._audit_event(row) for row in rows]

    def model_secondary_use_authorization(
        self,
        user_id: UUID,
    ) -> ModelSecondaryUseAuthorization:
        row = self._db.get(UserPreferenceRow, str(user_id))
        if row is None:
            raise RuntimeError("account preferences are missing")
        return ModelSecondaryUseAuthorization(
            user_id=user_id,
            allowed=row.model_improvement_allowed,
            policy_version=row.consent_policy_version,
            updated_at=_as_utc(row.consent_updated_at) if row.consent_updated_at else None,
        )

    def _personal_snapshot(self, *, user_id: UUID, exported_at: datetime) -> dict[str, object]:
        bind = self._db.get_bind()
        metadata = MetaData()
        metadata.reflect(bind=bind)
        user_table = metadata.tables["users"]
        user_row = self._db.execute(
            select(user_table).where(user_table.c.user_id == str(user_id))
        ).mappings().first()
        if user_row is None:
            raise RuntimeError("account disappeared while exporting")

        excluded_tables = {
            "alembic_version",
            "account_system_state",
            "account_mutation_requests",
            "account_password_resets",
            "personal_data_exports",
        }
        selected: dict[str, list[dict[str, Any]]] = {"users": [dict(user_row)]}
        selected_identities: dict[str, set[tuple[Any, ...]]] = {
            "users": {self._row_identity(user_table, dict(user_row))}
        }
        queue: deque[tuple[str, list[dict[str, Any]]]] = deque(
            [("users", [dict(user_row)])]
        )
        while queue:
            parent_name, parent_rows = queue.popleft()
            for child_name, child in metadata.tables.items():
                if child_name in excluded_tables or child_name == "users":
                    continue
                predicates = []
                for constraint in child.foreign_key_constraints:
                    if constraint.referred_table.name != parent_name:
                        continue
                    pairs = list(constraint.elements)
                    parent_values = {
                        tuple(row[element.column.name] for element in pairs)
                        for row in parent_rows
                    }
                    if not parent_values:
                        continue
                    local_columns = [child.c[element.parent.name] for element in pairs]
                    if len(local_columns) == 1:
                        predicate = local_columns[0].in_({item[0] for item in parent_values})
                    else:
                        predicate = tuple_(*local_columns).in_(parent_values)
                    predicates.append(predicate)
                if not predicates:
                    continue
                rows = [
                    dict(row)
                    for row in self._db.execute(select(child).where(or_(*predicates))).mappings()
                ]
                identities = selected_identities.setdefault(child_name, set())
                new_rows = []
                for row in rows:
                    identity = self._row_identity(child, row)
                    if identity in identities:
                        continue
                    identities.add(identity)
                    new_rows.append(row)
                if new_rows:
                    selected.setdefault(child_name, []).extend(new_rows)
                    queue.append((child_name, new_rows))

        task_ids = {
            row["task_id"] for row in selected.get("research_tasks", []) if row.get("task_id")
        }
        if task_ids and "model_invocations" in metadata.tables:
            invocations = metadata.tables["model_invocations"]
            selected["model_invocations"] = [
                dict(row)
                for row in self._db.execute(
                    select(invocations).where(invocations.c.task_id.in_(task_ids))
                ).mappings()
            ]

        records: dict[str, object] = {}
        for table_name, rows in sorted(selected.items()):
            records[table_name] = [self._sanitize_export_row(row) for row in rows]
        return _json_safe(
            {
                "format_version": "2026-08-account-export-v1",
                "exported_at": exported_at,
                "processing_notice": (
                    "模型改进授权仅适用于可选的二次使用；研究功能所需推理记录按产品保留策略导出。"
                ),
                "records": records,
            }
        )

    @staticmethod
    def _row_identity(table: Any, row: dict[str, Any]) -> tuple[Any, ...]:
        primary_keys = list(table.primary_key.columns)
        if primary_keys:
            return tuple(row[column.name] for column in primary_keys)
        return tuple(sorted(row.items()))

    @staticmethod
    def _sanitize_export_row(row: dict[str, Any]) -> dict[str, object]:
        forbidden = {
            "credential_hash",
            "password_hash",
            "token_digest",
            "payload",
        }
        return {
            key: _json_safe(value)
            for key, value in row.items()
            if key not in forbidden
        }

    @staticmethod
    def _account(user: UserRow, preference: UserPreferenceRow) -> dict[str, object]:
        return {
            "user_id": user.user_id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "status": user.status,
            "version": user.version,
            "created_at": _as_utc(user.created_at),
            "updated_at": _as_utc(user.updated_at),
            "last_login_at": _as_utc(user.last_login_at) if user.last_login_at else None,
            "preferences": SqliteAccountRepository._preference(preference),
        }

    @staticmethod
    def _preference(row: UserPreferenceRow) -> dict[str, object]:
        return {
            "locale": row.locale,
            "timezone": row.timezone,
            "research_updates_enabled": row.research_updates_enabled,
            "model_improvement_allowed": row.model_improvement_allowed,
            "consent_policy_version": row.consent_policy_version,
            "consent_updated_at": (
                _as_utc(row.consent_updated_at) if row.consent_updated_at else None
            ),
            "version": row.version,
        }

    @staticmethod
    def _session(row: UserSessionRow, current_session_id: UUID) -> dict[str, object]:
        return {
            "session_id": row.session_id,
            "current": row.session_id == str(current_session_id),
            "created_at": _as_utc(row.created_at),
            "last_seen_at": _as_utc(row.last_seen_at or row.created_at),
            "expires_at": _as_utc(row.expires_at),
            "device_label": SqliteAccountRepository._device_label(row.user_agent),
            "ip_address": row.ip_address,
        }

    @staticmethod
    def _device_label(user_agent: str | None) -> str:
        if not user_agent:
            return "未知设备"
        browser = "Safari" if "Safari" in user_agent and "Chrome" not in user_agent else None
        if "Firefox" in user_agent:
            browser = "Firefox"
        elif "Chrome" in user_agent:
            browser = "Chrome"
        browser = browser or "浏览器"
        if "iPhone" in user_agent or "iPad" in user_agent:
            platform = "iOS"
        elif "Macintosh" in user_agent:
            platform = "macOS"
        elif "Windows" in user_agent:
            platform = "Windows"
        elif "Android" in user_agent:
            platform = "Android"
        else:
            platform = "未知系统"
        return f"{browser} · {platform}"

    @staticmethod
    def _directory_user(
        row: UserRow,
        current_user_id: UUID | None,
        protected_user_id: str | None,
    ) -> dict[str, object]:
        return {
            "user_id": row.user_id,
            "email": row.email,
            "display_name": row.display_name,
            "role": row.role,
            "status": row.status,
            "version": row.version,
            "created_at": _as_utc(row.created_at),
            "last_active_at": _as_utc(row.last_login_at) if row.last_login_at else None,
            "is_current_user": (
                row.user_id == str(current_user_id) if current_user_id is not None else False
            ),
            "is_protected_admin": row.user_id == protected_user_id,
        }

    @staticmethod
    def _export(row: PersonalDataExportRow) -> dict[str, object]:
        return {
            "export_id": row.export_id,
            "status": row.status,
            "format": row.format,
            "created_at": _as_utc(row.created_at),
            "expires_at": _as_utc(row.expires_at),
            "download_href": f"/api/account/data-exports/{row.export_id}/download",
        }

    @staticmethod
    def _audit_event(row: AccountAuditEventRow) -> dict[str, object]:
        return {
            "event_id": row.event_id,
            "action": row.action,
            "outcome": row.outcome,
            "actor_email": row.actor_email,
            "target_email": row.target_email,
            "reason": row.details.get("reason") if row.details else None,
            "details": row.details,
            "occurred_at": _as_utc(row.created_at),
        }
