from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from qunxue_api.modules.identity import AuthenticatedSession, IdentityService
from qunxue_api.modules.research_intake import ResearchTask, ResearchTaskService


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
