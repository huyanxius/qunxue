from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import ErrorResponse
from qunxue_api.api.contracts.knowledge import (
    BuiltInCasePageResponse,
    BuiltInCaseResponse,
    KnowledgeEntryDetailResponse,
    KnowledgeEntryPageResponse,
    KnowledgeReleaseResponse,
)
from qunxue_api.api.routes.stubs import not_implemented_response
from qunxue_api.modules.knowledge_catalog import KnowledgeUsePurpose

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
def get_current_knowledge_release(request: Request) -> KnowledgeReleaseResponse:
    release = request.app.state.knowledge_catalog.current_release(
        purpose=KnowledgeUsePurpose.BROWSE
    )
    return KnowledgeReleaseResponse(
        knowledge_release_id=release.knowledge_release_id,
        level=release.level,
        content_hash=release.content_hash,
    )


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
    request: Request,
    knowledge_release_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> BuiltInCasePageResponse:
    catalog = request.app.state.builtin_case_catalog
    if (
        knowledge_release_id is not None
        and knowledge_release_id != catalog.knowledge_release_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    try:
        page = catalog.list_page(cursor=cursor, limit=limit)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
        ) from error
    return BuiltInCasePageResponse(
        knowledge_release_id=catalog.knowledge_release_id,
        cases=[
            BuiltInCaseResponse(
                case_id=item.case_id,
                title=item.title,
                summary=item.summary,
                phenomenon=item.phenomenon,
                research_intent=item.research_intent,
                context=item.context,
                content_status=item.content_status,
            )
            for item in page.items
        ],
        stable_order=[item.case_id for item in page.items],
        next_cursor=page.next_cursor,
    )
