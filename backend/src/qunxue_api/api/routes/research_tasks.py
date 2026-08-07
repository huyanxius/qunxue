from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, status
from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import ErrorResponse
from qunxue_api.api.contracts.research_tasks import (
    CreateResearchTaskRequest,
    DeleteResearchTaskResponse,
    MarkdownExportResponse,
    ResearchTaskLifecycleStatus,
    ResearchTaskNavigationAction,
    ResearchTaskNavigationResponse,
    ResearchTaskPageResponse,
    ResearchTaskPhenomenonSummaryResponse,
    ResearchTaskResponse,
    ResearchTaskStage,
    ResearchTraceResponse,
)
from qunxue_api.api.dependencies import (
    CurrentSessionDependency,
    OwnedResearchTaskDependency,
    PhenomenonServiceDependency,
    ResearchTaskServiceDependency,
)
from qunxue_api.api.routes.stubs import IdempotencyKey, not_implemented_response
from qunxue_api.modules.research_intake import PhenomenonProgress, ResearchTask

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
    current: CurrentSessionDependency,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=128),
    ],
) -> ResearchTaskResponse:
    task = service.create(
        user_id=current.user.user_id,
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
    owned_task: OwnedResearchTaskDependency,
) -> ResearchTaskResponse:
    return ResearchTaskResponse.from_domain(owned_task)


@router.get(
    "",
    operation_id="list_research_tasks",
    response_model=ResearchTaskPageResponse,
    responses={401: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def list_research_tasks(
    service: ResearchTaskServiceDependency,
    phenomenon_service: PhenomenonServiceDependency,
    current: CurrentSessionDependency,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> ResearchTaskPageResponse:
    tasks = service.list_for_user(current.user.user_id, limit=limit)
    return ResearchTaskPageResponse(
        items=[
            _navigation_response(task, phenomenon_service.progress(task.task_id))
            for task in tasks
        ],
        next_cursor=None,
    )


@router.get(
    "/{task_id}/navigation",
    operation_id="get_research_task_navigation",
    response_model=ResearchTaskNavigationResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def get_research_task_navigation(
    task_id: UUID,
    owned_task: OwnedResearchTaskDependency,
    phenomenon_service: PhenomenonServiceDependency,
) -> ResearchTaskNavigationResponse:
    if owned_task.task_id != task_id:
        raise RuntimeError("owned task dependency returned a different task")
    return _navigation_response(owned_task, phenomenon_service.progress(task_id))


@router.delete(
    "/{task_id}",
    operation_id="delete_research_task",
    response_model=DeleteResearchTaskResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def delete_research_task(
    task_id: UUID,
    _idempotency_key: IdempotencyKey,
    service: ResearchTaskServiceDependency,
    current: CurrentSessionDependency,
) -> DeleteResearchTaskResponse:
    task = service.delete(task_id, user_id=current.user.user_id)
    return DeleteResearchTaskResponse(
        task_id=task.task_id,
        version=task.version + 1,
        allowed_actions=[],
        deleted=True,
    )


@router.get(
    "/{task_id}/trace",
    operation_id="get_research_trace",
    response_model=ResearchTraceResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def get_research_trace(
    task_id: UUID,
    _owned_task: OwnedResearchTaskDependency,
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
def export_research_trace(
    task_id: UUID,
    _owned_task: OwnedResearchTaskDependency,
) -> JSONResponse:
    return not_implemented_response()


def _navigation_response(
    task: ResearchTask,
    progress: PhenomenonProgress,
) -> ResearchTaskNavigationResponse:
    if progress.confirmed is not None:
        stage = ResearchTaskStage.THEORY_MATCHING
        status = ResearchTaskLifecycleStatus.IN_PROGRESS
        actions = [ResearchTaskNavigationAction.START_MATCHING]
        summary = ResearchTaskPhenomenonSummaryResponse(
            phenomenon_query_id=progress.confirmed.phenomenon_query_id,
            version=progress.confirmed.version,
            phenomenon=progress.confirmed.phenomenon,
            research_intent=progress.confirmed.research_intent,
        )
    elif progress.candidate is not None:
        stage = ResearchTaskStage.PHENOMENON_CONFIRMATION
        status = ResearchTaskLifecycleStatus.IN_PROGRESS
        actions = [ResearchTaskNavigationAction.CONFIRM_PHENOMENON]
        summary = None
    else:
        stage = ResearchTaskStage.PHENOMENON_INPUT
        status = ResearchTaskLifecycleStatus.DRAFT
        actions = [ResearchTaskNavigationAction.SUBMIT_PHENOMENON]
        summary = None

    return ResearchTaskNavigationResponse(
        task_id=task.task_id,
        entry_type=task.entry_type,
        status=status,
        current_stage=stage,
        version=task.version,
        allowed_actions=actions,
        seed_theory_id=None,
        phenomenon_summary=summary,
        adopted_theory_count=0,
        current_phenomenon_candidate_id=(
            progress.candidate.candidate_id if progress.candidate else None
        ),
        current_match_run_id=None,
        current_framework_id=None,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )
