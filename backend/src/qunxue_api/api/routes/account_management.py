import json
import os
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from qunxue_api.api.contracts.account_management import (
    AccountAuditPageResponse,
    AccountPreferencesResponse,
    AccountResponse,
    AccountSessionPageResponse,
    AdminRoleUpdateRequest,
    AdminRuntimeSettingsResponse,
    AdminRuntimeSettingsUpdateRequest,
    AdminStatusUpdateRequest,
    AdminUserPageResponse,
    AdminUserResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    CreditCodeBatchCreateRequest,
    CreditCodeBatchResponse,
    CreditLedgerEntryResponse,
    CreditPricingResponse,
    CreditRedemptionRequest,
    CreditRedemptionResponse,
    CreditSummaryResponse,
    DataExportCreateRequest,
    DataExportResponse,
    DeactivateAccountRequest,
    DeactivateAccountResponse,
    DeleteAccountRequest,
    DeleteAccountResponse,
    PasswordResetConsumeRequest,
    PasswordResetConsumeResponse,
    PasswordResetLinkResponse,
    RevokeSessionResponse,
    UpdateModelDataAuthorizationRequest,
    UpdatePreferencesRequest,
    UpdateProfileRequest,
)
from qunxue_api.api.contracts.common import ErrorResponse
from qunxue_api.api.dependencies import CurrentSessionDependency
from qunxue_api.api.routes.stubs import IdempotencyKey
from qunxue_api.modules.account_management import AccountManagementService
from qunxue_api.modules.billing import (
    INPUT_TOKENS_PER_CREDIT,
    OUTPUT_TOKENS_PER_CREDIT,
    WELCOME_GRANT,
    CreditService,
)


def get_account_management_service(request: Request) -> Iterator[AccountManagementService]:
    with request.app.state.account_management_service_scope() as service:
        yield service


AccountManagementServiceDependency = Annotated[
    AccountManagementService,
    Depends(get_account_management_service),
]


def get_credit_service(request: Request) -> Iterator[CreditService]:
    with request.app.state.credit_service_scope() as service:
        yield service


CreditServiceDependency = Annotated[CreditService, Depends(get_credit_service)]

account_router = APIRouter(
    prefix="/api/account",
    tags=["account"],
    responses={422: {"model": ErrorResponse}},
)
admin_router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)


def _runtime_config_path(request: Request):
    configured = os.environ.get("QUNXUE_CANONICAL_CONFIG_PATH")
    if configured:
        return configured
    candidate = "/root/qunxue-config/qunxue.env"
    if os.path.exists(candidate):
        return candidate
    return str(Path(__file__).resolve().parents[4] / ".env")


def _replace_env_values(path: str, values: dict[str, str]) -> None:
    with open(path, encoding="utf-8") as handle:
        lines = handle.readlines()
    seen = set()
    output = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in values:
            output.append(f"{key}={values[key]}\n")
            seen.add(key)
        else:
            output.append(line)
    for key, value in values.items():
        if key not in seen:
            output.append(f"{key}={value}\n")
    directory = os.path.dirname(path) or "."
    fd, temporary = tempfile.mkstemp(prefix="qunxue-config-", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.writelines(output)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@account_router.get("", operation_id="get_account", response_model=AccountResponse)
def get_account(
    current: CurrentSessionDependency,
    service: AccountManagementServiceDependency,
) -> AccountResponse:
    return AccountResponse.model_validate(service.get_account(current.user.user_id))


@account_router.get(
    "/credits",
    operation_id="get_account_credits",
    response_model=CreditSummaryResponse,
)
def get_account_credits(
    current: CurrentSessionDependency,
    service: CreditServiceDependency,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
) -> CreditSummaryResponse:
    summary = service.summary(
        user_id=current.user.user_id,
        offset=cursor,
        limit=limit,
    )
    return CreditSummaryResponse(
        balance=summary.balance,
        credit_limit=WELCOME_GRANT,
        grant_amount=WELCOME_GRANT,
        is_unlimited=summary.is_unlimited,
        pricing=CreditPricingResponse(
            input_tokens_per_credit=INPUT_TOKENS_PER_CREDIT,
            output_tokens_per_credit=OUTPUT_TOKENS_PER_CREDIT,
        ),
        entries=[CreditLedgerEntryResponse.model_validate(entry) for entry in summary.entries],
        total_entries=summary.total_entries,
        next_cursor=summary.next_cursor,
    )


@account_router.post(
    "/credit-redemptions",
    operation_id="redeem_account_credits",
    response_model=CreditRedemptionResponse,
)
def redeem_account_credits(
    payload: CreditRedemptionRequest,
    _idempotency_key: IdempotencyKey,
    current: CurrentSessionDependency,
    service: CreditServiceDependency,
) -> CreditRedemptionResponse:
    return CreditRedemptionResponse.model_validate(
        service.redeem(user_id=current.user.user_id, code=payload.code),
        from_attributes=True,
    )


@account_router.patch(
    "/profile",
    operation_id="update_account_profile",
    response_model=AccountResponse,
)
def update_account_profile(
    payload: UpdateProfileRequest,
    idempotency_key: IdempotencyKey,
    current: CurrentSessionDependency,
    service: AccountManagementServiceDependency,
) -> AccountResponse:
    return AccountResponse.model_validate(
        service.update_profile(
            user_id=current.user.user_id,
            display_name=payload.display_name,
            expected_version=payload.expected_version,
            idempotency_key=idempotency_key,
        )
    )


@account_router.patch(
    "/preferences",
    operation_id="update_account_preferences",
    response_model=AccountPreferencesResponse,
)
def update_account_preferences(
    payload: UpdatePreferencesRequest,
    idempotency_key: IdempotencyKey,
    current: CurrentSessionDependency,
    service: AccountManagementServiceDependency,
) -> AccountPreferencesResponse:
    return AccountPreferencesResponse.model_validate(
        service.update_preferences(
            user_id=current.user.user_id,
            locale=payload.locale,
            timezone=payload.timezone,
            research_updates_enabled=payload.research_updates_enabled,
            expected_version=payload.expected_version,
            idempotency_key=idempotency_key,
        )
    )


@account_router.patch(
    "/model-data-authorization",
    operation_id="update_model_data_authorization",
    response_model=AccountPreferencesResponse,
)
def update_model_data_authorization(
    payload: UpdateModelDataAuthorizationRequest,
    idempotency_key: IdempotencyKey,
    current: CurrentSessionDependency,
    service: AccountManagementServiceDependency,
) -> AccountPreferencesResponse:
    return AccountPreferencesResponse.model_validate(
        service.update_model_data_authorization(
            user_id=current.user.user_id,
            allowed=payload.allowed,
            policy_version=payload.policy_version,
            expected_version=payload.expected_version,
            idempotency_key=idempotency_key,
        )
    )


@account_router.get(
    "/sessions",
    operation_id="list_account_sessions",
    response_model=AccountSessionPageResponse,
)
def list_account_sessions(
    current: CurrentSessionDependency,
    service: AccountManagementServiceDependency,
) -> AccountSessionPageResponse:
    return AccountSessionPageResponse(
        items=service.list_sessions(
            user_id=current.user.user_id,
            current_session_id=current.session.session_id,
        )
    )


@account_router.post(
    "/sessions/{session_id}/revoke",
    operation_id="revoke_account_session",
    response_model=RevokeSessionResponse,
)
def revoke_account_session(
    session_id: UUID,
    idempotency_key: IdempotencyKey,
    current: CurrentSessionDependency,
    service: AccountManagementServiceDependency,
) -> RevokeSessionResponse:
    return RevokeSessionResponse.model_validate(
        service.revoke_session(
            user_id=current.user.user_id,
            current_session_id=current.session.session_id,
            session_id=session_id,
            idempotency_key=idempotency_key,
        )
    )


@account_router.post(
    "/password/change",
    operation_id="change_account_password",
    response_model=ChangePasswordResponse,
)
def change_account_password(
    payload: ChangePasswordRequest,
    idempotency_key: IdempotencyKey,
    current: CurrentSessionDependency,
    service: AccountManagementServiceDependency,
) -> ChangePasswordResponse:
    return ChangePasswordResponse.model_validate(
        service.change_password(
            user_id=current.user.user_id,
            current_session_id=current.session.session_id,
            current_password=payload.current_password,
            new_password=payload.new_password,
            revoke_other_sessions=payload.revoke_other_sessions,
            idempotency_key=idempotency_key,
        )
    )


@account_router.post(
    "/password-resets/consume",
    operation_id="consume_account_password_reset",
    response_model=PasswordResetConsumeResponse,
)
def consume_account_password_reset(
    payload: PasswordResetConsumeRequest,
    idempotency_key: IdempotencyKey,
    service: AccountManagementServiceDependency,
) -> PasswordResetConsumeResponse:
    return PasswordResetConsumeResponse.model_validate(
        service.consume_password_reset(
            token=payload.token,
            new_password=payload.new_password,
            idempotency_key=idempotency_key,
        )
    )


@account_router.post(
    "/data-exports",
    operation_id="create_account_data_export",
    response_model=DataExportResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_account_data_export(
    _payload: DataExportCreateRequest,
    idempotency_key: IdempotencyKey,
    current: CurrentSessionDependency,
    service: AccountManagementServiceDependency,
) -> DataExportResponse:
    return DataExportResponse.model_validate(
        service.create_export(
            user_id=current.user.user_id,
            idempotency_key=idempotency_key,
        )
    )


@account_router.get(
    "/data-exports/{export_id}",
    operation_id="get_account_data_export",
    response_model=DataExportResponse,
)
def get_account_data_export(
    export_id: UUID,
    current: CurrentSessionDependency,
    service: AccountManagementServiceDependency,
) -> DataExportResponse:
    return DataExportResponse.model_validate(
        service.get_export(user_id=current.user.user_id, export_id=export_id)
    )


@account_router.get(
    "/data-exports/{export_id}/download",
    operation_id="download_account_data_export",
)
def download_account_data_export(
    export_id: UUID,
    current: CurrentSessionDependency,
    service: AccountManagementServiceDependency,
) -> Response:
    payload = service.get_export_payload(
        user_id=current.user.user_id,
        export_id=export_id,
    )
    return Response(
        content=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": (
                f'attachment; filename="qunxue-account-export-{export_id}.json"'
            ),
            "Content-Type": "application/json; charset=utf-8",
            "X-Content-Type-Options": "nosniff",
        },
    )


@account_router.post(
    "/deactivate",
    operation_id="deactivate_account",
    response_model=DeactivateAccountResponse,
)
def deactivate_account(
    payload: DeactivateAccountRequest,
    idempotency_key: IdempotencyKey,
    response: Response,
    request: Request,
    current: CurrentSessionDependency,
    service: AccountManagementServiceDependency,
) -> DeactivateAccountResponse:
    result = service.deactivate_account(
        user_id=current.user.user_id,
        current_password=payload.current_password,
        reason=payload.reason,
        idempotency_key=idempotency_key,
    )
    _clear_session_cookie(response, request)
    return DeactivateAccountResponse.model_validate(result)


@account_router.post(
    "/delete",
    operation_id="delete_account",
    response_model=DeleteAccountResponse,
)
def delete_account(
    payload: DeleteAccountRequest,
    idempotency_key: IdempotencyKey,
    response: Response,
    request: Request,
    current: CurrentSessionDependency,
    service: AccountManagementServiceDependency,
) -> DeleteAccountResponse:
    result = service.delete_account(
        user_id=current.user.user_id,
        current_password=payload.current_password,
        confirmation_email=payload.confirmation_email,
        idempotency_key=idempotency_key,
    )
    _clear_session_cookie(response, request)
    return DeleteAccountResponse.model_validate(result)


@admin_router.get(
    "/runtime-settings",
    operation_id="get_admin_runtime_settings",
    response_model=AdminRuntimeSettingsResponse,
)
def get_admin_runtime_settings(
    current: CurrentSessionDependency,
    service: AccountManagementServiceDependency,
    request: Request,
) -> AdminRuntimeSettingsResponse:
    service.require_admin_access(current.user.user_id)
    settings = request.app.state.settings
    return AdminRuntimeSettingsResponse(
        model=settings.model_name or "",
        reasoning_effort=settings.model_reasoning_effort or "high",
        provider_base_url=settings.model_base_url or "",
    )


@admin_router.patch(
    "/runtime-settings",
    operation_id="update_admin_runtime_settings",
    response_model=AdminRuntimeSettingsResponse,
)
def update_admin_runtime_settings(
    payload: AdminRuntimeSettingsUpdateRequest,
    _idempotency_key: IdempotencyKey,
    current: CurrentSessionDependency,
    service: AccountManagementServiceDependency,
    request: Request,
) -> AdminRuntimeSettingsResponse:
    service.require_admin_access(current.user.user_id)
    path = _runtime_config_path(request)
    _replace_env_values(path, {
        "QUNXUE_MODEL_NAME": payload.model.strip(),
        "QUNXUE_MODEL_REASONING_EFFORT": payload.reasoning_effort,
    })
    subprocess.Popen(
        ["pm2", "restart", "qunxue-api"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return AdminRuntimeSettingsResponse(
        model=payload.model.strip(),
        reasoning_effort=payload.reasoning_effort,
        provider_base_url=request.app.state.settings.model_base_url or "",
        restart_required=True,
    )


@admin_router.get(
    "/users",
    operation_id="list_admin_users",
    response_model=AdminUserPageResponse,
)
def list_admin_users(
    current: CurrentSessionDependency,
    service: AccountManagementServiceDependency,
    query: str | None = Query(default=None, max_length=120),
    role: str | None = Query(default=None, pattern="^(member|admin)$"),
    account_status: str | None = Query(
        default=None,
        alias="status",
        pattern="^(active|disabled|deactivated)$",
    ),
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> AdminUserPageResponse:
    return AdminUserPageResponse.model_validate(
        service.list_users(
            actor_user_id=current.user.user_id,
            query=query,
            role=role,
            account_status=account_status,
            offset=cursor,
            limit=limit,
        )
    )


@admin_router.post(
    "/credit-redemption-codes",
    operation_id="create_admin_credit_redemption_codes",
    response_model=CreditCodeBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_admin_credit_redemption_codes(
    payload: CreditCodeBatchCreateRequest,
    idempotency_key: IdempotencyKey,
    current: CurrentSessionDependency,
    account_service: AccountManagementServiceDependency,
    credit_service: CreditServiceDependency,
) -> CreditCodeBatchResponse:
    account_service.require_admin_access(current.user.user_id)
    batch = credit_service.generate_redemption_codes(
        actor_user_id=current.user.user_id,
        batch_id=idempotency_key,
        count=payload.count,
        expires_in_days=payload.expires_in_days,
    )
    return CreditCodeBatchResponse(
        codes=list(batch.codes),
        points=batch.points,
        expires_at=batch.expires_at,
    )


@admin_router.patch(
    "/users/{user_id}/role",
    operation_id="update_admin_user_role",
    response_model=AdminUserResponse,
)
def update_admin_user_role(
    user_id: UUID,
    payload: AdminRoleUpdateRequest,
    idempotency_key: IdempotencyKey,
    current: CurrentSessionDependency,
    service: AccountManagementServiceDependency,
) -> AdminUserResponse:
    return AdminUserResponse.model_validate(
        service.update_user_role(
            actor_user_id=current.user.user_id,
            user_id=user_id,
            role=payload.role.value,
            expected_version=payload.expected_version,
            reason=payload.reason,
            idempotency_key=idempotency_key,
        )
    )


def _update_admin_status(
    *,
    user_id: UUID,
    payload: AdminStatusUpdateRequest,
    idempotency_key: str,
    current: CurrentSessionDependency,
    service: AccountManagementService,
    account_status: str,
) -> AdminUserResponse:
    return AdminUserResponse.model_validate(
        service.update_user_status(
            actor_user_id=current.user.user_id,
            user_id=user_id,
            account_status=account_status,
            expected_version=payload.expected_version,
            reason=payload.reason,
            idempotency_key=idempotency_key,
        )
    )


@admin_router.post(
    "/users/{user_id}/disable",
    operation_id="disable_admin_user",
    response_model=AdminUserResponse,
)
def disable_admin_user(
    user_id: UUID,
    payload: AdminStatusUpdateRequest,
    idempotency_key: IdempotencyKey,
    current: CurrentSessionDependency,
    service: AccountManagementServiceDependency,
) -> AdminUserResponse:
    return _update_admin_status(
        user_id=user_id,
        payload=payload,
        idempotency_key=idempotency_key,
        current=current,
        service=service,
        account_status="disabled",
    )


@admin_router.post(
    "/users/{user_id}/enable",
    operation_id="enable_admin_user",
    response_model=AdminUserResponse,
)
def enable_admin_user(
    user_id: UUID,
    payload: AdminStatusUpdateRequest,
    idempotency_key: IdempotencyKey,
    current: CurrentSessionDependency,
    service: AccountManagementServiceDependency,
) -> AdminUserResponse:
    return _update_admin_status(
        user_id=user_id,
        payload=payload,
        idempotency_key=idempotency_key,
        current=current,
        service=service,
        account_status="active",
    )


@admin_router.post(
    "/users/{user_id}/password-reset-links",
    operation_id="create_admin_password_reset",
    response_model=PasswordResetLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_admin_password_reset(
    user_id: UUID,
    idempotency_key: IdempotencyKey,
    current: CurrentSessionDependency,
    service: AccountManagementServiceDependency,
) -> PasswordResetLinkResponse:
    return PasswordResetLinkResponse.model_validate(
        service.create_password_reset(
            actor_user_id=current.user.user_id,
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
    )


@admin_router.get(
    "/audit-events",
    operation_id="list_account_audit_events",
    response_model=AccountAuditPageResponse,
)
def list_account_audit_events(
    current: CurrentSessionDependency,
    service: AccountManagementServiceDependency,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> AccountAuditPageResponse:
    return AccountAuditPageResponse.model_validate(
        service.list_audit_events(
            actor_user_id=current.user.user_id,
            offset=cursor,
            limit=limit,
        )
    )


def _clear_session_cookie(response: Response, request: Request) -> None:
    settings = request.app.state.settings
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )


routers = (account_router, admin_router)

__all__ = ["account_router", "admin_router", "routers"]
