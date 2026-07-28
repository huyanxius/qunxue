from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from qunxue_api.modules.research_intake import ResearchTaskService


def get_research_task_service(
    request: Request,
) -> Iterator[ResearchTaskService]:
    with request.app.state.research_task_service_scope() as service:
        yield service


ResearchTaskServiceDependency = Annotated[
    ResearchTaskService,
    Depends(get_research_task_service),
]
