from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite import UserRow, UserSessionRow
from qunxue_api.modules.identity import (
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

    def add_user(self, user: User) -> None:
        self._db_session.add(
            UserRow(
                user_id=str(user.user_id),
                email=user.email,
                password_hash=user.password_hash,
                display_name=user.display_name,
                created_at=user.created_at,
                updated_at=user.updated_at,
            )
        )
        try:
            self._db_session.flush()
        except IntegrityError as error:
            self._db_session.rollback()
            raise EmailAlreadyRegistered from error

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

    def revoke_session(self, session_id: UUID, revoked_at: datetime) -> UserSession:
        self._db_session.execute(
            update(UserSessionRow)
            .where(UserSessionRow.session_id == str(session_id))
            .values(revoked_at=revoked_at, version=UserSessionRow.version + 1)
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
        )
