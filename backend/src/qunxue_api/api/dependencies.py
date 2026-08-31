from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from qunxue_api.application import (
    ResearchAnalysisApplication,
    ResearchDocumentApplication,
    ResearchDocumentProposalApplication,
    ResearchMaterialApplication,
    ResearchMethodPlanApplication,
    TheoryMatchingApplication,
)
from qunxue_api.modules.identity import AuthenticatedSession, IdentityService
from qunxue_api.modules.research_intake import PhenomenonService, ResearchTask, ResearchTaskService


def get_identity_service(request: Request) -> Iterator[IdentityService]:
    with request.app.state.identity_service_scope() as service:
        yield service


IdentityServiceDependency = Annotated[
    IdentityService,
    Depends(get_identity_service),
]


def get_current_session(
    request: Request,
    service: IdentityServiceDependency,
) -> AuthenticatedSession:
    cookie_name = request.app.state.settings.session_cookie_name
    return service.authenticate(request.cookies.get(cookie_name))


CurrentSessionDependency = Annotated[
    AuthenticatedSession,
    Depends(get_current_session),
]


def get_research_task_service(
    request: Request,
) -> Iterator[ResearchTaskService]:
    with request.app.state.research_task_service_scope() as service:
        yield service


ResearchTaskServiceDependency = Annotated[
    ResearchTaskService,
    Depends(get_research_task_service),
]


def get_phenomenon_service(request: Request) -> Iterator[PhenomenonService]:
    with request.app.state.phenomenon_service_scope() as service:
        yield service


PhenomenonServiceDependency = Annotated[
    PhenomenonService,
    Depends(get_phenomenon_service),
]


def get_theory_matching_application(
    request: Request,
) -> Iterator[TheoryMatchingApplication]:
    with request.app.state.theory_matching_application_scope() as application:
        yield application


TheoryMatchingApplicationDependency = Annotated[
    TheoryMatchingApplication,
    Depends(get_theory_matching_application),
]


def get_research_document_application(
    request: Request,
) -> Iterator[ResearchDocumentApplication]:
    with request.app.state.research_document_application_scope() as application:
        yield application


ResearchDocumentApplicationDependency = Annotated[
    ResearchDocumentApplication,
    Depends(get_research_document_application),
]


def get_research_document_proposal_application(
    request: Request,
) -> Iterator[ResearchDocumentProposalApplication]:
    with request.app.state.research_document_proposal_application_scope() as application:
        yield application


ResearchDocumentProposalApplicationDependency = Annotated[
    ResearchDocumentProposalApplication,
    Depends(get_research_document_proposal_application),
]


def get_research_material_application(
    request: Request,
) -> Iterator[ResearchMaterialApplication]:
    with request.app.state.research_material_application_scope() as application:
        yield application


ResearchMaterialApplicationDependency = Annotated[
    ResearchMaterialApplication,
    Depends(get_research_material_application),
]


def get_research_analysis_application(
    request: Request,
) -> Iterator[ResearchAnalysisApplication]:
    with request.app.state.research_analysis_application_scope() as application:
        yield application


ResearchAnalysisApplicationDependency = Annotated[
    ResearchAnalysisApplication,
    Depends(get_research_analysis_application),
]


def get_research_method_plan_application(
    request: Request,
) -> Iterator[ResearchMethodPlanApplication]:
    with request.app.state.research_method_plan_application_scope() as application:
        yield application


ResearchMethodPlanApplicationDependency = Annotated[
    ResearchMethodPlanApplication,
    Depends(get_research_method_plan_application),
]


def get_owned_research_task(
    task_id: UUID,
    current: CurrentSessionDependency,
    service: ResearchTaskServiceDependency,
) -> ResearchTask:
    return service.get(task_id, user_id=current.user.user_id)


OwnedResearchTaskDependency = Annotated[
    ResearchTask,
    Depends(get_owned_research_task),
]
