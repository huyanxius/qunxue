from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite import UserRow, UserSessionRow
from qunxue_api.modules.identity import (
    AccountRole,
    AccountStatus,
    EmailAlreadyRegistered,
    IdentityRepository,
    User,
    UserSession,
)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SqliteIdentityRepository(IdentityRepository):
    def __init__(self, session: Session) -> None:
        self._db_session = session

    def get_user_by_email(self, email: str) -> User | None:
        row = self._db_session.scalar(select(UserRow).where(UserRow.email == email))
        return self._user(row) if row is not None else None

    def add_user(self, user: User) -> User:
        # Imported lazily to keep the identity adapter usable while Alembic loads
        # all model modules through the registry.
        from qunxue_api.adapters.sqlite.account_management_model import UserPreferenceRow

        row = UserRow(
            user_id=str(user.user_id),
            email=user.email,
            password_hash=user.password_hash,
            display_name=user.display_name,
            role=user.role.value,
            status=user.status.value,
            version=user.version,
            last_login_at=user.created_at,
            deactivated_at=user.deactivated_at,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
        self._db_session.add(row)
        try:
            self._db_session.flush()
        except IntegrityError as error:
            self._db_session.rollback()
            raise EmailAlreadyRegistered from error

        self._db_session.add(
            UserPreferenceRow(
                user_id=str(user.user_id),
                locale="zh-CN",
                timezone="Asia/Shanghai",
                research_updates_enabled=True,
                model_improvement_allowed=False,
                consent_policy_version="2026-08-secondary-use-v1",
                consent_updated_at=None,
                version=1,
                updated_at=user.created_at,
            )
        )
        self._db_session.flush()
        return self._user(row)

    def add_session(self, session: UserSession) -> None:
        self._db_session.add(
            UserSessionRow(
                session_id=str(session.session_id),
                user_id=str(session.user_id),
                token_digest=session.token_digest,
                version=session.version,
                created_at=session.created_at,
                expires_at=session.expires_at,
                revoked_at=session.revoked_at,
                last_seen_at=session.last_seen_at,
                user_agent=session.user_agent,
                ip_address=session.ip_address,
                revoked_reason=session.revoked_reason,
            )
        )
        self._db_session.flush()

    def get_active_session(self, token_digest: str, now: datetime) -> UserSession | None:
        row = self._db_session.scalar(
            select(UserSessionRow).where(
                UserSessionRow.token_digest == token_digest,
                UserSessionRow.revoked_at.is_(None),
                UserSessionRow.expires_at > now,
            )
        )
        return self._to_session(row) if row is not None else None

    def get_user(self, user_id: UUID) -> User | None:
        row = self._db_session.get(UserRow, str(user_id))
        return self._user(row) if row is not None else None

    def record_login(self, user_id: UUID, logged_in_at: datetime) -> User:
        self._db_session.execute(
            update(UserRow)
            .where(UserRow.user_id == str(user_id))
            .values(last_login_at=logged_in_at)
        )
        row = self._db_session.get(UserRow, str(user_id))
        if row is None:
            raise RuntimeError("user disappeared while recording a login")
        return self._user(row)

    def touch_session(self, session_id: UUID, seen_at: datetime) -> UserSession:
        self._db_session.execute(
            update(UserSessionRow)
            .where(UserSessionRow.session_id == str(session_id))
            .values(last_seen_at=seen_at)
        )
        row = self._db_session.get(UserSessionRow, str(session_id))
        if row is None:
            raise RuntimeError("session disappeared while recording activity")
        return self._to_session(row)

    def revoke_session(
        self,
        session_id: UUID,
        revoked_at: datetime,
        reason: str | None = None,
    ) -> UserSession:
        self._db_session.execute(
            update(UserSessionRow)
            .where(UserSessionRow.session_id == str(session_id))
            .values(
                revoked_at=revoked_at,
                revoked_reason=reason,
                version=UserSessionRow.version + 1,
            )
        )
        row = self._db_session.get(UserSessionRow, str(session_id))
        if row is None:
            raise RuntimeError("session disappeared while revoking it")
        return self._to_session(row)

    @staticmethod
    def _user(row: UserRow) -> User:
        return User(
            user_id=UUID(row.user_id),
            email=row.email,
            password_hash=row.password_hash,
            display_name=row.display_name,
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
            role=AccountRole(row.role),
            status=AccountStatus(row.status),
            version=row.version,
            last_login_at=_as_utc(row.last_login_at) if row.last_login_at else None,
            deactivated_at=_as_utc(row.deactivated_at) if row.deactivated_at else None,
        )

    @staticmethod
    def _to_session(row: UserSessionRow) -> UserSession:
        return UserSession(
            session_id=UUID(row.session_id),
            user_id=UUID(row.user_id),
            token_digest=row.token_digest,
            version=row.version,
            created_at=_as_utc(row.created_at),
            expires_at=_as_utc(row.expires_at),
            revoked_at=_as_utc(row.revoked_at) if row.revoked_at else None,
            last_seen_at=_as_utc(row.last_seen_at) if row.last_seen_at else None,
            user_agent=row.user_agent,
            ip_address=row.ip_address,
            revoked_reason=row.revoked_reason,
        )
