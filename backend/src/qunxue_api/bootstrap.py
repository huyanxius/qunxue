from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from qunxue_api.adapters.model import (
    BuiltInCaseCatalog,
    ModelGateway,
    ModelInvocationError,
    ModelProvider,
    OpenAICompatibleModelProvider,
    SqliteModelInvocationRecorder,
    create_deterministic_mock_provider,
)
from qunxue_api.adapters.security import Argon2PasswordHasher
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.identity_repository import SqliteIdentityRepository
from qunxue_api.adapters.sqlite.knowledge_catalog import SqliteKnowledgeCatalog
from qunxue_api.adapters.sqlite.phenomenon_repository import SqlitePhenomenonRepository
from qunxue_api.adapters.sqlite.research_task_repository import (
    SqliteResearchTaskRepository,
)
from qunxue_api.adapters.sqlite.theory_matching import (
    SqliteMatchingRequestRepository,
    SqliteMatchRunRepository,
    SqliteTheoryDecisionRepository,
    SqliteTheoryDecisionRequestRepository,
)
from qunxue_api.adapters.theory_evidence import CatalogTheoryEvidenceSource
from qunxue_api.api.contracts.common import ErrorCode, ErrorDetail, ErrorResponse
from qunxue_api.api.routes.frameworks import router as frameworks_router
from qunxue_api.api.routes.health import router as health_router
from qunxue_api.api.routes.knowledge import router as knowledge_router
from qunxue_api.api.routes.matching import router as matching_router
from qunxue_api.api.routes.phenomena import example_router as phenomenon_examples_router
from qunxue_api.api.routes.phenomena import material_router as material_intakes_router
from qunxue_api.api.routes.phenomena import router as phenomena_router
from qunxue_api.api.routes.research_tasks import router as research_tasks_router
from qunxue_api.api.routes.session import router as session_router
from qunxue_api.application import (
    ResearchJourney,
    ResearchJourneyDependencies,
    TheoryMatchingApplication,
)
from qunxue_api.modules.identity import (
    EmailAlreadyRegistered,
    IdentityError,
    IdentityService,
    InvalidEmail,
    Unauthenticated,
)
from qunxue_api.modules.research_intake import (
    PhenomenonService,
    ResearchTaskNotFound,
    ResearchTaskService,
)
from qunxue_api.modules.theory_matching import (
    TheoryDecisionService,
    TheoryMatchingService,
)
from qunxue_api.settings import KNOWLEDGE_ROOT, Settings, get_settings


def create_app(
    *,
    settings: Settings | None = None,
    database: Database | None = None,
    journey_dependencies: ResearchJourneyDependencies | None = None,
    model_provider: ModelProvider | None = None,
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
    app.state.knowledge_catalog = SqliteKnowledgeCatalog(
        resolved_database,
        knowledge_root=KNOWLEDGE_ROOT,
    )
    builtin_case_catalog = BuiltInCaseCatalog.default()
    resolved_model_provider = model_provider or _model_provider_from_settings(
        settings=resolved_settings,
        builtin_case_catalog=builtin_case_catalog,
    )
    model_invocation_recorder = SqliteModelInvocationRecorder(resolved_database)
    app.state.builtin_case_catalog = builtin_case_catalog
    app.state.model_invocation_recorder = model_invocation_recorder
    app.state.model_gateway = ModelGateway(
        provider=resolved_model_provider,
        recorder=model_invocation_recorder,
        contract_version=resolved_settings.contract_version,
    )
    app.state.research_journey = (
        ResearchJourney(journey_dependencies)
        if journey_dependencies is not None
        else None
    )
    password_hasher = Argon2PasswordHasher()
    invalid_password_hash = password_hasher.hash("invalid-account-password")

    @contextmanager
    def identity_service_scope() -> Iterator[IdentityService]:
        with resolved_database.session() as session:
            yield IdentityService(
                SqliteIdentityRepository(session),
                password_hasher,
                invalid_password_hash=invalid_password_hash,
                session_ttl=timedelta(seconds=resolved_settings.session_ttl_seconds),
            )

    @contextmanager
    def research_task_service_scope() -> Iterator[ResearchTaskService]:
        with resolved_database.session() as session:
            yield ResearchTaskService(SqliteResearchTaskRepository(session))

    @contextmanager
    def phenomenon_service_scope() -> Iterator[PhenomenonService]:
        with resolved_database.session() as session:
            yield PhenomenonService(
                SqlitePhenomenonRepository(session),
                SqliteResearchTaskRepository(session),
            )

    @contextmanager
    def theory_matching_application_scope() -> Iterator[TheoryMatchingApplication]:
        with resolved_database.session() as session:
            descriptor = app.state.model_gateway.descriptor
            match_runs = SqliteMatchRunRepository(session)
            matching = TheoryMatchingService(
                evidence_source=CatalogTheoryEvidenceSource(app.state.knowledge_catalog),
                judge=app.state.model_gateway,
                repository=match_runs,
                provider=descriptor.provider,
                model_version=descriptor.model_version,
                capability=descriptor.capability_tier,
                contract_version=resolved_settings.contract_version,
            )
            yield TheoryMatchingApplication(
                catalog=app.state.knowledge_catalog,
                matching=matching,
                decisions=TheoryDecisionService(
                    SqliteTheoryDecisionRepository(session, match_runs)
                ),
                matching_requests=SqliteMatchingRequestRepository(session),
                decision_requests=SqliteTheoryDecisionRequestRepository(session),
                research_tasks=SqliteResearchTaskRepository(session),
            )

    app.state.research_task_service_scope = research_task_service_scope
    app.state.phenomenon_service_scope = phenomenon_service_scope
    app.state.theory_matching_application_scope = theory_matching_application_scope
    app.state.identity_service_scope = identity_service_scope
    app.include_router(health_router)
    app.include_router(session_router)
    app.include_router(research_tasks_router)
    app.include_router(phenomena_router)
    app.include_router(phenomenon_examples_router)
    app.include_router(material_intakes_router)
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

    @app.exception_handler(IdentityError)
    async def handle_identity_error(
        _request: Request,
        error: IdentityError,
    ) -> JSONResponse:
        if isinstance(error, EmailAlreadyRegistered):
            status_code = status.HTTP_409_CONFLICT
        elif isinstance(error, InvalidEmail):
            status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
        else:
            status_code = status.HTTP_401_UNAUTHORIZED
        code = (
            ErrorCode.UNAUTHENTICATED
            if status_code == status.HTTP_401_UNAUTHORIZED
            else ErrorCode.VALIDATION_ERROR
        )
        body = ErrorResponse(
            error=ErrorDetail(
                code=code,
                message=str(error),
                trace_id=str(uuid4()),
            )
        )
        response = JSONResponse(
            status_code=status_code,
            content=body.model_dump(mode="json"),
        )
        if isinstance(error, Unauthenticated):
            response.delete_cookie(
                resolved_settings.session_cookie_name,
                path="/",
                secure=resolved_settings.session_cookie_secure,
                httponly=True,
                samesite="lax",
            )
        return response

    @app.exception_handler(ModelInvocationError)
    async def handle_model_invocation_error(
        _request: Request,
        error: ModelInvocationError,
    ) -> JSONResponse:
        public_code, response_status = {
            "model_timeout": (
                ErrorCode.MODEL_TIMEOUT,
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ),
            "model_unavailable": (
                ErrorCode.MODEL_TIMEOUT,
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ),
            "model_rate_limited": (
                ErrorCode.MODEL_TIMEOUT,
                status.HTTP_429_TOO_MANY_REQUESTS,
            ),
            "model_invalid_output": (
                ErrorCode.INTERNAL_SERVER_ERROR,
                status.HTTP_502_BAD_GATEWAY,
            ),
            "no_reliable_candidate": (
                ErrorCode.NO_RELIABLE_CANDIDATE,
                status.HTTP_409_CONFLICT,
            ),
            "insufficient_sources": (
                ErrorCode.INSUFFICIENT_SOURCES,
                status.HTTP_409_CONFLICT,
            ),
        }[error.code]
        body = ErrorResponse(
            error=ErrorDetail(
                code=public_code,
                message=str(error),
                trace_id=str(error.trace_id),
            )
        )
        return JSONResponse(
            status_code=response_status,
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


def _model_provider_from_settings(
    *,
    settings: Settings,
    builtin_case_catalog: BuiltInCaseCatalog,
) -> ModelProvider:
    if settings.runtime_mode == "mock":
        return create_deterministic_mock_provider(catalog=builtin_case_catalog)
    if settings.model_base_url is None or settings.model_name is None:
        raise ValueError(
            "QUNXUE_MODEL_BASE_URL (model_base_url) and "
            "QUNXUE_MODEL_NAME (model_name) are required outside mock mode"
        )

    headers = {
        name: value.get_secret_value()
        for name, value in settings.model_extra_headers.items()
    }
    if settings.runtime_mode == "sft" and settings.model_sft_resource_id is not None:
        header_name = settings.model_sft_resource_header
        if header_name.lower() in {name.lower() for name in headers}:
            raise ValueError("SFT resource header duplicates a model extension header")
        headers[header_name] = settings.model_sft_resource_id.get_secret_value()

    return OpenAICompatibleModelProvider(
        base_url=settings.model_base_url,
        api_key=(
            settings.model_api_key.get_secret_value()
            if settings.model_api_key is not None
            else None
        ),
        model=settings.model_name,
        timeout_seconds=settings.model_timeout_seconds,
        capability_tier=settings.runtime_mode,
        extra_headers=headers,
    )
