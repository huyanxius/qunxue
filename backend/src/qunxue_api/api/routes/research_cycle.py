from uuid import UUID

from fastapi import APIRouter

from qunxue_api.api.contracts.research_cycle import (
    ResearchCycleResponse,
    ResearchCycleVersionListResponse,
)
from qunxue_api.api.dependencies import (
    CurrentSessionDependency,
    OwnedResearchTaskDependency,
    ResearchCycleApplicationDependency,
)

router = APIRouter(tags=["research-cycle"])


@router.get(
    "/api/research-tasks/{task_id}/research-cycle",
    operation_id="get_research_cycle",
    response_model=ResearchCycleResponse,
)
def get_research_cycle(
    task_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchCycleApplicationDependency,
) -> ResearchCycleResponse:
    return ResearchCycleResponse.from_domain(
        application.current(user_id=current.user.user_id, task_id=task_id)
    )


@router.get(
    "/api/research-tasks/{task_id}/research-cycle/versions",
    operation_id="list_research_cycle_versions",
    response_model=ResearchCycleVersionListResponse,
)
def list_research_cycle_versions(
    task_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchCycleApplicationDependency,
) -> ResearchCycleVersionListResponse:
    return ResearchCycleVersionListResponse(
        task_id=task_id,
        items=[
            ResearchCycleResponse.from_domain(item)
            for item in application.versions(user_id=current.user.user_id, task_id=task_id)
        ],
    )
