from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from qunxue_api.api.contracts.common import ErrorResponse
from qunxue_api.api.contracts.frontier import (
    FrontierOverviewResponse,
    FrontierRecordPageResponse,
    FrontierRecordResponse,
    FrontierSourcePageResponse,
    FrontierStatusResponse,
    FrontierTopicPageResponse,
)
from qunxue_api.modules.frontier_knowledge import frontier_today

router = APIRouter(
    prefix="/api/frontier", tags=["frontier"], responses={422: {"model": ErrorResponse}}
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
    return request.app.state.frontier_service.search(
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


@router.get(
    "/records/{record_id}",
    operation_id="get_frontier_record",
    response_model=FrontierRecordResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_frontier_record(request: Request, record_id: str):
    record = request.app.state.frontier_store.get_record(record_id)
    if not record or not record["eligibility"]["browse"]:
        raise HTTPException(404, detail="Frontier record not found")
    return record


@router.get(
    "/topics", operation_id="list_frontier_topics", response_model=FrontierTopicPageResponse
)
def list_frontier_topics(request: Request, as_of: date | None = None):
    as_of = as_of or frontier_today()
    return {
        "items": request.app.state.frontier_service.topics(as_of=as_of),
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
