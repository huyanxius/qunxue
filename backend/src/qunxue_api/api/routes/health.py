from uuid import uuid4

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import (
    ErrorCode,
    ErrorDetail,
    ErrorResponse,
)
from qunxue_api.api.contracts.health import HealthResponse
from qunxue_api.modules.knowledge_catalog import (
    KnowledgeUsePurpose,
    RetrievalPipelineUnavailable,
)
from qunxue_api.settings import Settings

router = APIRouter(
    prefix="/api",
    tags=["system"],
    responses={422: {"model": ErrorResponse}},
)


@router.get(
    "/health",
    operation_id="get_health",
    response_model=HealthResponse,
    responses={503: {"model": ErrorResponse}},
)
def get_health(request: Request) -> HealthResponse | JSONResponse:
    settings: Settings = request.app.state.settings
    request.app.state.database.is_ready()
    descriptor = request.app.state.model_gateway.descriptor
    release = request.app.state.knowledge_catalog.current_release(
        purpose=KnowledgeUsePurpose.BROWSE
    )
    if settings.runtime_mode != "mock":
        try:
            match_release = request.app.state.knowledge_catalog.current_release(
                purpose=KnowledgeUsePurpose.MATCH
            )
            request.app.state.knowledge_retriever.require_ready_manifest(
                knowledge_release_id=match_release.knowledge_release_id,
                release_content_hash=match_release.content_hash,
            )
        except (LookupError, RetrievalPipelineUnavailable):
            body = ErrorResponse(
                error=ErrorDetail(
                    code=ErrorCode.RETRIEVAL_UNAVAILABLE,
                    message=(
                        "当前 MATCH 知识发布没有身份一致的 ready 检索索引。"
                    ),
                    trace_id=str(uuid4()),
                )
            )
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=body.model_dump(mode="json"),
            )
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        runtime_mode=settings.runtime_mode,
        persistence="sqlite",
        contract_version=settings.contract_version,
        capability=descriptor.capability_tier,
        knowledge_release_id=release.knowledge_release_id,
    )
