from uuid import UUID, uuid4

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import ErrorCode, ErrorDetail, ErrorResponse
from qunxue_api.api.contracts.research_method import (
    ConfirmMethodPlanRequest,
    CreateMethodPlanRequest,
    MethodPlanResponse,
    MethodPlanSectionContract,
    MethodPlanVersionListResponse,
    ResolveMethodPlanReviewRequest,
    RestoreMethodPlanRequest,
    ReviewMethodPlanRequest,
    UpdateMethodPlanRequest,
)
from qunxue_api.api.dependencies import (
    CurrentSessionDependency,
    OwnedResearchTaskDependency,
    ResearchMethodPlanApplicationDependency,
)
from qunxue_api.api.routes.stubs import IdempotencyKey
from qunxue_api.modules.research_method import MethodPlanSection

router = APIRouter(tags=["research-method-plans"], responses={422: {"model": ErrorResponse}})


def _error(code: ErrorCode, message: str, status_code: int = 409) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message, trace_id=str(uuid4())))
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def _mutation_error(error: ValueError) -> JSONResponse:
    message = str(error)
    code = (
        ErrorCode.IDEMPOTENCY_CONFLICT
        if "Idempotency-Key" in message
        else ErrorCode.VALIDATION_ERROR
    )
    return _error(code, message)


@router.post(
    "/api/research-tasks/{task_id}/method-plans",
    operation_id="create_method_plan",
    response_model=MethodPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_method_plan(
    task_id: UUID,
    task: OwnedResearchTaskDependency,
    payload: CreateMethodPlanRequest,
    current: CurrentSessionDependency,
    application: ResearchMethodPlanApplicationDependency,
    _idempotency_key: IdempotencyKey,
) -> MethodPlanResponse | JSONResponse:
    try:
        value = application.create(
            user_id=current.user.user_id,
            task=task,
            framework_id=payload.framework_id,
            theory_plan_id=payload.theory_plan_id,
            method_kind=payload.method_kind,
            idempotency_key=_idempotency_key,
        )
    except LookupError as error:
        return _error(ErrorCode.NOT_FOUND, str(error), 404)
    except ValueError as error:
        return _mutation_error(error)
    return MethodPlanResponse.from_domain(value)


@router.get(
    "/api/research-tasks/{task_id}/method-plans/current",
    operation_id="get_current_method_plan",
    response_model=MethodPlanResponse | None,
)
def get_current_method_plan(
    task_id: UUID,
    task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchMethodPlanApplicationDependency,
) -> MethodPlanResponse | None:
    value = application.latest_for_task(user_id=current.user.user_id, task=task)
    return MethodPlanResponse.from_domain(value) if value else None


@router.get(
    "/api/method-plans/{plan_id}",
    operation_id="get_method_plan",
    response_model=MethodPlanResponse,
)
def get_method_plan(
    plan_id: UUID,
    current: CurrentSessionDependency,
    application: ResearchMethodPlanApplicationDependency,
) -> MethodPlanResponse | JSONResponse:
    try:
        return MethodPlanResponse.from_domain(
            application.get(user_id=current.user.user_id, plan_id=plan_id)
        )
    except LookupError:
        return _error(ErrorCode.NOT_FOUND, "MethodPlan not found.", 404)


@router.get(
    "/api/method-plans/{plan_id}/versions",
    operation_id="list_method_plan_versions",
    response_model=MethodPlanVersionListResponse,
)
def list_method_plan_versions(
    plan_id: UUID,
    current: CurrentSessionDependency,
    application: ResearchMethodPlanApplicationDependency,
) -> MethodPlanVersionListResponse | JSONResponse:
    try:
        values = application.versions(user_id=current.user.user_id, plan_id=plan_id)
    except LookupError:
        return _error(ErrorCode.NOT_FOUND, "MethodPlan not found.", 404)
    return MethodPlanVersionListResponse(
        plan_id=plan_id, items=[MethodPlanResponse.from_domain(item) for item in values]
    )


@router.patch(
    "/api/method-plans/{plan_id}",
    operation_id="update_method_plan",
    response_model=MethodPlanResponse,
)
def update_method_plan(
    plan_id: UUID,
    payload: UpdateMethodPlanRequest,
    current: CurrentSessionDependency,
    application: ResearchMethodPlanApplicationDependency,
    _idempotency_key: IdempotencyKey,
) -> MethodPlanResponse | JSONResponse:
    try:
        value = application.revise(
            user_id=current.user.user_id,
            plan_id=plan_id,
            expected_version=payload.expected_version,
            method_kind=payload.method_kind,
            rationale=payload.rationale,
            change_summary=payload.change_summary,
            sections=tuple(_section(item) for item in payload.sections),
            idempotency_key=_idempotency_key,
        )
    except LookupError:
        return _error(ErrorCode.NOT_FOUND, "MethodPlan not found.", 404)
    except ValueError as error:
        return _mutation_error(error)
    return MethodPlanResponse.from_domain(value)


@router.post(
    "/api/method-plans/{plan_id}/reviews",
    operation_id="review_method_plan",
    response_model=MethodPlanResponse,
)
def review_method_plan(
    plan_id: UUID,
    payload: ReviewMethodPlanRequest,
    current: CurrentSessionDependency,
    application: ResearchMethodPlanApplicationDependency,
    _idempotency_key: IdempotencyKey,
) -> MethodPlanResponse | JSONResponse:
    try:
        value = application.review(
            user_id=current.user.user_id,
            plan_id=plan_id,
            expected_version=payload.expected_version,
            note=payload.note,
            blocking=payload.blocking,
            idempotency_key=_idempotency_key,
        )
    except LookupError:
        return _error(ErrorCode.NOT_FOUND, "MethodPlan not found.", 404)
    except ValueError as error:
        return _mutation_error(error)
    return MethodPlanResponse.from_domain(value)


@router.post(
    "/api/method-plans/{plan_id}/reviews/{review_id}/resolve",
    operation_id="resolve_method_plan_review",
    response_model=MethodPlanResponse,
)
def resolve_method_plan_review(
    plan_id: UUID,
    review_id: UUID,
    payload: ResolveMethodPlanReviewRequest,
    current: CurrentSessionDependency,
    application: ResearchMethodPlanApplicationDependency,
    _idempotency_key: IdempotencyKey,
) -> MethodPlanResponse | JSONResponse:
    try:
        value = application.resolve_review(
            user_id=current.user.user_id,
            plan_id=plan_id,
            review_id=review_id,
            expected_version=payload.expected_version,
            reason=payload.reason,
            idempotency_key=_idempotency_key,
        )
    except LookupError:
        return _error(ErrorCode.NOT_FOUND, "MethodPlan or review not found.", 404)
    except ValueError as error:
        return _mutation_error(error)
    return MethodPlanResponse.from_domain(value)


@router.post(
    "/api/method-plans/{plan_id}/confirm",
    operation_id="confirm_method_plan",
    response_model=MethodPlanResponse,
)
def confirm_method_plan(
    plan_id: UUID,
    payload: ConfirmMethodPlanRequest,
    current: CurrentSessionDependency,
    application: ResearchMethodPlanApplicationDependency,
    _idempotency_key: IdempotencyKey,
) -> MethodPlanResponse | JSONResponse:
    try:
        value = application.confirm(
            user_id=current.user.user_id,
            plan_id=plan_id,
            expected_version=payload.expected_version,
            reason=payload.reason,
            idempotency_key=_idempotency_key,
        )
    except LookupError:
        return _error(ErrorCode.NOT_FOUND, "MethodPlan not found.", 404)
    except ValueError as error:
        return _mutation_error(error)
    return MethodPlanResponse.from_domain(value)


@router.post(
    "/api/method-plans/{plan_id}/restore",
    operation_id="restore_method_plan",
    response_model=MethodPlanResponse,
)
def restore_method_plan(
    plan_id: UUID,
    payload: RestoreMethodPlanRequest,
    current: CurrentSessionDependency,
    application: ResearchMethodPlanApplicationDependency,
    _idempotency_key: IdempotencyKey,
) -> MethodPlanResponse | JSONResponse:
    try:
        value = application.restore(
            user_id=current.user.user_id,
            plan_id=plan_id,
            source_version=payload.source_version,
            expected_version=payload.expected_version,
            reason=payload.reason,
            idempotency_key=_idempotency_key,
        )
    except LookupError:
        return _error(ErrorCode.NOT_FOUND, "MethodPlan not found.", 404)
    except ValueError as error:
        return _mutation_error(error)
    return MethodPlanResponse.from_domain(value)


def _section(item: MethodPlanSectionContract) -> MethodPlanSection:
    return MethodPlanSection(
        key=item.key, title=item.title, content=item.content, source=item.source
    )
