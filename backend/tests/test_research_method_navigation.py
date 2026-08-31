from datetime import UTC, datetime
from uuid import UUID

from qunxue_api.api.routes.research_tasks import _navigation_response
from qunxue_api.modules.research_intake import (
    EntryType,
    PhenomenonProgress,
    ResearchTask,
    ResearchTaskStatus,
)


def test_framework_confirmed_task_resumes_method_design_until_plan_is_confirmed() -> None:
    now = datetime(2026, 8, 31, tzinfo=UTC)
    task = ResearchTask(
        task_id=UUID(int=1), user_id=UUID(int=2), entry_type=EntryType.DIRECT_INPUT,
        status=ResearchTaskStatus.FRAMEWORK_CONFIRMED, version=4,
        idempotency_key="task", created_at=now, updated_at=now,
        current_framework_id=UUID(int=3), current_method_plan_id=None,
        current_method_plan_status=None,
    )
    value = _navigation_response(task, PhenomenonProgress(None, None, None))
    assert value.current_stage.value == "method_design"
    assert value.allowed_actions[0].value == "design_method"
    assert value.resume_path == "/research/00000000-0000-0000-0000-000000000001/method"
