from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class AccountRole(StrEnum):
    MEMBER = "member"
    ADMIN = "admin"


class AccountStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    DEACTIVATED = "deactivated"


@dataclass(frozen=True, slots=True)
class User:
    user_id: UUID
    email: str
    password_hash: str
    display_name: str | None
    created_at: datetime
    updated_at: datetime
    role: AccountRole = AccountRole.MEMBER
    status: AccountStatus = AccountStatus.ACTIVE
    version: int = 1
    last_login_at: datetime | None = None
    deactivated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class UserSession:
    session_id: UUID
    user_id: UUID
    token_digest: str
    version: int
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    last_seen_at: datetime | None = None
    user_agent: str | None = None
    ip_address: str | None = None
    revoked_reason: str | None = None


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    session: UserSession
    user: User


@dataclass(frozen=True, slots=True)
class SessionGrant:
    authenticated: AuthenticatedSession
    credential: str
