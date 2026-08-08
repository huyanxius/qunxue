from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class User:
    user_id: UUID
    email: str
    password_hash: str
    display_name: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class UserSession:
    session_id: UUID
    user_id: UUID
    token_digest: str
    version: int
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    session: UserSession
    user: User


@dataclass(frozen=True, slots=True)
class SessionGrant:
    authenticated: AuthenticatedSession
    credential: str
