from fastapi import APIRouter, Request

from qunxue_api.api.contracts.common import ErrorResponse
from qunxue_api.api.contracts.health import HealthResponse
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
)
def get_health(request: Request) -> HealthResponse:
    settings: Settings = request.app.state.settings
    request.app.state.database.is_ready()
    descriptor = request.app.state.model_gateway.descriptor
    case_catalog = request.app.state.builtin_case_catalog
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        runtime_mode=settings.runtime_mode,
        persistence="sqlite",
        contract_version=settings.contract_version,
        capability=descriptor.capability_tier,
        knowledge_release_id=case_catalog.knowledge_release_id,
    )
