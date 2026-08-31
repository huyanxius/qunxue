from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import ErrorResponse
from qunxue_api.api.contracts.research_tasks import (
    CreateResearchTaskRequest,
    DeleteResearchTaskResponse,
    MarkdownExportResponse,
    ResearchTaskLifecycleStatus,
    ResearchTaskNavigationAction,
    ResearchTaskNavigationBlockerResponse,
    ResearchTaskNavigationResponse,
    ResearchTaskNavigationRetryResponse,
    ResearchTaskPageResponse,
    ResearchTaskPhenomenonSummaryResponse,
    ResearchTaskResponse,
    ResearchTaskStage,
    ResearchTraceResponse,
    UpdateResearchTaskRequest,
)
from qunxue_api.api.dependencies import (
    CurrentSessionDependency,
    OwnedResearchTaskDependency,
    PhenomenonServiceDependency,
    ResearchTaskServiceDependency,
)
from qunxue_api.api.routes.stubs import IdempotencyKey, not_implemented_response
from qunxue_api.modules.knowledge_catalog import KnowledgeUsePurpose
from qunxue_api.modules.research_intake import (
    PhenomenonProgress,
    ProjectLifecycleStatus,
    ResearchCentralTool,
    ResearchEntryMode,
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
    request: Request,
    service: ResearchTaskServiceDependency,
    current: CurrentSessionDependency,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=128),
    ],
) -> ResearchTaskResponse:
    seed_theory_name = None
    if payload.seed_theory_id is not None:
        catalog = request.app.state.knowledge_catalog
        release = catalog.current_release(purpose=KnowledgeUsePurpose.BROWSE)
        try:
            seed_theory_name = catalog.get_theory_profile(
                theory_id=payload.seed_theory_id,
                release_id=release.knowledge_release_id,
            ).title
        except LookupError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Seed theory is not in the current knowledge release.",
            ) from error
    task = service.create(
        user_id=current.user.user_id,
        entry_type=payload.entry_type,
        idempotency_key=idempotency_key,
        entry_mode=payload.entry_mode,
        lifecycle_status=(
            ProjectLifecycleStatus.IN_PROGRESS
            if payload.entry_mode is ResearchEntryMode.EXISTING_RESEARCH
            else ProjectLifecycleStatus.DRAFT
        ),
        project_title=payload.project_title or seed_theory_name or "未命名研究",
        project_stage=payload.project_stage,
        method_orientation=payload.method_orientation,
        last_central_tool=(
            ResearchCentralTool.MATERIALS
            if payload.entry_mode is ResearchEntryMode.EXISTING_RESEARCH
            else ResearchCentralTool.PHENOMENON
        ),
        seed_theory_id=payload.seed_theory_id,
        seed_theory_name=seed_theory_name,
    )
    return ResearchTaskResponse.from_domain(task)


@router.patch(
    "/{task_id}",
    operation_id="update_research_task",
    response_model=ResearchTaskResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def update_research_task(
    task_id: UUID,
    payload: UpdateResearchTaskRequest,
    _owned_task: OwnedResearchTaskDependency,
    _idempotency_key: IdempotencyKey,
    service: ResearchTaskServiceDependency,
    current: CurrentSessionDependency,
) -> ResearchTaskResponse:
    updated = service.update_project(
        task_id,
        user_id=current.user.user_id,
        expected_version=payload.expected_version,
        lifecycle_status=payload.lifecycle_status,
        project_title=payload.project_title,
        project_stage=payload.project_stage,
        method_orientation=payload.method_orientation,
        last_central_tool=payload.last_central_tool,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Research task version changed; reload before updating the project.",
        )
    return ResearchTaskResponse.from_domain(updated)


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
    request: Request,
    service: ResearchTaskServiceDependency,
    phenomenon_service: PhenomenonServiceDependency,
    current: CurrentSessionDependency,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> ResearchTaskPageResponse:
    tasks = service.list_for_user(current.user.user_id, limit=limit)
    with request.app.state.research_navigation_match_reader_scope() as matches:
        return ResearchTaskPageResponse(
            items=[
                _navigation_response(
                    task,
                    phenomenon_service.progress(task.task_id),
                    match_status=_match_status(matches, task),
                )
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
    request: Request,
    owned_task: OwnedResearchTaskDependency,
    phenomenon_service: PhenomenonServiceDependency,
) -> ResearchTaskNavigationResponse:
    if owned_task.task_id != task_id:
        raise RuntimeError("owned task dependency returned a different task")
    with request.app.state.research_navigation_match_reader_scope() as matches:
        return _navigation_response(
            owned_task,
            phenomenon_service.progress(task_id),
            match_status=_match_status(matches, owned_task),
        )


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
    *,
    match_status: str | None = None,
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
        ResearchTaskStatus.THEORY_PLAN_CONFIRMED: (
            ResearchTaskLifecycleStatus.IN_PROGRESS,
            ResearchTaskStage.FRAMEWORK_DRAFTING,
            ResearchTaskNavigationAction.CREATE_FRAMEWORK,
        ),
        ResearchTaskStatus.FRAMEWORK_DRAFT: (
            ResearchTaskLifecycleStatus.IN_PROGRESS,
            ResearchTaskStage.FRAMEWORK_DRAFTING,
            ResearchTaskNavigationAction.REVIEW_FRAMEWORK,
        ),
        ResearchTaskStatus.FRAMEWORK_CONFIRMED: (
            ResearchTaskLifecycleStatus.IN_PROGRESS
            if getattr(task, "current_method_plan_status", None) != "confirmed"
            else ResearchTaskLifecycleStatus.COMPLETED,
            ResearchTaskStage.METHOD_DESIGN
            if getattr(task, "current_method_plan_status", None) != "confirmed"
            else ResearchTaskStage.COMPLETED,
            ResearchTaskNavigationAction.DESIGN_METHOD
            if getattr(task, "current_method_plan_status", None) != "confirmed"
            else ResearchTaskNavigationAction.EXPORT,
        ),
    }
    lifecycle_status, current_stage, action = navigation_by_status[task.status]
    if task.status is ResearchTaskStatus.DRAFT and progress.candidate is not None:
        lifecycle_status = ResearchTaskLifecycleStatus.IN_PROGRESS
        current_stage = ResearchTaskStage.PHENOMENON_CONFIRMATION
        action = ResearchTaskNavigationAction.CONFIRM_PHENOMENON
    if match_status == "no_reliable_candidate":
        action = ResearchTaskNavigationAction.START_MATCHING
    if task.lifecycle_status is ProjectLifecycleStatus.ARCHIVED:
        lifecycle_status = ResearchTaskLifecycleStatus.ARCHIVED
    elif (
        lifecycle_status is not ResearchTaskLifecycleStatus.COMPLETED
        and task.lifecycle_status is ProjectLifecycleStatus.IN_PROGRESS
    ):
        lifecycle_status = ResearchTaskLifecycleStatus.IN_PROGRESS
    stage_label = {
        ResearchTaskStage.PHENOMENON_INPUT: "现象输入",
        ResearchTaskStage.PHENOMENON_CONFIRMATION: "现象确认",
        ResearchTaskStage.THEORY_MATCHING: "理论匹配",
        ResearchTaskStage.THEORY_DECISION: "理论决策",
        ResearchTaskStage.FRAMEWORK_DRAFTING: "研究方案",
        ResearchTaskStage.FRAMEWORK_REVIEW: "方案确认",
        ResearchTaskStage.METHOD_DESIGN: "研究方法",
        ResearchTaskStage.COMPLETED: "已完成",
    }[current_stage]
    next_action_label = {
        ResearchTaskNavigationAction.SUBMIT_PHENOMENON: "补充研究现象",
        ResearchTaskNavigationAction.CONFIRM_PHENOMENON: "确认研究现象",
        ResearchTaskNavigationAction.START_MATCHING: "开始理论匹配",
        ResearchTaskNavigationAction.REVIEW_THEORY_CANDIDATES: "审阅理论候选",
        ResearchTaskNavigationAction.CONFIRM_THEORY_PLAN: "确认理论方案",
        ResearchTaskNavigationAction.CREATE_FRAMEWORK: "生成研究方案",
        ResearchTaskNavigationAction.REVIEW_FRAMEWORK: "审阅研究方案",
        ResearchTaskNavigationAction.CONFIRM_FRAMEWORK: "确认研究方案",
        ResearchTaskNavigationAction.DESIGN_METHOD: "制定研究方法",
        ResearchTaskNavigationAction.EXPORT: "查看并导出成果",
    }[action]
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
    workflow_resume_path = (
        f"/research/{task.task_id}/phenomenon"
        if task.status is ResearchTaskStatus.DRAFT
        else f"/research/{task.task_id}/match"
        if task.status
        in {
            ResearchTaskStatus.PHENOMENON_CONFIRMED,
            ResearchTaskStatus.MATCH_GENERATING,
            ResearchTaskStatus.DECISIONS_RECORDED,
        }
        else f"/research/{task.task_id}/method"
        if task.status is ResearchTaskStatus.FRAMEWORK_CONFIRMED
        else f"/research/{task.task_id}/framework"
    )
    resume_path = (
        f"/research/new?conversation_id={task.conversation_id}"
        if task.last_central_tool in {ResearchCentralTool.AGENT, ResearchCentralTool.RESEARCH_MAP}
        and task.conversation_id is not None
        else f"/research/materials?task_id={task.task_id}"
        if task.last_central_tool is ResearchCentralTool.MATERIALS
        else workflow_resume_path
    )
    blocker = None
    retry = None
    if match_status == "no_reliable_candidate":
        blocker = ResearchTaskNavigationBlockerResponse(
            code="no_reliable_candidate",
            message="固定知识发布中没有可正式采用的理论候选，请调整研究现象后重试。",
            recoverable=True,
            action=ResearchTaskNavigationAction.START_MATCHING,
        )
        retry = ResearchTaskNavigationRetryResponse(
            method="POST",
            href=f"/api/research-tasks/{task.task_id}/match-runs",
            action=ResearchTaskNavigationAction.START_MATCHING,
            label="重新匹配",
        )

    return ResearchTaskNavigationResponse(
        task_id=task.task_id,
        entry_type=task.entry_type,
        entry_mode=task.entry_mode,
        project_title=task.project_title,
        project_stage=task.project_stage,
        method_orientation=task.method_orientation,
        last_central_tool=task.last_central_tool,
        status=lifecycle_status,
        current_stage=current_stage,
        stage_label=stage_label,
        version=task.version,
        allowed_actions=[action],
        next_action_label=next_action_label,
        seed_theory_id=task.seed_theory_id,
        seed_theory_name=task.seed_theory_name,
        phenomenon_summary=phenomenon_summary,
        adopted_theory_count=task.adopted_theory_count,
        current_phenomenon_candidate_id=(
            task.current_phenomenon_candidate_id
            or (progress.candidate.candidate_id if progress.candidate else None)
        ),
        current_material_intake_run_id=task.current_material_intake_run_id,
        current_match_run_id=task.current_match_run_id,
        current_theory_plan_id=task.current_theory_plan_id,
        current_framework_id=task.current_framework_id,
        current_method_plan_id=getattr(task, "current_method_plan_id", None),
        current_method_plan_status=getattr(task, "current_method_plan_status", None),
        resume_path=resume_path,
        blocker=blocker,
        retry=retry,
        knowledge_release_id=task.knowledge_release_id,
        conversation_id=task.conversation_id,
        source_turn_id=task.source_turn_id,
        source_run_id=task.source_agent_run_id,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _match_status(matches, task: ResearchTask) -> str | None:
    if task.current_match_run_id is None:
        return None
    snapshot = matches.get(task.current_match_run_id)
    return snapshot.status.value if snapshot is not None else None
