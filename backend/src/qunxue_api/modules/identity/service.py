import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID, uuid4

from qunxue_api.modules.identity.domain import (
    AuthenticatedSession,
    SessionGrant,
    User,
    UserSession,
)
from qunxue_api.modules.identity.errors import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    InvalidEmail,
    Unauthenticated,
)
from qunxue_api.modules.identity.ports import IdentityRepository, PasswordHasher

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class IdentityService:
    def __init__(
        self,
        repository: IdentityRepository,
        password_hasher: PasswordHasher,
        *,
        invalid_password_hash: str,
        session_ttl: timedelta,
        id_factory: Callable[[], UUID] = uuid4,
        credential_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._password_hasher = password_hasher
        self._invalid_password_hash = invalid_password_hash
        self._session_ttl = session_ttl
        self._id_factory = id_factory
        self._credential_factory = credential_factory or (lambda: token_urlsafe(32))
        self._clock = clock or (lambda: datetime.now(UTC))

    def register(
        self,
        *,
        email: str,
        password: str,
        display_name: str | None,
    ) -> SessionGrant:
        normalized_email = self._normalize_email(email)
        if self._repository.get_user_by_email(normalized_email) is not None:
            raise EmailAlreadyRegistered

        now = self._clock()
        user = User(
            user_id=self._id_factory(),
            email=normalized_email,
            password_hash=self._password_hasher.hash(password),
            display_name=display_name.strip() if display_name else None,
            created_at=now,
            updated_at=now,
        )
        self._repository.add_user(user)
        return self._grant(user, now)

    def login(self, *, email: str, password: str) -> SessionGrant:
        normalized_email = email.strip().casefold()
        user = self._repository.get_user_by_email(normalized_email)
        password_hash = user.password_hash if user is not None else self._invalid_password_hash
        valid = self._password_hasher.verify(password_hash, password)
        if not valid or user is None:
            raise InvalidCredentials
        return self._grant(user, self._clock())

    def authenticate(self, credential: str | None) -> AuthenticatedSession:
        if not credential:
            raise Unauthenticated
        now = self._clock()
        session = self._repository.get_active_session(self._digest(credential), now)
        if session is None:
            raise Unauthenticated
        user = self._repository.get_user(session.user_id)
        if user is None:
            raise Unauthenticated
        return AuthenticatedSession(session=session, user=user)

    def logout(self, credential: str | None) -> AuthenticatedSession:
        authenticated = self.authenticate(credential)
        revoked = self._repository.revoke_session(
            authenticated.session.session_id,
            self._clock(),
        )
        return AuthenticatedSession(session=revoked, user=authenticated.user)

    def _grant(self, user: User, now: datetime) -> SessionGrant:
        credential = self._credential_factory()
        session = UserSession(
            session_id=self._id_factory(),
            user_id=user.user_id,
            token_digest=self._digest(credential),
            version=1,
            created_at=now,
            expires_at=now + self._session_ttl,
            revoked_at=None,
        )
        self._repository.add_session(session)
        return SessionGrant(
            authenticated=AuthenticatedSession(session=session, user=user),
            credential=credential,
        )

    @staticmethod
    def _digest(credential: str) -> str:
        return sha256(credential.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_email(email: str) -> str:
        normalized = email.strip().casefold()
        if not _EMAIL_PATTERN.fullmatch(normalized):
            raise InvalidEmail
        return normalized
