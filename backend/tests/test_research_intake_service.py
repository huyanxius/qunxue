from datetime import UTC, datetime
from uuid import UUID

import pytest

from qunxue_api.modules.research_intake import (
    EntryType,
    ResearchIntakeValidationError,
    ResearchTask,
    ResearchTaskAction,
    ResearchTaskService,
    ResearchTaskStatus,
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
        task_id_factory=lambda _idempotency_key: UUID(
            '9c2fb49f-cfd0-41f1-9556-118371c9de65'
        ),
        clock=lambda: datetime(2026, 8, 5, 12, 0, tzinfo=UTC),
    )


def test_create_accepts_valid_research_intake() -> None:
    task = build_service().create(
        idempotency_key='stable-request-key',
        phenomenon='Communities reuse the same moderator phrases after conflict.',
        research_intent='Study imitation under moderation pressure.',
        context='Observed in three volunteer groups.',
    )

    assert str(task.task_id) == '9c2fb49f-cfd0-41f1-9556-118371c9de65'
    assert task.entry_type is EntryType.DIRECT_INPUT
    assert task.status is ResearchTaskStatus.DRAFT
    assert task.version == 1
    assert task.allowed_actions == (ResearchTaskAction.SUBMIT_PHENOMENON,)
    assert task.phenomenon == (
        'Communities reuse the same moderator phrases after conflict.'
    )
    assert task.research_intent == 'Study imitation under moderation pressure.'
    assert task.context == 'Observed in three volunteer groups.'
    assert task.source == 'user_input'


def test_create_reuses_the_same_task_for_the_same_idempotency_key() -> None:
    service = build_service()

    first = service.create(
        idempotency_key='stable-request-key',
        phenomenon='Members stop volunteering after coordination debt grows.',
        research_intent='Track fatigue in volunteer labor.',
        context='Observed in a mutual aid group.',
    )
    second = service.create(
        idempotency_key='stable-request-key',
        phenomenon='Members stop volunteering after coordination debt grows.',
        research_intent='Track fatigue in volunteer labor.',
        context='Observed in a mutual aid group.',
    )

    assert second.task_id == first.task_id
    assert second.version == first.version
    assert second.status is ResearchTaskStatus.DRAFT


@pytest.mark.parametrize('phenomenon', ['', '   '])
def test_create_rejects_blank_phenomenon(phenomenon: str) -> None:
    with pytest.raises(
        ResearchIntakeValidationError,
        match='研究现象不能为空或纯空白。',
    ):
        build_service().create(
            idempotency_key='stable-request-key',
            phenomenon=phenomenon,
            research_intent=None,
            context=None,
        )