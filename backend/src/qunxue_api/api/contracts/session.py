from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class SessionStatus(StrEnum):
    ACTIVE = "active"
    LOGGED_OUT = "logged_out"


class SessionAction(StrEnum):
    LOGOUT = "logout"


class RegisterSessionRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, min_length=1, max_length=80)


class LoginSessionRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)


class SessionUserResponse(BaseModel):
    user_id: UUID
    email: str
    display_name: str | None


class SessionResponse(BaseModel):
    session_id: UUID
    status: SessionStatus
    version: int
    allowed_actions: list[SessionAction]
    user: SessionUserResponse
    expires_at: datetime


class LogoutSessionResponse(BaseModel):
    session_id: UUID
    status: SessionStatus
    version: int
    allowed_actions: list[SessionAction]
