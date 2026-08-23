from datetime import datetime
from typing import Protocol
from uuid import UUID

from qunxue_api.modules.identity.domain import RegistrationVerification, User, UserSession


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str, password: str) -> bool: ...


class EmailProvider(Protocol):
    def send_verification_code(self, email: str, code: str) -> None: ...


class IdentityRepository(Protocol):
    def get_user_by_email(self, email: str) -> User | None: ...

    def add_user(self, user: User) -> User: ...

    def add_session(self, session: UserSession) -> None: ...

    def get_registration_verification(self, email: str) -> RegistrationVerification | None: ...

    def save_registration_verification(
        self,
        verification: RegistrationVerification,
    ) -> None: ...

    def delete_registration_verification(self, email: str) -> None: ...

    def get_active_session(self, token_digest: str, now: datetime) -> UserSession | None: ...

    def get_user(self, user_id: UUID) -> User | None: ...

    def record_login(self, user_id: UUID, logged_in_at: datetime) -> User: ...

    def touch_session(self, session_id: UUID, seen_at: datetime) -> UserSession: ...

    def revoke_session(
        self,
        session_id: UUID,
        revoked_at: datetime,
        reason: str | None = None,
    ) -> UserSession: ...
