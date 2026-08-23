import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from math import ceil
from secrets import randbelow, token_urlsafe
from uuid import UUID, uuid4

from qunxue_api.modules.identity.domain import (
    AccountStatus,
    AuthenticatedSession,
    RegistrationVerification,
    SessionGrant,
    User,
    UserSession,
)
from qunxue_api.modules.identity.errors import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    InvalidEmail,
    InvalidVerificationCode,
    Unauthenticated,
    VerificationCodeRateLimited,
)
from qunxue_api.modules.identity.ports import EmailProvider, IdentityRepository, PasswordHasher

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_VERIFICATION_TTL = timedelta(minutes=5)
_VERIFICATION_COOLDOWN = timedelta(seconds=60)
_VERIFICATION_ATTEMPTS = 5


class IdentityService:
    def __init__(
        self,
        repository: IdentityRepository,
        password_hasher: PasswordHasher,
        *,
        invalid_password_hash: str,
        session_ttl: timedelta,
        email_provider: EmailProvider | None = None,
        id_factory: Callable[[], UUID] = uuid4,
        credential_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        verification_code_factory: Callable[[], str] | None = None,
        require_email_verification: bool = True,
    ) -> None:
        self._repository = repository
        self._password_hasher = password_hasher
        self._email_provider = email_provider
        self._invalid_password_hash = invalid_password_hash
        self._session_ttl = session_ttl
        self._id_factory = id_factory
        self._credential_factory = credential_factory or (lambda: token_urlsafe(32))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._verification_code_factory = verification_code_factory or self._generate_code
        self._require_email_verification = require_email_verification

    def send_registration_code(self, *, email: str) -> None:
        normalized_email = self._normalize_email(email)
        now = self._clock()
        current = self._repository.get_registration_verification(normalized_email)
        if current is not None and current.resend_available_at > now:
            retry_after = max(1, ceil((current.resend_available_at - now).total_seconds()))
            raise VerificationCodeRateLimited(retry_after)

        code = self._verification_code_factory()
        verification = RegistrationVerification(
            email=normalized_email,
            code_hash=self._password_hasher.hash(code),
            expires_at=now + _VERIFICATION_TTL,
            resend_available_at=now + _VERIFICATION_COOLDOWN,
            attempts_remaining=_VERIFICATION_ATTEMPTS,
        )
        self._repository.save_registration_verification(verification)
        if self._email_provider is None:
            from qunxue_api.modules.identity.errors import EmailDeliveryUnavailable

            raise EmailDeliveryUnavailable
        self._email_provider.send_verification_code(normalized_email, code)

    def register(
        self,
        *,
        email: str,
        password: str,
        display_name: str | None,
        verification_code: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> SessionGrant:
        normalized_email = self._normalize_email(email)
        if self._require_email_verification:
            self._consume_registration_code(normalized_email, verification_code)
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
        persisted = self._repository.add_user(user)
        return self._grant(
            persisted,
            now,
            user_agent=user_agent,
            ip_address=ip_address,
        )

    def _consume_registration_code(self, email: str, code: str | None) -> None:
        verification = self._repository.get_registration_verification(email)
        now = self._clock()
        if (
            verification is None
            or verification.expires_at <= now
            or verification.attempts_remaining <= 0
            or code is None
        ):
            raise InvalidVerificationCode

        if not self._password_hasher.verify(verification.code_hash, code):
            self._repository.save_registration_verification(
                RegistrationVerification(
                    email=verification.email,
                    code_hash=verification.code_hash,
                    expires_at=verification.expires_at,
                    resend_available_at=verification.resend_available_at,
                    attempts_remaining=verification.attempts_remaining - 1,
                )
            )
            raise InvalidVerificationCode
        self._repository.delete_registration_verification(email)

    def login(
        self,
        *,
        email: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> SessionGrant:
        normalized_email = email.strip().casefold()
        user = self._repository.get_user_by_email(normalized_email)
        password_hash = user.password_hash if user is not None else self._invalid_password_hash
        valid = self._password_hasher.verify(password_hash, password)
        if not valid or user is None or user.status is not AccountStatus.ACTIVE:
            raise InvalidCredentials
        now = self._clock()
        user = self._repository.record_login(user.user_id, now)
        return self._grant(
            user,
            now,
            user_agent=user_agent,
            ip_address=ip_address,
        )

    def authenticate(self, credential: str | None) -> AuthenticatedSession:
        if not credential:
            raise Unauthenticated
        now = self._clock()
        session = self._repository.get_active_session(self._digest(credential), now)
        if session is None:
            raise Unauthenticated
        user = self._repository.get_user(session.user_id)
        if user is None or user.status is not AccountStatus.ACTIVE:
            raise Unauthenticated
        return AuthenticatedSession(session=session, user=user)

    def logout(self, credential: str | None) -> AuthenticatedSession:
        authenticated = self.authenticate(credential)
        revoked = self._repository.revoke_session(
            authenticated.session.session_id,
            self._clock(),
            "logout",
        )
        return AuthenticatedSession(session=revoked, user=authenticated.user)

    def _grant(
        self,
        user: User,
        now: datetime,
        *,
        user_agent: str | None,
        ip_address: str | None,
    ) -> SessionGrant:
        credential = self._credential_factory()
        session = UserSession(
            session_id=self._id_factory(),
            user_id=user.user_id,
            token_digest=self._digest(credential),
            version=1,
            created_at=now,
            expires_at=now + self._session_ttl,
            revoked_at=None,
            last_seen_at=now,
            user_agent=user_agent.strip()[:512] if user_agent else None,
            ip_address=ip_address.strip()[:64] if ip_address else None,
            revoked_reason=None,
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

    @staticmethod
    def _generate_code() -> str:
        return f"{randbelow(1_000_000):06d}"
