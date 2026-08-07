from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import ErrorResponse
from qunxue_api.api.contracts.knowledge import (
    BuiltInCasePageResponse,
    KnowledgeEntryDetailResponse,
    KnowledgeEntryPageResponse,
    KnowledgeReleaseResponse,
)
from qunxue_api.api.routes.stubs import not_implemented_response

router = APIRouter(
    prefix="/api/knowledge",
    tags=["knowledge"],
    responses={422: {"model": ErrorResponse}},
)


@router.get(
    "/releases/current",
    operation_id="get_current_knowledge_release",
    response_model=KnowledgeReleaseResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def get_current_knowledge_release() -> JSONResponse:
    return not_implemented_response()


@router.get(
    "/entries",
    operation_id="list_knowledge_entries",
    response_model=KnowledgeEntryPageResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def list_knowledge_entries(
    knowledge_release_id: str | None = None,
    query: str | None = None,
    category: str | None = None,
    category_id: str | None = None,
    dimension_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> JSONResponse:
    return not_implemented_response()


@router.get(
    "/entries/{knowledge_id}",
    operation_id="get_knowledge_entry",
    response_model=KnowledgeEntryDetailResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def get_knowledge_entry(
    knowledge_id: str,
    knowledge_release_id: str | None = None,
) -> JSONResponse:
    return not_implemented_response()


@router.get(
    "/cases",
    operation_id="list_builtin_cases",
    response_model=BuiltInCasePageResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def list_builtin_cases(
    knowledge_release_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> JSONResponse:
    return not_implemented_response()
