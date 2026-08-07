from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import ErrorResponse
from qunxue_api.api.contracts.phenomena import (
    ConfirmPhenomenonCandidateRequest,
    DirectInputRequest,
    EntryInputResponse,
    ExtractPhenomenonCandidatesRequest,
    MaterialInputRequest,
    PhenomenonCandidatePageResponse,
    PhenomenonCandidateResponse,
    PhenomenonSnapshotPageResponse,
    PhenomenonSnapshotResponse,
    UpdatePhenomenonCandidateRequest,
)
from qunxue_api.api.routes.stubs import IdempotencyKey, not_implemented_response

router = APIRouter(
    prefix="/api/research-tasks/{task_id}",
    tags=["phenomena"],
    responses={422: {"model": ErrorResponse}},
)


@router.post(
    "/inputs/direct",
    operation_id="submit_direct_input",
    response_model=EntryInputResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def submit_direct_input(
    task_id: UUID,
    payload: DirectInputRequest,
    _idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return not_implemented_response()


@router.post(
    "/inputs/material",
    operation_id="submit_material_input",
    response_model=EntryInputResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def submit_material_input(
    task_id: UUID,
    payload: MaterialInputRequest,
    _idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return not_implemented_response()


@router.post(
    "/phenomenon-candidates",
    operation_id="extract_phenomenon_candidates",
    response_model=PhenomenonCandidatePageResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def extract_phenomenon_candidates(
    task_id: UUID,
    payload: ExtractPhenomenonCandidatesRequest,
    _idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return not_implemented_response()


@router.get(
    "/phenomenon-candidates/{candidate_id}",
    operation_id="get_phenomenon_candidate",
    response_model=PhenomenonCandidateResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def get_phenomenon_candidate(task_id: UUID, candidate_id: UUID) -> JSONResponse:
    return not_implemented_response()


@router.patch(
    "/phenomenon-candidates/{candidate_id}",
    operation_id="update_phenomenon_candidate",
    response_model=PhenomenonCandidateResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def update_phenomenon_candidate(
    task_id: UUID,
    candidate_id: UUID,
    payload: UpdatePhenomenonCandidateRequest,
    _idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return not_implemented_response()


@router.post(
    "/phenomenon-candidates/{candidate_id}/confirm",
    operation_id="confirm_phenomenon_candidate",
    response_model=PhenomenonSnapshotResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def confirm_phenomenon_candidate(
    task_id: UUID,
    candidate_id: UUID,
    payload: ConfirmPhenomenonCandidateRequest,
    _idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return not_implemented_response()


@router.get(
    "/phenomenon-snapshots",
    operation_id="list_phenomenon_snapshots",
    response_model=PhenomenonSnapshotPageResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def list_phenomenon_snapshots(
    task_id: UUID,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> JSONResponse:
    return not_implemented_response()
