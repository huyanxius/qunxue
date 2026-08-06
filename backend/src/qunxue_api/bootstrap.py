from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.research_task_repository import (
    SqliteResearchTaskRepository,
)
from qunxue_api.api.contracts.common import ErrorCode, ErrorDetail, ErrorResponse
from qunxue_api.api.routes.frameworks import router as frameworks_router
from qunxue_api.api.routes.health import router as health_router
from qunxue_api.api.routes.knowledge import router as knowledge_router
from qunxue_api.api.routes.matching import router as matching_router
from qunxue_api.api.routes.phenomena import router as phenomena_router
from qunxue_api.api.routes.research_tasks import router as research_tasks_router
from qunxue_api.api.routes.session import router as session_router
from qunxue_api.application import ResearchJourney, ResearchJourneyDependencies
from qunxue_api.modules.research_intake import (
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
        description="群学致知前后端架构基线 API。",
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
    app.include_router(session_router)
    app.include_router(research_tasks_router)
    app.include_router(phenomena_router)
    app.include_router(knowledge_router)
    app.include_router(matching_router)
    app.include_router(frameworks_router)

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

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        _request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorDetail(
                code="validation_error",
                message="Request validation failed.",
                trace_id=str(uuid4()),
            )
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=body.model_dump(mode="json"),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        _request: Request,
        error: StarletteHTTPException,
    ) -> JSONResponse:
        code, message = {
            status.HTTP_401_UNAUTHORIZED: (
                ErrorCode.UNAUTHENTICATED,
                "Authentication required.",
            ),
            status.HTTP_404_NOT_FOUND: (
                ErrorCode.NOT_FOUND,
                "Resource not found.",
            ),
            status.HTTP_405_METHOD_NOT_ALLOWED: (
                ErrorCode.METHOD_NOT_ALLOWED,
                "Method not allowed.",
            ),
        }.get(
            error.status_code,
            (
                ErrorCode.VALIDATION_ERROR
                if error.status_code < 500
                else ErrorCode.INTERNAL_SERVER_ERROR,
                "Request failed."
                if error.status_code < 500
                else "Internal server error.",
            ),
        )
        body = ErrorResponse(
            error=ErrorDetail(
                code=code,
                message=message,
                trace_id=str(uuid4()),
            )
        )
        return JSONResponse(
            status_code=error.status_code,
            content=body.model_dump(mode="json"),
        )

    return app
