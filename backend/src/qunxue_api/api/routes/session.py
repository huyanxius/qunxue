from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import ErrorResponse
from qunxue_api.api.contracts.session import (
    LoginSessionRequest,
    LogoutSessionResponse,
    RegisterSessionRequest,
    SessionResponse,
)
from qunxue_api.api.routes.stubs import IdempotencyKey, not_implemented_response

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
) -> JSONResponse:
    return not_implemented_response()


@router.post(
    "/login",
    operation_id="login_session",
    response_model=SessionResponse,
    responses={401: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def login_session(
    payload: LoginSessionRequest,
    _idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return not_implemented_response()


@router.post(
    "/logout",
    operation_id="logout_session",
    response_model=LogoutSessionResponse,
    responses={401: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def logout_session(_idempotency_key: IdempotencyKey) -> JSONResponse:
    return not_implemented_response()


@router.get(
    "",
    operation_id="get_current_session",
    response_model=SessionResponse,
    responses={401: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def get_current_session() -> JSONResponse:
    return not_implemented_response()
