from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, status

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
