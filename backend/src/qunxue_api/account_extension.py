import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from qunxue_api.adapters.sqlite.account_management_repository import (
    SqliteAccountRepository,
)
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.identity_repository import SqliteIdentityRepository
from qunxue_api.api.contracts.common import ErrorCode, ErrorDetail, ErrorResponse
from qunxue_api.api.routes.account_management import routers
from qunxue_api.modules.account_management import (
    AccountCapabilityUnavailable,
    AccountConflict,
    AccountForbidden,
    AccountManagementError,
    AccountManagementService,
    AccountNotFound,
    ExpiredAccountToken,
    IdempotencyConflict,
    InvalidConfirmation,
    InvalidCurrentPassword,
    InvalidPasswordReset,
    ProvisionedAdministratorProtected,
)
from qunxue_api.modules.identity import PasswordHasher, User

logger = logging.getLogger(__name__)


def install_account_management(
    app: FastAPI,
    *,
    database: Database,
    password_hasher: PasswordHasher,
    initial_admin_email: str | None = None,
    initial_admin_password: str | None = None,
) -> None:
    """Install D's isolated router/service adapter at the composition boundary.

    The shared application composition root calls this once. Keeping the
    installer here lets account work ship without taking ownership of App/router.
    """

    if getattr(app.state, "account_management_installed", False):
        return

    configured_admin_email = (
        initial_admin_email or app.state.settings.account_initial_admin_email
    ).strip().casefold()
    configured_admin_password = initial_admin_password
    if configured_admin_password is None:
        setting = app.state.settings.account_initial_admin_password
        if setting is not None:
            configured_admin_password = setting.get_secret_value()
    if not configured_admin_email or not configured_admin_password:
        raise RuntimeError(
            "QUNXUE_ACCOUNT_INITIAL_ADMIN_PASSWORD must be configured before "
            "installing account management"
        )
    if len(configured_admin_password) < 12:
        raise RuntimeError("the initial administrator password must have 12+ characters")

    _provision_initial_administrator(
        database=database,
        password_hasher=password_hasher,
        email=configured_admin_email,
        password=configured_admin_password,
    )

    @contextmanager
    def service_scope() -> Iterator[AccountManagementService]:
        with database.session() as session:
            yield AccountManagementService(
                SqliteAccountRepository(session),
                password_hasher,
                password_reset_signing_secret=configured_admin_password,
            )

    app.state.account_management_service_scope = service_scope
    app.state.account_management_installed = True
    for router in routers:
        app.include_router(router)

    @app.exception_handler(AccountManagementError)
    async def handle_account_management_error(
        request: Request,
        error: AccountManagementError,
    ) -> JSONResponse:
        if error.audit_action is not None:
            try:
                with database.session() as session:
                    SqliteAccountRepository(session).add_audit_event(
                        actor_user_id=error.audit_actor_user_id,
                        target_user_id=error.audit_target_user_id,
                        action=error.audit_action,
                        outcome="denied",
                        details=error.audit_details or {},
                        now=datetime.now(UTC),
                        ip_address=request.client.host if request.client else None,
                        user_agent=request.headers.get("user-agent"),
                    )
            except Exception:
                logger.exception("Unable to persist a denied account audit event")
        if isinstance(error, AccountForbidden):
            response_status = status.HTTP_403_FORBIDDEN
            code = ErrorCode.FORBIDDEN
        elif isinstance(error, AccountNotFound):
            response_status = status.HTTP_404_NOT_FOUND
            code = ErrorCode.NOT_FOUND
        elif isinstance(error, InvalidCurrentPassword):
            response_status = status.HTTP_401_UNAUTHORIZED
            code = ErrorCode.REAUTHENTICATION_REQUIRED
        elif isinstance(error, (InvalidPasswordReset, ExpiredAccountToken)):
            response_status = status.HTTP_410_GONE
            code = (
                ErrorCode.TOKEN_EXPIRED
                if isinstance(error, ExpiredAccountToken)
                else ErrorCode.PASSWORD_RESET_INVALID
            )
        elif isinstance(error, InvalidConfirmation):
            response_status = status.HTTP_422_UNPROCESSABLE_CONTENT
            code = ErrorCode.VALIDATION_ERROR
        elif isinstance(error, AccountCapabilityUnavailable):
            response_status = status.HTTP_503_SERVICE_UNAVAILABLE
            code = ErrorCode.CAPABILITY_UNAVAILABLE
        elif isinstance(error, (IdempotencyConflict, AccountConflict)):
            response_status = status.HTTP_409_CONFLICT
            if isinstance(error, IdempotencyConflict):
                code = ErrorCode.IDEMPOTENCY_CONFLICT
            elif isinstance(error, ProvisionedAdministratorProtected):
                code = ErrorCode.PROVISIONED_ADMINISTRATOR_PROTECTED
            else:
                code = ErrorCode.CONFLICT
        else:
            response_status = status.HTTP_400_BAD_REQUEST
            code = ErrorCode.VALIDATION_ERROR
        body = ErrorResponse(
            error=ErrorDetail(code=code, message=str(error), trace_id=str(uuid4()))
        )
        return JSONResponse(
            status_code=response_status,
            content=body.model_dump(mode="json"),
        )


def _provision_initial_administrator(
    *,
    database: Database,
    password_hasher: PasswordHasher,
    email: str,
    password: str,
) -> None:
    now = datetime.now(UTC)
    with database.session() as session:
        accounts = SqliteAccountRepository(session)
        provisioned_user_id = accounts.lock_initial_admin_provisioning()
        if provisioned_user_id is not None:
            account = accounts.get_account(provisioned_user_id)
            if (
                account is None
                or account["email"] != email
                or account["role"] != "admin"
                or account["status"] != "active"
            ):
                raise RuntimeError(
                    "the configured initial administrator no longer matches "
                    "the provisioned account"
                )
            return

        password_hash = password_hasher.hash(password)
        identities = SqliteIdentityRepository(session)
        user = identities.get_user_by_email(email)
        if user is None:
            user = identities.add_user(
                User(
                    user_id=uuid4(),
                    email=email,
                    password_hash=password_hash,
                    display_name=None,
                    created_at=now,
                    updated_at=now,
                )
            )
        accounts.provision_initial_admin(
            user_id=user.user_id,
            password_hash=password_hash,
            now=now,
        )
        accounts.add_audit_event(
            actor_user_id=user.user_id,
            target_user_id=user.user_id,
            action="admin.provisioned",
            outcome="succeeded",
            details={"source": "deployment_configuration"},
            now=now,
        )


__all__ = ["install_account_management"]
