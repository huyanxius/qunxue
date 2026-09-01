from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.research_document_model import ResearchDocumentMutationRequestRow
from qunxue_api.adapters.sqlite.research_document_mutation import (
    SqliteResearchDocumentMutationRepository,
)
from qunxue_api.adapters.sqlite.research_method_model import (
    ResearchMethodPlanIdentityRow,
    ResearchMethodPlanVersionRow,
)
from qunxue_api.adapters.sqlite.research_method_repository import SqliteMethodPlanRepository
from qunxue_api.application.research_method import ResearchMethodPlanApplication
from qunxue_api.modules.research_framework import ResearchDocumentStatus
from qunxue_api.modules.research_intake import EntryType, ResearchTask, ResearchTaskStatus
from qunxue_api.modules.research_method import MethodKind, MethodPlanService


def test_method_plan_repository_round_trips_versions_and_reviews() -> None:
    engine = create_engine("sqlite:///:memory:")
    for model in (ResearchMethodPlanIdentityRow, ResearchMethodPlanVersionRow):
        model.__table__.create(engine, checkfirst=True)
    with Session(engine) as session:
        service = MethodPlanService(SqliteMethodPlanRepository(session))
        plan = service.create(
            task_id=UUID(int=1),
            framework_id=UUID(int=2),
            framework_version=1,
            theory_plan_id=UUID(int=3),
            theory_plan_version=1,
            research_question="问题",
            theory_summary="理论",
            material_constraints=("材料边界",),
            ethical_constraints=("伦理",),
            method_kind=MethodKind.MIXED,
            now=datetime(2026, 8, 31, tzinfo=UTC),
        )
        reviewed = service.submit_review(
            plan_id=plan.plan_id, expected_version=1, note="补充整合点", blocking=True
        )
        session.commit()
        restored = service.get(plan.plan_id)
    assert reviewed.version == 2
    assert restored.reviews[0].note == "补充整合点"
    assert restored.status.value == "under_review"
    engine.dispose()


def test_method_plan_mutations_replay_and_reject_idempotency_conflicts() -> None:
    engine = create_engine("sqlite:///:memory:")
    for model in (
        ResearchMethodPlanIdentityRow,
        ResearchMethodPlanVersionRow,
        ResearchDocumentMutationRequestRow,
    ):
        model.__table__.create(engine, checkfirst=True)
    task_id = UUID(int=11)
    user_id = UUID(int=12)
    framework_id = UUID(int=13)
    theory_id = UUID(int=14)
    task = ResearchTask(
        task_id=task_id,
        user_id=user_id,
        entry_type=EntryType.DIRECT_INPUT,
        status=ResearchTaskStatus.FRAMEWORK_CONFIRMED,
        version=1,
        idempotency_key="task-key",
        created_at=datetime(2026, 8, 31, tzinfo=UTC),
        updated_at=datetime(2026, 8, 31, tzinfo=UTC),
        current_framework_id=framework_id,
    )
    framework = SimpleNamespace(
        document_id=framework_id,
        task_id=task_id,
        version=1,
        status=ResearchDocumentStatus.CONFIRMED,
        sections=(),
    )
    theory = SimpleNamespace(
        theory_plan_id=theory_id,
        task_id=task_id,
        version=1,
        knowledge_release=SimpleNamespace(knowledge_release_id="release-1"),
        candidates=(),
        evidence_bundle=SimpleNamespace(evidence_items=()),
    )
    cycle = SimpleNamespace(
        content_hash="sha256:cycle-method-create",
        project_facts=SimpleNamespace(
            material_count=2,
            material_kinds=(("interview_transcript", 2),),
            case_count=1,
            case_material_coverage=(("家庭甲", 2),),
            consent_scopes=(("project_only", 2),),
            sensitivity_levels=(("sensitive", 2),),
            pending_deidentification_count=0,
            sampling_batches=("首轮访谈",),
            analysis_counts=(("codes", 1), ("memos", 1), ("comparisons", 0)),
        ),
        evidence=(),
        gaps=(),
        reporting_hints=(),
    )

    class TaskRepository:
        def __init__(self, value: ResearchTask) -> None:
            self.value = value

        def get(
            self, requested_task_id: UUID, requested_user_id: UUID
        ) -> ResearchTask | None:
            return (
                self.value
                if (requested_task_id, requested_user_id) == (task_id, user_id)
                else None
            )

        def save_progress(self, value: ResearchTask) -> ResearchTask:
            self.value = value
            return value

    task_repository = TaskRepository(task)
    with Session(engine) as session:
        application = ResearchMethodPlanApplication(
            plans=MethodPlanService(SqliteMethodPlanRepository(session)),
            research_tasks=task_repository,
            mutations=SqliteResearchDocumentMutationRepository(session),
            get_framework=lambda _id: framework,
            get_theory_plan=lambda _id: theory,
            get_cycle_snapshot=lambda requested_user, requested_task: (
                cycle
                if (requested_user, requested_task) == (user_id, task_id)
                else None
            ),
        )
        first = application.create(
            user_id=user_id,
            task=task,
            framework_id=framework_id,
            theory_plan_id=theory_id,
            method_kind=MethodKind.MIXED,
            idempotency_key="method-create-replay",
        )
        replay = application.create(
            user_id=user_id,
            task=task,
            framework_id=framework_id,
            theory_plan_id=theory_id,
            method_kind=MethodKind.MIXED,
            idempotency_key="method-create-replay",
        )
        session.commit()
        assert first.plan_id == replay.plan_id
        assert first.version == replay.version == 1
        assert task_repository.value.current_method_plan_id == first.plan_id
        assert task_repository.value.current_method_plan_status == "draft"
        context = {item.key: item for item in first.shared_context}
        assert context["project_materials"].content == (
            "材料总数：2\ninterview_transcript：2"
        )
        assert context["research_cycle_basis"].content == cycle.content_hash
        with pytest.raises(ValueError, match="Idempotency-Key"):
            application.create(
                user_id=user_id,
                task=task,
                framework_id=framework_id,
                theory_plan_id=theory_id,
                method_kind=MethodKind.QUALITATIVE,
                idempotency_key="method-create-replay",
            )
    engine.dispose()


def test_method_plan_repository_persists_stale_and_recreated_versions() -> None:
    engine = create_engine("sqlite:///:memory:")
    for model in (ResearchMethodPlanIdentityRow, ResearchMethodPlanVersionRow):
        model.__table__.create(engine, checkfirst=True)
    with Session(engine) as session:
        service = MethodPlanService(SqliteMethodPlanRepository(session))
        first = service.create(
            task_id=UUID(int=1),
            framework_id=UUID(int=2),
            framework_version=1,
            theory_plan_id=UUID(int=3),
            theory_plan_version=1,
            research_question="问题",
            theory_summary="理论",
            material_constraints=("材料",),
            ethical_constraints=("伦理",),
            method_kind=MethodKind.QUALITATIVE,
        )
        stale = service.mark_stale(plan_id=first.plan_id, reason="框架已更新")
        recreated = service.create(
            task_id=UUID(int=1),
            framework_id=UUID(int=4),
            framework_version=2,
            theory_plan_id=UUID(int=3),
            theory_plan_version=1,
            research_question="新问题",
            theory_summary="新理论",
            material_constraints=("新材料",),
            ethical_constraints=("新伦理",),
            method_kind=MethodKind.MIXED,
        )
        session.commit()
        versions = service.list_versions(first.plan_id)
    assert stale.status.value == "stale"
    assert recreated.plan_id == first.plan_id
    assert recreated.version == 3
    assert [item.version for item in versions] == [3, 2, 1]
    engine.dispose()
