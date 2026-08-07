from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import ErrorCode, ErrorDetail, ErrorResponse
from qunxue_api.api.contracts.matching import (
    AcknowledgePartialMatchRequest,
    ConfirmedTheoryPlanResponse,
    ConfirmTheoryPlanRequest,
    CreateMatchRunRequest,
    CreateTheoryDecisionsRequest,
    DeferredTheoryPlanResponse,
    DeferTheoryPlanRequest,
    MatchCandidatePageResponse,
    MatchRunResponse,
    RetryMatchCandidateRequest,
    TheoryCandidateResponse,
    TheoryDecisionPageResponse,
    TheoryDecisionSetResponse,
)
from qunxue_api.api.dependencies import (
    OwnedResearchTaskDependency,
    PhenomenonServiceDependency,
    get_current_session,
)
from qunxue_api.api.routes.stubs import IdempotencyKey, not_implemented_response

router = APIRouter(
    tags=["matching"],
    responses={422: {"model": ErrorResponse}},
    dependencies=[Depends(get_current_session)],
)


@router.post(
    "/api/research-tasks/{task_id}/match-runs",
    operation_id="create_match_run",
    response_model=MatchRunResponse,
    responses={409: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def create_match_run(
    task_id: UUID,
    _owned_task: OwnedResearchTaskDependency,
    payload: CreateMatchRunRequest,
    _idempotency_key: IdempotencyKey,
    phenomenon_service: PhenomenonServiceDependency,
) -> JSONResponse:
    if phenomenon_service.progress(task_id).confirmed is None:
        body = ErrorResponse(
            error=ErrorDetail(
                code=ErrorCode.PHENOMENON_UNCONFIRMED,
                message="Confirm the phenomenon before starting theory matching.",
                trace_id=str(uuid4()),
            )
        )
        return JSONResponse(status_code=409, content=body.model_dump(mode="json"))
    return not_implemented_response()


@router.get(
    "/api/match-runs/{match_run_id}",
    operation_id="get_match_run",
    response_model=MatchRunResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def get_match_run(match_run_id: UUID) -> JSONResponse:
    return not_implemented_response()


@router.get(
    "/api/match-runs/{match_run_id}/candidates",
    operation_id="list_match_candidates",
    response_model=MatchCandidatePageResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def list_match_candidates(
    match_run_id: UUID,
    cursor: str | None = None,
    limit: int = Query(default=4, ge=1, le=8),
) -> JSONResponse:
    return not_implemented_response()


@router.post(
    "/api/match-runs/{match_run_id}/candidates/{candidate_id}/retry",
    operation_id="retry_match_candidate",
    response_model=TheoryCandidateResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        501: {"model": ErrorResponse},
    },
)
def retry_match_candidate(
    match_run_id: UUID,
    candidate_id: UUID,
    payload: RetryMatchCandidateRequest,
    _idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return not_implemented_response()


@router.post(
    "/api/match-runs/{match_run_id}/partial-completion-acknowledgements",
    operation_id="acknowledge_partial_match",
    response_model=MatchRunResponse,
    responses={409: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def acknowledge_partial_match(
    match_run_id: UUID,
    payload: AcknowledgePartialMatchRequest,
    _idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return not_implemented_response()


@router.post(
    "/api/match-runs/{match_run_id}/decisions",
    operation_id="create_theory_decisions",
    response_model=TheoryDecisionSetResponse,
    responses={409: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def create_theory_decisions(
    match_run_id: UUID,
    payload: CreateTheoryDecisionsRequest,
    _idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return not_implemented_response()


@router.get(
    "/api/match-runs/{match_run_id}/decisions",
    operation_id="list_theory_decisions",
    response_model=TheoryDecisionPageResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def list_theory_decisions(
    match_run_id: UUID,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> JSONResponse:
    return not_implemented_response()


@router.post(
    "/api/match-runs/{match_run_id}/defer",
    operation_id="defer_theory_plan",
    response_model=DeferredTheoryPlanResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        501: {"model": ErrorResponse},
    },
)
def defer_theory_plan(
    match_run_id: UUID,
    payload: DeferTheoryPlanRequest,
    _idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return not_implemented_response()


@router.post(
    "/api/decision-sets/{decision_set_id}/confirm",
    operation_id="confirm_theory_plan",
    response_model=ConfirmedTheoryPlanResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        501: {"model": ErrorResponse},
    },
)
def confirm_theory_plan(
    decision_set_id: UUID,
    payload: ConfirmTheoryPlanRequest,
    _idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return not_implemented_response()
