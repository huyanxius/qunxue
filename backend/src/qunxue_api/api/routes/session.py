from fastapi import APIRouter, Request, Response, status

from qunxue_api.api.contracts.common import ErrorResponse
from qunxue_api.api.contracts.session import (
    LoginSessionRequest,
    LogoutSessionResponse,
    RegisterSessionRequest,
    SessionResponse,
    SessionStatus,
)
from qunxue_api.api.dependencies import (
    CurrentSessionDependency,
    IdentityServiceDependency,
)
from qunxue_api.api.routes.stubs import IdempotencyKey
from qunxue_api.modules.identity import AuthenticatedSession, SessionGrant

router = APIRouter(
    prefix="/api/session",
    tags=["session"],
    responses={422: {"model": ErrorResponse}},
)


@router.post(
    "/register",
    operation_id="register_session",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={401: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def register_session(
    payload: RegisterSessionRequest,
    _idempotency_key: IdempotencyKey,
    response: Response,
    request: Request,
    service: IdentityServiceDependency,
) -> SessionResponse:
    grant = service.register(
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
    )
    _set_session_cookie(response, request, grant)
    return _session_response(grant.authenticated)


@router.post(
    "/login",
    operation_id="login_session",
    response_model=SessionResponse,
    responses={401: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def login_session(
    payload: LoginSessionRequest,
    _idempotency_key: IdempotencyKey,
    response: Response,
    request: Request,
    service: IdentityServiceDependency,
) -> SessionResponse:
    grant = service.login(email=payload.email, password=payload.password)
    _set_session_cookie(response, request, grant)
    return _session_response(grant.authenticated)


@router.post(
    "/logout",
    operation_id="logout_session",
    response_model=LogoutSessionResponse,
    responses={401: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def logout_session(
    _idempotency_key: IdempotencyKey,
    response: Response,
    request: Request,
    service: IdentityServiceDependency,
) -> LogoutSessionResponse:
    settings = request.app.state.settings
    authenticated = service.logout(request.cookies.get(settings.session_cookie_name))
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )
    return LogoutSessionResponse(
        session_id=authenticated.session.session_id,
        status=SessionStatus.LOGGED_OUT,
        version=authenticated.session.version,
        allowed_actions=[],
    )


@router.get(
    "",
    operation_id="get_current_session",
    response_model=SessionResponse,
    responses={401: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def get_current_session(current: CurrentSessionDependency) -> SessionResponse:
    return _session_response(current)


def _session_response(current: AuthenticatedSession) -> SessionResponse:
    return SessionResponse(
        session_id=current.session.session_id,
        status=SessionStatus.ACTIVE,
        version=current.session.version,
        allowed_actions=["logout"],
        user={
            "user_id": current.user.user_id,
            "email": current.user.email,
            "display_name": current.user.display_name,
        },
        expires_at=current.session.expires_at,
    )


def _set_session_cookie(
    response: Response,
    request: Request,
    grant: SessionGrant,
) -> None:
    settings = request.app.state.settings
    response.set_cookie(
        settings.session_cookie_name,
        grant.credential,
        max_age=settings.session_ttl_seconds,
        expires=grant.authenticated.session.expires_at,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )
