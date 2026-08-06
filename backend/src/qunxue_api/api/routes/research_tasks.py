from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, status
from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import ErrorDetail, ErrorResponse
from qunxue_api.api.contracts.research_tasks import (
    CreateResearchTaskRequest,
    ResearchTaskResponse,
)
from qunxue_api.api.dependencies import ResearchTaskServiceDependency
from qunxue_api.modules.research_intake import (
    ResearchIntakeValidationError,
    ResearchTaskNotFound,
)

router = APIRouter(prefix='/api/research-tasks', tags=['research-tasks'])


def _unexpected_service_failure_response() -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(
            code='internal_server_error',
            message='系统暂时无法处理请求。',
            trace_id=str(uuid4()),
        )
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=body.model_dump(mode='json'),
    )


@router.post(
    '',
    operation_id='create_research_task',
    response_model=ResearchTaskResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        422: {'model': ErrorResponse},
        500: {'model': ErrorResponse},
    },
)
def create_research_task(
    payload: CreateResearchTaskRequest,
    service: ResearchTaskServiceDependency,
    idempotency_key: Annotated[
        str,
        Header(alias='Idempotency-Key', min_length=8, max_length=128),
    ],
) -> ResearchTaskResponse | JSONResponse:
    try:
        task = service.create(
            idempotency_key=idempotency_key,
            phenomenon=payload.phenomenon,
            research_intent=payload.research_intent,
            context=payload.context,
        )
    except ResearchIntakeValidationError:
        raise
    except Exception:
        return _unexpected_service_failure_response()
    return ResearchTaskResponse.from_domain(task)


@router.get(
    '/{task_id}',
    operation_id='get_research_task',
    response_model=ResearchTaskResponse,
    responses={
        404: {'model': ErrorResponse},
        500: {'model': ErrorResponse},
    },
)
def get_research_task(
    task_id: UUID,
    service: ResearchTaskServiceDependency,
) -> ResearchTaskResponse | JSONResponse:
    try:
        task = service.get(task_id)
    except ResearchTaskNotFound:
        raise
    except Exception:
        return _unexpected_service_failure_response()
    return ResearchTaskResponse.from_domain(task)