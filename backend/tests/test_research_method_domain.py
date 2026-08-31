from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from qunxue_api.application.research_document_mutations import ResearchDocumentMutationReceipt
from qunxue_api.application.research_method import ResearchMethodPlanApplication, _shared_context
from qunxue_api.modules.research_framework import ResearchDocumentStatus
from qunxue_api.modules.research_intake import ResearchTaskStatus
from qunxue_api.modules.research_method import (
    MethodKind,
    MethodPlanSection,
    MethodPlanService,
    MethodPlanStatus,
)


def test_method_plan_starts_with_shared_constraints_and_user_can_defer() -> None:
    service = MethodPlanService.in_memory()
    task_id = UUID(int=1)
    framework_id = UUID(int=2)
    theory_plan_id = UUID(int=3)
    plan = service.create(
        task_id=task_id,
        framework_id=framework_id,
        framework_version=4,
        theory_plan_id=theory_plan_id,
        theory_plan_version=2,
        research_question="家庭内照护如何重新分配？",
        theory_summary="结构与能动性视角",
        material_constraints=("仅使用用户已确认的个人材料",),
        ethical_constraints=("去标识化并尊重撤回",),
        method_kind=MethodKind.UNDECIDED,
        now=datetime(2026, 8, 31, tzinfo=UTC),
    )

    assert plan.status is MethodPlanStatus.DRAFT
    assert plan.decision_source == "system_recommendation"
    assert plan.shared_constraints.material_constraints == ("仅使用用户已确认的个人材料",)

    contextual = service.create(
        task_id=UUID(int=4),
        framework_id=UUID(int=5),
        framework_version=1,
        theory_plan_id=UUID(int=6),
        theory_plan_version=1,
        research_question="问题",
        theory_summary="理论",
        material_constraints=(),
        ethical_constraints=(),
        theory_concepts=("照护",),
        evidence_ref_ids=("evidence-1",),
        knowledge_release_id="release-1",
        method_kind=MethodKind.UNDECIDED,
    )
    assert contextual.shared_constraints.theory_concepts == ("照护",)
    assert contextual.shared_constraints.evidence_ref_ids == ("evidence-1",)
    assert contextual.shared_constraints.knowledge_release_id == "release-1"

    revised = service.revise(
        plan_id=plan.plan_id,
        expected_version=plan.version,
        method_kind=MethodKind.QUALITATIVE,
        sections=(
            MethodPlanSection(
                key="design",
                title="研究设计",
                content="解释性个案研究",
                source="user",
            ),
            MethodPlanSection("research_object", "研究对象", "家庭照护案例", "user"),
            MethodPlanSection("sampling", "取样策略", "按差异化案例取样", "user"),
            MethodPlanSection("material_acquisition", "材料获取", "使用已授权日记", "user"),
            MethodPlanSection("analysis", "质性分析路径", "开放编码后跨案例比较", "user"),
            MethodPlanSection("credibility", "可信度策略", "保留反例并复核", "user"),
            MethodPlanSection("reflexivity", "反身性", "记录研究者位置", "user"),
            MethodPlanSection("ethics", "伦理与风险", "去标识化并允许撤回", "user"),
        ),
        rationale="先完成质性编码，再决定是否需要定量补充。",
        change_summary="用户选择质性路径",
        actor="user",
    )
    assert revised.version == 2
    assert revised.method_kind is MethodKind.QUALITATIVE
    assert revised.decision_source == "user_decision"

    deferred = service.confirm(
        plan_id=revised.plan_id,
        expected_version=revised.version,
        reason="确认当前方法计划",
    )
    assert deferred.status is MethodPlanStatus.CONFIRMED


def test_shared_context_keeps_every_framework_section_and_evidence_locator() -> None:
    evidence = SimpleNamespace(
        evidence_ref_id="framework-ref-1",
        source_id="source-1",
        source_kind=SimpleNamespace(value="personal_material"),
        knowledge_release_id=None,
        annotation_id=UUID(int=51),
        material_id=UUID(int=52),
        parse_id=UUID(int=53),
        segment_id="segment-1",
        locator={"section": "访谈 A", "paragraph": 2},
    )
    framework = SimpleNamespace(
        sections=(
            SimpleNamespace(
                key="sample_and_sources",
                title="样本与资料来源",
                content="仅使用已授权访谈。",
                evidence_refs=(evidence,),
            ),
            SimpleNamespace(
                key="ethics",
                title="伦理",
                content="去标识化。",
                evidence_refs=(),
            ),
        )
    )
    theory = SimpleNamespace(
        phenomenon=SimpleNamespace(phenomenon="照护如何变化？", research_intent="解释机制"),
        candidates=(
            SimpleNamespace(
                content=SimpleNamespace(title="协商理论", core_claims=("资源影响协商",)),
                judgement=SimpleNamespace(applicable_conditions=("有连续材料",), limitations=()),
            ),
        ),
        use_assignments=(),
        relations=(),
        evidence_bundle=SimpleNamespace(evidence_items=()),
    )
    context = _shared_context(framework, theory)
    sample = next(item for item in context if item.key == "sample_and_sources")
    assert sample.evidence_refs[0].evidence_ref_id == "framework-ref-1"
    assert sample.evidence_refs[0].locator == '{"paragraph": 2, "section": "访谈 A"}'
    assert {item.key for item in context} == {"sample_and_sources", "ethics", "theory_plan"}

def test_method_plan_rejects_creation_without_confirmed_framework() -> None:
    service = MethodPlanService.in_memory()
    with pytest.raises(ValueError, match="confirmed research framework"):
        service.create(
            task_id=UUID(int=1),
            framework_id=UUID(int=2),
            framework_version=1,
            theory_plan_id=UUID(int=3),
            theory_plan_version=1,
            research_question="问题",
            theory_summary="理论",
            material_constraints=(),
            ethical_constraints=(),
            method_kind=MethodKind.QUALITATIVE,
            framework_confirmed=False,
        )


def test_blocking_review_can_be_resolved_without_erasing_review_history() -> None:
    service = MethodPlanService.in_memory()
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
        method_kind=MethodKind.QUALITATIVE,
    )
    reviewed = service.submit_review(
        plan_id=plan.plan_id, expected_version=1, note="说明反身性", blocking=True
    )
    resolved = service.resolve_review(
        plan_id=plan.plan_id,
        expected_version=reviewed.version,
        review_id=reviewed.reviews[0].review_id,
        reason="已补充反身性记录",
    )
    assert resolved.status is MethodPlanStatus.DRAFT
    assert resolved.reviews[0].resolved_at is not None
    assert resolved.reviews[0].note == "说明反身性"


def test_revision_keeps_unresolved_review_and_confirmation_remains_blocked() -> None:
    service = MethodPlanService.in_memory()
    plan = service.create(
        task_id=UUID(int=11),
        framework_id=UUID(int=12),
        framework_version=1,
        theory_plan_id=UUID(int=13),
        theory_plan_version=1,
        research_question="问题",
        theory_summary="理论",
        material_constraints=(),
        ethical_constraints=(),
        method_kind=MethodKind.QUALITATIVE,
    )
    reviewed = service.submit_review(
        plan_id=plan.plan_id, expected_version=1, note="需要补充反身性", blocking=True
    )
    revised = service.revise(
        plan_id=plan.plan_id,
        expected_version=reviewed.version,
        method_kind=MethodKind.QUALITATIVE,
        sections=tuple(
            MethodPlanSection(item.key, item.title, f"用户补充：{item.key}", "user")
            for item in reviewed.sections
        ),
        rationale="补充方法细节",
        change_summary="根据审校意见修订",
        actor="user",
    )
    assert revised.reviews == reviewed.reviews
    assert revised.status is MethodPlanStatus.UNDER_REVIEW
    with pytest.raises(ValueError, match="blocking method plan review"):
        service.confirm(
            plan_id=plan.plan_id,
            expected_version=revised.version,
            reason="不应绕过审校",
        )


def test_restore_keeps_unresolved_review_and_confirmation_remains_blocked() -> None:
    service = MethodPlanService.in_memory()
    plan = service.create(
        task_id=UUID(int=31),
        framework_id=UUID(int=32),
        framework_version=1,
        theory_plan_id=UUID(int=33),
        theory_plan_version=1,
        research_question="问题",
        theory_summary="理论",
        material_constraints=(),
        ethical_constraints=(),
        method_kind=MethodKind.UNDECIDED,
    )
    reviewed = service.submit_review(
        plan_id=plan.plan_id, expected_version=1, note="请说明暂缓标准", blocking=True
    )
    restored = service.restore(
        plan_id=plan.plan_id,
        source_version=plan.version,
        expected_version=reviewed.version,
        reason="恢复草案继续处理",
    )
    assert restored.reviews == reviewed.reviews
    with pytest.raises(ValueError, match="blocking method plan review"):
        service.confirm(
            plan_id=plan.plan_id,
            expected_version=restored.version,
            reason="不应绕过审校",
        )


def test_recreating_after_a_changed_framework_keeps_history_and_new_current_version() -> None:
    service = MethodPlanService.in_memory()
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
    assert stale.status is MethodPlanStatus.STALE
    assert recreated.plan_id == first.plan_id
    assert recreated.version > stale.version
    assert recreated.framework_id == UUID(int=4)
    assert recreated.status is MethodPlanStatus.DRAFT
    assert len(service.list_versions(first.plan_id)) == 3


def test_application_rejects_a_task_framework_mismatch_before_persisting() -> None:
    task_id = UUID(int=1)
    user_id = UUID(int=9)
    framework_id = UUID(int=2)
    theory_id = UUID(int=3)
    task = SimpleNamespace(task_id=task_id, user_id=user_id, current_framework_id=UUID(int=99))
    framework = SimpleNamespace(
        document_id=framework_id,
        task_id=task_id,
        version=1,
        status=ResearchDocumentStatus.CONFIRMED,
        sections=(),
    )
    theory = SimpleNamespace(theory_plan_id=theory_id, task_id=task_id, version=1)
    service = MethodPlanService.in_memory()

    class MutationDouble:
        def claim(self, **kwargs):
            return ResearchDocumentMutationReceipt(
                request_id=uuid4(),
                user_id=user_id,
                idempotency_key="test-key",
                operation="test",
                request_hash="hash",
                status="pending",
            )

        def complete(self, **kwargs):
            return None

        def fail(self, **kwargs):
            return None

    application = ResearchMethodPlanApplication(
        plans=service,
        research_tasks=SimpleNamespace(),
        mutations=MutationDouble(),
        get_framework=lambda _id: framework,
        get_theory_plan=lambda _id: theory,
    )
    with pytest.raises(ValueError, match="does not match"):
        application.create(
            user_id=user_id,
            task=task,
            framework_id=framework_id,
            theory_plan_id=theory_id,
            method_kind=MethodKind.QUALITATIVE,
            idempotency_key="test-method-plan-create",
        )
    assert service.latest_for_task(task_id) is None


def test_application_rejects_confirmed_framework_when_task_projection_is_not_confirmed() -> None:
    task_id = UUID(int=41)
    user_id = UUID(int=42)
    framework_id = UUID(int=43)
    theory_id = UUID(int=44)
    task = SimpleNamespace(
        task_id=task_id,
        user_id=user_id,
        current_framework_id=framework_id,
        status=ResearchTaskStatus.FRAMEWORK_DRAFT,
    )
    framework = SimpleNamespace(
        document_id=framework_id,
        task_id=task_id,
        version=1,
        status=ResearchDocumentStatus.CONFIRMED,
        sections=(),
    )
    theory = SimpleNamespace(theory_plan_id=theory_id, task_id=task_id, version=1)
    service = MethodPlanService.in_memory()

    class MutationDouble:
        def claim(self, **_kwargs):
            return ResearchDocumentMutationReceipt(
                request_id=uuid4(),
                user_id=user_id,
                idempotency_key="status-gate",
                operation="create",
                request_hash="hash",
                status="pending",
            )

        def complete(self, **_kwargs):
            return None

        def fail(self, **_kwargs):
            return None

    application = ResearchMethodPlanApplication(
        plans=service,
        research_tasks=SimpleNamespace(),
        mutations=MutationDouble(),
        get_framework=lambda _id: framework,
        get_theory_plan=lambda _id: theory,
    )
    with pytest.raises(ValueError, match="framework-confirmed"):
        application.create(
            user_id=user_id,
            task=task,
            framework_id=framework_id,
            theory_plan_id=theory_id,
            method_kind=MethodKind.QUALITATIVE,
            idempotency_key="status-gate",
        )
    assert service.latest_for_task(task_id) is None


def test_revising_method_kind_adds_the_required_path_sections() -> None:
    service = MethodPlanService.in_memory()
    plan = service.create(
        task_id=UUID(int=1),
        framework_id=UUID(int=2),
        framework_version=1,
        theory_plan_id=UUID(int=3),
        theory_plan_version=1,
        research_question="问题",
        theory_summary="理论",
        material_constraints=(),
        ethical_constraints=(),
        method_kind=MethodKind.QUALITATIVE,
    )
    revised = service.revise(
        plan_id=plan.plan_id,
        expected_version=1,
        method_kind=MethodKind.QUANTITATIVE,
        sections=(MethodPlanSection("design", "研究设计", "用户设计", "user"),),
        rationale="改用定量路径",
        change_summary="选择定量研究",
        actor="user",
    )
    keys = {section.key for section in revised.sections}
    assert {
        "design",
        "operationalization",
        "variables_indicators",
        "hypotheses",
        "measurement",
        "sampling",
        "analysis_plan",
        "conditions",
        "limitations",
        "ethics",
    } <= keys
    assert (
        next(section for section in revised.sections if section.key == "design").content
        == "用户设计"
    )


def test_method_plan_cannot_confirm_untouched_system_prompts() -> None:
    service = MethodPlanService.in_memory()
    plan = service.create(
        task_id=UUID(int=21),
        framework_id=UUID(int=22),
        framework_version=1,
        theory_plan_id=UUID(int=23),
        theory_plan_version=1,
        research_question="问题",
        theory_summary="理论",
        material_constraints=(),
        ethical_constraints=(),
        method_kind=MethodKind.MIXED,
    )
    with pytest.raises(ValueError, match="requires user decisions"):
        service.confirm(plan_id=plan.plan_id, expected_version=plan.version, reason="确认")


def test_stale_plan_cannot_be_restored_into_a_confirmable_current_plan() -> None:
    service = MethodPlanService.in_memory()
    plan = service.create(
        task_id=UUID(int=1),
        framework_id=UUID(int=2),
        framework_version=1,
        theory_plan_id=UUID(int=3),
        theory_plan_version=1,
        research_question="问题",
        theory_summary="理论",
        material_constraints=(),
        ethical_constraints=(),
        method_kind=MethodKind.QUALITATIVE,
    )
    stale = service.mark_stale(plan_id=plan.plan_id, reason="理论已更新")
    with pytest.raises(ValueError, match="stale method plan"):
        service.restore(
            plan_id=plan.plan_id,
            source_version=plan.version,
            expected_version=stale.version,
            reason="尝试恢复旧计划",
        )
