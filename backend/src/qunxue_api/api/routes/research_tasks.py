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
from qunxue_api.modules.research_intake import (
    PhenomenonProgress,
    ResearchTask,
    ResearchTaskStatus,
)

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
        seed_theory_id=payload.seed_theory_id,
        seed_theory_name=payload.seed_theory_name,
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
    navigation_by_status = {
        ResearchTaskStatus.DRAFT: (
            ResearchTaskLifecycleStatus.DRAFT,
            ResearchTaskStage.PHENOMENON_INPUT,
            ResearchTaskNavigationAction.SUBMIT_PHENOMENON,
        ),
        ResearchTaskStatus.PHENOMENON_CONFIRMED: (
            ResearchTaskLifecycleStatus.IN_PROGRESS,
            ResearchTaskStage.THEORY_MATCHING,
            ResearchTaskNavigationAction.START_MATCHING,
        ),
        ResearchTaskStatus.MATCH_GENERATING: (
            ResearchTaskLifecycleStatus.IN_PROGRESS,
            ResearchTaskStage.THEORY_MATCHING,
            ResearchTaskNavigationAction.REVIEW_THEORY_CANDIDATES,
        ),
        ResearchTaskStatus.DECISIONS_RECORDED: (
            ResearchTaskLifecycleStatus.IN_PROGRESS,
            ResearchTaskStage.THEORY_DECISION,
            ResearchTaskNavigationAction.CONFIRM_THEORY_PLAN,
        ),
        ResearchTaskStatus.FRAMEWORK_DRAFT: (
            ResearchTaskLifecycleStatus.IN_PROGRESS,
            ResearchTaskStage.FRAMEWORK_DRAFTING,
            ResearchTaskNavigationAction.REVIEW_FRAMEWORK,
        ),
        ResearchTaskStatus.FRAMEWORK_CONFIRMED: (
            ResearchTaskLifecycleStatus.COMPLETED,
            ResearchTaskStage.COMPLETED,
            ResearchTaskNavigationAction.EXPORT,
        ),
    }
    lifecycle_status, current_stage, action = navigation_by_status[task.status]
    if task.status is ResearchTaskStatus.DRAFT and progress.candidate is not None:
        lifecycle_status = ResearchTaskLifecycleStatus.IN_PROGRESS
        current_stage = ResearchTaskStage.PHENOMENON_CONFIRMATION
        action = ResearchTaskNavigationAction.CONFIRM_PHENOMENON
    phenomenon_summary = None
    if (
        task.phenomenon_query_id is not None
        and task.phenomenon_version is not None
        and task.phenomenon_summary is not None
    ):
        phenomenon_summary = ResearchTaskPhenomenonSummaryResponse(
            phenomenon_query_id=task.phenomenon_query_id,
            version=task.phenomenon_version,
            phenomenon=task.phenomenon_summary,
            research_intent=task.phenomenon_research_intent,
        )

    return ResearchTaskNavigationResponse(
        task_id=task.task_id,
        entry_type=task.entry_type,
        status=lifecycle_status,
        current_stage=current_stage,
        version=task.version,
        allowed_actions=[action],
        seed_theory_id=task.seed_theory_id,
        seed_theory_name=task.seed_theory_name,
        phenomenon_summary=phenomenon_summary,
        adopted_theory_count=task.adopted_theory_count,
        current_phenomenon_candidate_id=(
            task.current_phenomenon_candidate_id
            or (progress.candidate.candidate_id if progress.candidate else None)
        ),
        current_match_run_id=task.current_match_run_id,
        current_framework_id=task.current_framework_id,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )
