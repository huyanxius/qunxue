from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.research_task_repository import (
    SqliteResearchTaskRepository,
)
from qunxue_api.api.contracts.common import ErrorDetail, ErrorResponse
from qunxue_api.api.routes.health import router as health_router
from qunxue_api.api.routes.research_tasks import router as research_tasks_router
from qunxue_api.application import ResearchJourney, ResearchJourneyDependencies
from qunxue_api.modules.research_intake import (
    ResearchIntakeValidationError,
    ResearchTaskNotFound,
    ResearchTaskService,
)
from qunxue_api.settings import Settings, get_settings


def create_app(
    *,
    settings: Settings | None = None,
    database: Database | None = None,
    journey_dependencies: ResearchJourneyDependencies | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_database = database or Database(resolved_settings.database_url)

    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        description="SocioMatch API.",
    )
    app.state.settings = resolved_settings
    app.state.database = resolved_database
    app.state.research_journey = (
        ResearchJourney(journey_dependencies)
        if journey_dependencies is not None
        else None
    )

    @contextmanager
    def research_task_service_scope() -> Iterator[ResearchTaskService]:
        with resolved_database.session() as session:
            yield ResearchTaskService(SqliteResearchTaskRepository(session))

    app.state.research_task_service_scope = research_task_service_scope
    app.include_router(health_router)
    app.include_router(research_tasks_router)

    @app.exception_handler(ResearchTaskNotFound)
    async def handle_research_task_not_found(
        _request: Request,
        error: ResearchTaskNotFound,
    ) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorDetail(
                code=error.code,
                message=str(error),
                trace_id=str(uuid4()),
            )
        )
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=body.model_dump(mode="json"),
        )

    @app.exception_handler(ResearchIntakeValidationError)
    async def handle_research_intake_validation_error(
        _request: Request,
        error: ResearchIntakeValidationError,
    ) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorDetail(
                code=error.code,
                message=str(error),
                trace_id=str(uuid4()),
            )
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=body.model_dump(mode="json"),
        )

    @app.exception_handler(Exception)
    async def handle_internal_server_error(
        _request: Request,
        _error: Exception,
    ) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorDetail(
                code="internal_server_error",
                message="unexpected service failure",
                trace_id=str(uuid4()),
            )
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=body.model_dump(mode="json"),
        )

    return app
