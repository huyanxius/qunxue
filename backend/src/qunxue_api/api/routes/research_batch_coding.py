from uuid import UUID, uuid4

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import ErrorCode, ErrorDetail, ErrorResponse
from qunxue_api.api.contracts.research_batch_coding import BatchCodingRunResponse
from qunxue_api.api.dependencies import (
    CurrentSessionDependency,
    OwnedResearchTaskDependency,
    ResearchBatchCodingApplicationDependency,
)
from qunxue_api.api.routes.stubs import IdempotencyKey

router = APIRouter(
    prefix="/api/research-tasks/{task_id}/batch-coding", tags=["research-batch-coding"]
)


def _error(code: ErrorCode, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error=ErrorDetail(code=code, message=message, trace_id=str(uuid4()))
        ).model_dump(mode="json"),
    )


@router.post(
    "",
    operation_id="startResearchBatchCoding",
    response_model=BatchCodingRunResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def start_batch_coding(
    task_id: UUID,
    material_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchBatchCodingApplicationDependency,
    idempotency_key: IdempotencyKey,
) -> BatchCodingRunResponse | JSONResponse:
    try:
        value = application.start(
            user_id=current.user.user_id,
            task_id=task_id,
            material_id=material_id,
            idempotency_key=idempotency_key,
        )
    except LookupError:
        return _error(ErrorCode.RESEARCH_MATERIAL_NOT_FOUND, "材料不存在或尚未完成解析。", 404)
    except ValueError as error:
        return _error(ErrorCode.VALIDATION_ERROR, str(error), 422)
    return BatchCodingRunResponse.from_domain(value)


@router.get(
    "/{run_id}",
    operation_id="getResearchBatchCoding",
    response_model=BatchCodingRunResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def get_batch_coding(
    task_id: UUID,
    run_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchBatchCodingApplicationDependency,
) -> BatchCodingRunResponse | JSONResponse:
    try:
        value = application.get(user_id=current.user.user_id, task_id=task_id, run_id=run_id)
    except LookupError:
        return _error(ErrorCode.NOT_FOUND, "批量编码批次不存在。", 404)
    return BatchCodingRunResponse.from_domain(value)


@router.post(
    "/{run_id}/retry",
    operation_id="retryResearchBatchCoding",
    response_model=BatchCodingRunResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def retry_batch_coding(
    task_id: UUID,
    run_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchBatchCodingApplicationDependency,
    _idempotency_key: IdempotencyKey,
) -> BatchCodingRunResponse | JSONResponse:
    try:
        value = application.retry(user_id=current.user.user_id, task_id=task_id, run_id=run_id)
    except LookupError:
        return _error(ErrorCode.NOT_FOUND, "批量编码批次不存在。", 404)
    except ValueError as error:
        return _error(ErrorCode.VALIDATION_ERROR, str(error), 422)
    return BatchCodingRunResponse.from_domain(value)
