from uuid import UUID

from fastapi import APIRouter, status

from qunxue_api.api.contracts.common import ErrorResponse
from qunxue_api.api.contracts.research_tasks import (
    CreateResearchTaskRequest,
    ResearchTaskResponse,
)
from qunxue_api.api.dependencies import ResearchTaskServiceDependency

router = APIRouter(prefix="/api/research-tasks", tags=["research-tasks"])


@router.post(
    "",
    operation_id="create_research_task",
    response_model=ResearchTaskResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def create_research_task(
    payload: CreateResearchTaskRequest,
    service: ResearchTaskServiceDependency,
) -> ResearchTaskResponse:
    task = service.create(
        phenomenon=payload.phenomenon,
        research_intent=payload.research_intent,
        context=payload.context,
    )
    return ResearchTaskResponse.from_domain(task)


@router.get(
    "/{task_id}",
    operation_id="get_research_task",
    response_model=ResearchTaskResponse,
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def get_research_task(
    task_id: UUID,
    service: ResearchTaskServiceDependency,
) -> ResearchTaskResponse:
    return ResearchTaskResponse.from_domain(service.get(task_id))
