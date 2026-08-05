from datetime import UTC, datetime
from uuid import UUID

import pytest

from qunxue_api.modules.research_intake import (
    ResearchIntakeValidationError,
    ResearchTask,
    ResearchTaskService,
)


class InMemoryResearchTaskRepository:
    def __init__(self) -> None:
        self.saved: dict[UUID, ResearchTask] = {}

    def get(self, task_id: UUID) -> ResearchTask | None:
        return self.saved.get(task_id)

    def add(self, task: ResearchTask) -> ResearchTask:
        self.saved[task.task_id] = task
        return task



def build_service() -> ResearchTaskService:
    return ResearchTaskService(
        InMemoryResearchTaskRepository(),
        id_factory=lambda: UUID("9c2fb49f-cfd0-41f1-9556-118371c9de65"),
        clock=lambda: datetime(2026, 8, 5, 12, 0, tzinfo=UTC),
    )



def test_create_accepts_valid_research_intake() -> None:
    task = build_service().create(
        phenomenon="Communities reuse the same moderator phrases after conflict.",
        research_intent="Study imitation under moderation pressure.",
        context="Observed in three volunteer groups.",
    )

    assert str(task.task_id) == "9c2fb49f-cfd0-41f1-9556-118371c9de65"
    assert task.phenomenon == (
        "Communities reuse the same moderator phrases after conflict."
    )
    assert task.research_intent == "Study imitation under moderation pressure."
    assert task.context == "Observed in three volunteer groups."
    assert task.source == "user_input"



@pytest.mark.parametrize("phenomenon", ["", "   "])
def test_create_rejects_blank_phenomenon(phenomenon: str) -> None:
    with pytest.raises(
        ResearchIntakeValidationError,
        match="phenomenon must not be empty or whitespace-only",
    ):
        build_service().create(
            phenomenon=phenomenon,
            research_intent=None,
            context=None,
        )
