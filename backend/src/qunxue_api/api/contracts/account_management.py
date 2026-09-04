from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from qunxue_api.modules.identity import AccountRole, AccountStatus


class ExportStatus(StrEnum):
    READY = "ready"
    FAILED = "failed"


class AccountPreferencesResponse(BaseModel):
    locale: str
    timezone: str
    research_updates_enabled: bool
    model_improvement_allowed: bool
    consent_policy_version: str
    consent_updated_at: datetime | None
    version: int


class AccountResponse(BaseModel):
    user_id: UUID
    email: str
    display_name: str | None
    role: AccountRole
    status: AccountStatus
    version: int
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
    is_protected_admin: bool
    preferences: AccountPreferencesResponse


class CreditLedgerEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entry_id: UUID
    kind: Literal["signup_grant", "usage", "redemption"]
    points: int
    balance_after: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    created_at: datetime


class CreditPricingResponse(BaseModel):
    input_tokens_per_credit: int = Field(ge=1)
    output_tokens_per_credit: int = Field(ge=1)


class CreditSummaryResponse(BaseModel):
    balance: int = Field(ge=0)
    credit_limit: int = Field(ge=0)
    grant_amount: int = Field(ge=0)
    is_unlimited: bool
    pricing: CreditPricingResponse
    entries: list[CreditLedgerEntryResponse]
    total_entries: int = Field(ge=0)
    next_cursor: str | None


class CreditRedemptionRequest(BaseModel):
    code: str = Field(min_length=16, max_length=64)


class CreditRedemptionResponse(BaseModel):
    redeemed_points: int = Field(gt=0)
    balance: int = Field(ge=0)


class CreditCodeBatchCreateRequest(BaseModel):
    count: int = Field(ge=1, le=100)
    expires_in_days: int = Field(ge=1, le=365)


class CreditCodeBatchResponse(BaseModel):
    codes: list[str]
    points: int = Field(gt=0)
    expires_at: datetime


class UpdateProfileRequest(BaseModel):
    display_name: str = Field(max_length=80)
    expected_version: int = Field(ge=1)


class UpdatePreferencesRequest(BaseModel):
    locale: str = Field(min_length=2, max_length=16)
    timezone: str = Field(min_length=1, max_length=64)
    research_updates_enabled: bool
    expected_version: int = Field(ge=1)


class UpdateModelDataAuthorizationRequest(BaseModel):
    allowed: bool
    policy_version: str = Field(min_length=1, max_length=64)
    expected_version: int = Field(ge=1)


class AccountSessionResponse(BaseModel):
    session_id: UUID
    current: bool
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    device_label: str
    ip_address: str | None


class AccountSessionPageResponse(BaseModel):
    items: list[AccountSessionResponse]


class RevokeSessionResponse(BaseModel):
    session_id: UUID
    revoked: bool


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)
    revoke_other_sessions: bool = True


class ChangePasswordResponse(BaseModel):
    revoked_session_count: int = Field(ge=0)


class AdminUserResponse(BaseModel):
    user_id: UUID
    email: str
    display_name: str | None
    role: AccountRole
    status: AccountStatus
    version: int
    created_at: datetime
    last_active_at: datetime | None
    is_current_user: bool
    is_protected_admin: bool


class AdminUserPageResponse(BaseModel):
    items: list[AdminUserResponse]
    total: int = Field(ge=0)
    next_cursor: str | None


class AdminRuntimeSettingsResponse(BaseModel):
    model: str
    reasoning_effort: str
    provider_base_url: str
    restart_required: bool = False


class AdminRuntimeSettingsUpdateRequest(BaseModel):
    model: str = Field(min_length=1, max_length=160)
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]


class AdminRoleUpdateRequest(BaseModel):
    role: AccountRole
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=240)


class AdminStatusUpdateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=240)


class PasswordResetLinkResponse(BaseModel):
    reset_id: UUID
    user_id: UUID
    expires_at: datetime
    reset_token: str | None = None


class PasswordResetConsumeRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=12, max_length=128)


class PasswordResetConsumeResponse(BaseModel):
    password_reset: bool


class DataExportCreateRequest(BaseModel):
    format: Literal["json"] = "json"


class DataExportResponse(BaseModel):
    export_id: UUID
    status: ExportStatus
    format: Literal["json"]
    created_at: datetime
    expires_at: datetime
    download_href: str


class DeactivateAccountRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    reason: str = Field(min_length=3, max_length=240)


class DeactivateAccountResponse(BaseModel):
    recoverable: Literal[True]
    recovery: Literal["contact_an_administrator"]


class DeleteAccountRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    confirmation_email: str = Field(min_length=3, max_length=320)


class DeleteAccountResponse(BaseModel):
    recoverable: Literal[False]


class AccountAuditEventResponse(BaseModel):
    event_id: UUID
    action: str
    outcome: Literal["succeeded", "denied", "failed"]
    actor_email: str | None
    target_email: str | None
    reason: str | None
    details: dict[str, object]
    occurred_at: datetime


class AccountAuditPageResponse(BaseModel):
    items: list[AccountAuditEventResponse]
    next_cursor: str | None
