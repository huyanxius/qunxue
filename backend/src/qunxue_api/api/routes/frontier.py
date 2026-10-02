from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request

from qunxue_api.api.contracts.common import ErrorResponse
from qunxue_api.api.contracts.frontier import (
    FrontierCalendarResponse,
    FrontierKnowledgeLinksResponse,
    FrontierOverviewResponse,
    FrontierPeriodReportResponse,
    FrontierReadingPriorityPageResponse,
    FrontierReadingPriorityResponse,
    FrontierRecordPageResponse,
    FrontierRecordResponse,
    FrontierRecordSummaryPageResponse,
    FrontierSourcePageResponse,
    FrontierStatusResponse,
    FrontierTopicPageResponse,
)
from qunxue_api.api.frontier_cache import FrontierPublicReadRoute
from qunxue_api.api.presenters.frontier import public_record
from qunxue_api.modules.frontier_knowledge import frontier_today

router = APIRouter(
    prefix="/api/frontier",
    tags=["frontier"],
    responses={422: {"model": ErrorResponse}},
    route_class=FrontierPublicReadRoute,
)


@router.get(
    "/overview", operation_id="get_frontier_overview", response_model=FrontierOverviewResponse
)
def get_frontier_overview(request: Request, as_of: date | None = None):
    return request.app.state.frontier_service.overview(as_of=as_of)


@router.get(
    "/search", operation_id="search_frontier_records", response_model=FrontierRecordPageResponse
)
def search_frontier_records(
    request: Request,
    q: str = Query(default="", max_length=200),
    stream: Literal["research", "practice"] | None = None,
    source_id: str | None = None,
    topic_id: str | None = None,
    since_days: int | None = Query(default=None, ge=1, le=3660),
    material_type: str | None = None,
    limit: int = Query(default=24, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    as_of: date | None = None,
):
    result = request.app.state.frontier_service.search(
        q=q,
        stream=stream,
        source_id=source_id,
        topic_id=topic_id,
        since_days=since_days,
        material_type=material_type,
        limit=limit,
        offset=offset,
        as_of=as_of,
    )
    return {**result, "items": [public_record(record) for record in result["items"]]}


@router.get(
    "/summaries",
    operation_id="list_frontier_summaries",
    response_model=FrontierRecordSummaryPageResponse,
)
def list_frontier_summaries(
    request: Request,
    q: str = Query(default="", max_length=200),
    stream: Literal["research", "practice"] | None = None,
    source_id: str | None = None,
    source_name: str | None = None,
    topic_id: str | None = None,
    since_days: int | None = Query(default=None, ge=1, le=3660),
    material_type: str | None = None,
    limit: int = Query(default=24, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    as_of: date | None = None,
    focus: bool = False,
    record_ids: Annotated[list[str] | None, Query(max_length=100)] = None,
):
    return request.app.state.frontier_service.search(
        q=q,
        stream=stream,
        source_id=source_id,
        source_name=source_name,
        topic_id=topic_id,
        since_days=since_days,
        material_type=material_type,
        limit=limit,
        offset=offset,
        as_of=as_of,
        summaries=True,
        focus=focus,
        record_ids=record_ids,
    )


@router.get(
    "/records/{record_id}",
    operation_id="get_frontier_record",
    response_model=FrontierRecordResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_frontier_record(request: Request, record_id: str, as_of: date | None = None):
    try:
        return public_record(request.app.state.frontier_service.record(record_id, as_of=as_of))
    except LookupError as error:
        raise HTTPException(404, detail="Frontier record not found") from error


@router.get(
    "/topics", operation_id="list_frontier_topics", response_model=FrontierTopicPageResponse
)
def list_frontier_topics(
    request: Request, as_of: date | None = None, detail: bool = True, topic_id: str | None = None
):
    as_of = as_of or frontier_today()
    return {
        "items": request.app.state.frontier_service.topics(
            as_of=as_of, detail=detail, topic_id=topic_id
        ),
        "as_of": as_of.isoformat(),
    }


@router.get(
    "/trends", operation_id="list_frontier_trends", response_model=FrontierTopicPageResponse
)
def list_frontier_trends(
    request: Request, window: Literal[30, 90, 180] = 30, as_of: date | None = None
):
    as_of = as_of or frontier_today()
    return {
        "items": request.app.state.frontier_service.topics(as_of=as_of),
        "as_of": as_of.isoformat(),
        "window": window,
    }


@router.get(
    "/sources", operation_id="list_frontier_sources", response_model=FrontierSourcePageResponse
)
def list_frontier_sources(request: Request):
    return {"items": request.app.state.frontier_store.list_sources()}


@router.get("/status", operation_id="get_frontier_status", response_model=FrontierStatusResponse)
def get_frontier_status(request: Request):
    store = request.app.state.frontier_store
    records = [r for r in store.list_records() if r["eligibility"]["browse"]]
    jobs = store.list_jobs()
    research = [r for r in records if r["material_type"] != "official_practice"]
    settings = request.app.state.settings
    return {
        "as_of": frontier_today().isoformat(),
        "record_count": len(records),
        "research_count": len(research),
        "practice_count": len(records) - len(research),
        "verified_research_count": sum(
            r["verification_status"] == "verified_frontier" for r in research
        ),
        "source_count": len({r["source_id"] for r in records}),
        "registered_source_count": len(store.list_sources()),
        "exact_dated_research_count": sum(
            bool(r.get("published_at")) and r.get("published_at_precision") == "day"
            for r in research
        ),
        "extractor_status": settings.frontier_extractor_status,
        "verifier_status": settings.frontier_verifier_status,
        "embedding_status": settings.frontier_embedding_status,
        "automatic_collection": False,
        "processing_mode": "manual_structured_import_and_lexical_retrieval",
        "pending_jobs": sum(j["status"] in {"pending", "retry", "running"} for j in jobs),
        "blocked_jobs": sum(j["status"] == "blocked" for j in jobs),
        "baseline_status": request.app.state.frontier_service.baseline_status(frontier_today()),
        "limitations": [
            "主题为明确词典归一和编辑归纳，不是模型聚类",
            "未核实的论文出版日不计入时间趋势；尚无完整历史采集覆盖基线",
            "当前快照仅元数据和最小摘录，研究摘要不能充当全文结论证据",
            "自动采集与WeRSS尚未启用；抽取、核验、embedding需要独立新配置且默认禁网",
        ],
    }


@router.get(
    "/calendar", operation_id="get_frontier_calendar", response_model=FrontierCalendarResponse
)
def get_frontier_calendar(
    request: Request, year: int = Query(ge=1, le=9999), as_of: date | None = None
):
    return request.app.state.frontier_service.calendar(year=year, as_of=as_of)


@router.get(
    "/records/{record_id}/knowledge-links",
    operation_id="get_frontier_knowledge_links",
    response_model=FrontierKnowledgeLinksResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_frontier_knowledge_links(request: Request, record_id: str, as_of: date | None = None):
    try:
        return request.app.state.frontier_knowledge_links.for_record(record_id, as_of=as_of)
    except LookupError as error:
        raise HTTPException(404, detail="Frontier record or knowledge release not found") from error


@router.get(
    "/period-report",
    operation_id="get_frontier_period_report",
    response_model=FrontierPeriodReportResponse,
)
def get_frontier_period_report(
    request: Request,
    previous_start: date,
    previous_end: date,
    current_start: date,
    current_end: date,
    topic_key: str = Query(min_length=1, max_length=100),
    as_of: date | None = None,
):
    try:
        return request.app.state.frontier_service.period_report(
            previous_start=previous_start,
            previous_end=previous_end,
            current_start=current_start,
            current_end=current_end,
            topic_key=topic_key,
            as_of=as_of,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get(
    "/records/{record_id}/reading-priority",
    operation_id="get_frontier_reading_priority",
    response_model=FrontierReadingPriorityResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_frontier_reading_priority(request: Request, record_id: str, as_of: date | None = None):
    try:
        return request.app.state.frontier_reading_priority.for_record(record_id, as_of=as_of)
    except LookupError as error:
        raise HTTPException(404, detail="Frontier record not found") from error


@router.get(
    "/reading-priorities",
    operation_id="list_frontier_reading_priorities",
    response_model=FrontierReadingPriorityPageResponse,
)
def list_frontier_reading_priorities(
    request: Request,
    q: str = Query(default="", max_length=200),
    readiness: Literal["passage_supported", "abstract_supported", "metadata_only"] | None = None,
    assessment_status: Literal["unassessed", "partial", "assessed"] | None = None,
    min_academic_value: float | None = Query(default=None, ge=0, le=100),
    as_of: date | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=24, ge=1, le=200),
):
    return request.app.state.frontier_reading_priority.search(
        q=q,
        readiness=readiness,
        assessment_status=assessment_status,
        min_academic_value=min_academic_value,
        as_of=as_of,
        offset=offset,
        limit=limit,
    )
