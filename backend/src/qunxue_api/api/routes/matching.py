from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import ErrorResponse
from qunxue_api.api.contracts.matching import (
    AcknowledgePartialMatchRequest,
    ConfirmedTheoryPlanResponse,
    ConfirmTheoryPlanRequest,
    CreateMatchRunRequest,
    CreateTheoryDecisionsRequest,
    MatchCandidatePageResponse,
    MatchRunResponse,
    RetryMatchCandidateRequest,
    TheoryCandidateResponse,
    TheoryDecisionPageResponse,
    TheoryDecisionSetResponse,
)
from qunxue_api.api.routes.stubs import IdempotencyKey, not_implemented_response

router = APIRouter(
    tags=["matching"],
    responses={422: {"model": ErrorResponse}},
)


@router.post(
    "/api/research-tasks/{task_id}/match-runs",
    operation_id="create_match_run",
    response_model=MatchRunResponse,
    responses={409: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def create_match_run(
    task_id: UUID,
    payload: CreateMatchRunRequest,
    _idempotency_key: IdempotencyKey,
) -> JSONResponse:
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
