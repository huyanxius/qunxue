from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import ErrorResponse
from qunxue_api.api.contracts.frameworks import (
    AuditResolutionSetResponse,
    ConfirmedFrameworkResponse,
    ConfirmFrameworkRequest,
    CreateFrameworkRequest,
    FormalFrameworkExportResponse,
    FrameworkResponse,
    FrameworkReviewResponse,
    RetryFrameworkReviewRequest,
    StartFrameworkReviewRequest,
    SubmitAuditResolutionsRequest,
    UpdateFrameworkRequest,
)
from qunxue_api.api.dependencies import (
    OwnedResearchTaskDependency,
    get_current_session,
)
from qunxue_api.api.routes.stubs import IdempotencyKey, not_implemented_response

router = APIRouter(
    tags=["frameworks"],
    responses={422: {"model": ErrorResponse}},
    dependencies=[Depends(get_current_session)],
)


@router.post(
    "/api/research-tasks/{task_id}/frameworks",
    operation_id="create_framework",
    response_model=FrameworkResponse,
    responses={409: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def create_framework(
    task_id: UUID,
    _owned_task: OwnedResearchTaskDependency,
    payload: CreateFrameworkRequest,
    _idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return not_implemented_response()


@router.get(
    "/api/frameworks/{framework_id}",
    operation_id="get_framework",
    response_model=FrameworkResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def get_framework(framework_id: UUID) -> JSONResponse:
    return not_implemented_response()


@router.patch(
    "/api/frameworks/{framework_id}",
    operation_id="update_framework",
    response_model=FrameworkResponse,
    responses={409: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def update_framework(
    framework_id: UUID,
    payload: UpdateFrameworkRequest,
    _idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return not_implemented_response()


@router.post(
    "/api/frameworks/{framework_id}/reviews",
    operation_id="start_framework_review",
    response_model=FrameworkReviewResponse,
    responses={409: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def start_framework_review(
    framework_id: UUID,
    payload: StartFrameworkReviewRequest,
    _idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return not_implemented_response()


@router.get(
    "/api/frameworks/{framework_id}/reviews/{review_run_id}",
    operation_id="get_framework_review",
    response_model=FrameworkReviewResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def get_framework_review(framework_id: UUID, review_run_id: UUID) -> JSONResponse:
    return not_implemented_response()


@router.post(
    "/api/frameworks/{framework_id}/reviews/{review_run_id}/retry",
    operation_id="retry_framework_review",
    response_model=FrameworkReviewResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        501: {"model": ErrorResponse},
    },
)
def retry_framework_review(
    framework_id: UUID,
    review_run_id: UUID,
    payload: RetryFrameworkReviewRequest,
    _idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return not_implemented_response()


@router.post(
    "/api/frameworks/{framework_id}/audit-resolutions",
    operation_id="submit_audit_resolutions",
    response_model=AuditResolutionSetResponse,
    responses={409: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def submit_audit_resolutions(
    framework_id: UUID,
    payload: SubmitAuditResolutionsRequest,
    _idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return not_implemented_response()


@router.post(
    "/api/frameworks/{framework_id}/confirm",
    operation_id="confirm_framework",
    response_model=ConfirmedFrameworkResponse,
    responses={409: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def confirm_framework(
    framework_id: UUID,
    payload: ConfirmFrameworkRequest,
    _idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return not_implemented_response()


@router.get(
    "/api/frameworks/{framework_id}/export",
    operation_id="export_confirmed_framework",
    response_model=FormalFrameworkExportResponse,
    responses={409: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def export_confirmed_framework(framework_id: UUID) -> JSONResponse:
    return not_implemented_response()
