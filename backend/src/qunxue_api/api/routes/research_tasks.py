from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, status
from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import ErrorResponse
from qunxue_api.api.contracts.research_tasks import (
    CreateResearchTaskRequest,
    DeleteResearchTaskResponse,
    MarkdownExportResponse,
    ResearchTaskPageResponse,
    ResearchTaskResponse,
    ResearchTraceResponse,
)
from qunxue_api.api.dependencies import ResearchTaskServiceDependency
from qunxue_api.api.routes.stubs import IdempotencyKey, not_implemented_response

router = APIRouter(
    prefix="/api/research-tasks",
    tags=["research-tasks"],
    responses={422: {"model": ErrorResponse}},
)


@router.post(
    "",
    operation_id="create_research_task",
    response_model=ResearchTaskResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}},
)
def create_research_task(
    payload: CreateResearchTaskRequest,
    service: ResearchTaskServiceDependency,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=128),
    ],
) -> ResearchTaskResponse:
    task = service.create(
        entry_type=payload.entry_type,
        idempotency_key=idempotency_key,
    )
    return ResearchTaskResponse.from_domain(task)


@router.get(
    "/{task_id}",
    operation_id="get_research_task",
    response_model=ResearchTaskResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_research_task(
    task_id: UUID,
    service: ResearchTaskServiceDependency,
) -> ResearchTaskResponse:
    return ResearchTaskResponse.from_domain(service.get(task_id))


@router.get(
    "",
    operation_id="list_research_tasks",
    response_model=ResearchTaskPageResponse,
    responses={401: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def list_research_tasks(
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> JSONResponse:
    return not_implemented_response()


@router.delete(
    "/{task_id}",
    operation_id="delete_research_task",
    response_model=DeleteResearchTaskResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def delete_research_task(
    task_id: UUID,
    _idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return not_implemented_response()


@router.get(
    "/{task_id}/trace",
    operation_id="get_research_trace",
    response_model=ResearchTraceResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def get_research_trace(
    task_id: UUID,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> JSONResponse:
    return not_implemented_response()


@router.get(
    "/{task_id}/export",
    operation_id="export_research_trace",
    response_model=MarkdownExportResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def export_research_trace(task_id: UUID) -> JSONResponse:
    return not_implemented_response()
