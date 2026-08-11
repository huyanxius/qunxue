from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from qunxue_api.modules.knowledge_catalog import KnowledgeReleaseLevel, KnowledgeReleaseRef
from qunxue_api.modules.research_framework import (
    AuditFindingDraft,
    AuditFindingSeverity,
    AuditFindingType,
    AuditOverallStatus,
    AuditResolution,
    AuditResolutionAction,
    FrameworkAuditDraft,
    FrameworkConfirmationBlocked,
    FrameworkContentOrigin,
    FrameworkRevisionConflict,
    MethodIntentSnapshot,
    ResearchFrameworkDraft,
    ResearchFrameworkDraftInput,
    ResearchFrameworkService,
)
from qunxue_api.modules.research_intake import ConfirmedPhenomenonSnapshot
from qunxue_api.modules.theory_matching import (
    ConfirmedTheoryPlanSnapshot,
    EvidenceBundleSnapshot,
)

NOW = datetime(2026, 8, 11, 9, 0, tzinfo=UTC)


class MemoryFrameworkRepository:
    def __init__(self) -> None:
        self.records = {}

    def add(self, record):
        self.records[record.framework_id] = record
        return record

    def get(self, framework_id):
        return self.records.get(framework_id)

    def save(self, record, *, expected_version):
        current = self.records.get(record.framework_id)
        if current is None or current.current.version != expected_version:
            return None
        self.records[record.framework_id] = record
        return record


class FixedDrafter:
    def draft(self, *, input):
        return ResearchFrameworkDraft(
            concept_mappings=(),
            evidence_requirements=(),
            inference_links=(),
            alternative_explanations=("资源供给变化",),
            method_plan=None,
            scope_and_limitations=("仅解释已确认的现象范围",),
            unresolved_items=("缺少竞争解释区分材料",),
            next_actions=("补充去标识化访谈摘要",),
            ethical_boundaries=("不上传未授权的原始材料",),
        )


class BlockingAuditor:
    def audit(self, *, framework):
        return FrameworkAuditDraft(
            overall_status=AuditOverallStatus.REVISE,
            findings=(
                AuditFindingDraft(
                    finding_type=AuditFindingType.EVIDENCE,
                    severity=AuditFindingSeverity.BLOCKING,
                    summary="区分性证据不足",
                    reason="草稿仍保留未解决项",
                    impact="无法排除替代解释",
                    recommendation="补充区分性材料并重新审校",
                    blocking=True,
                ),
            ),
        )


def _input() -> ResearchFrameworkDraftInput:
    phenomenon = ConfirmedPhenomenonSnapshot(
        task_id=UUID(int=1),
        phenomenon_query_id=UUID(int=2),
        version=1,
        phenomenon="社区互助为何随成员流动减少？",
        research_intent="区分关系与资源解释",
        context="社区成员持续流动",
        content_hash="a" * 64,
    )
    release = KnowledgeReleaseRef(
        knowledge_release_id="release-1",
        level=KnowledgeReleaseLevel.PREVIEW,
        content_hash="sha256:release",
    )
    plan = ConfirmedTheoryPlanSnapshot(
        theory_plan_id=UUID(int=3),
        task_id=phenomenon.task_id,
        match_run_id=UUID(int=4),
        decision_set_id=UUID(int=5),
        version=1,
        phenomenon=phenomenon,
        knowledge_release=release,
        evidence_bundle=EvidenceBundleSnapshot(
            evidence_bundle_id="bundle-1",
            version=1,
            content_hash="sha256:bundle",
            release=release,
            theory_profiles=(),
            evidence_items=(),
        ),
        candidates=(),
        decisions=(),
        use_assignments=(),
        relations=(),
        confirmed_at=NOW,
    )
    return ResearchFrameworkDraftInput(
        theory_plan=plan,
        original_research_question="社区互助为什么减少？",
        confirmed_research_question="成员流动如何影响社区互助？",
        question_adjustment_reason="收窄为可检验的关系",
        research_object="社区成员",
        analysis_unit="成员关系",
        context=phenomenon.context,
        method_intent=MethodIntentSnapshot(
            method_kind="访谈",
            constraints=("仅使用去标识化摘要",),
            source="user_confirmed",
        ),
    )


def _service() -> ResearchFrameworkService:
    ids = iter(UUID(int=value) for value in range(10, 100))
    return ResearchFrameworkService(
        drafter=FixedDrafter(),
        auditor=BlockingAuditor(),
        repository=MemoryFrameworkRepository(),
        id_factory=lambda: next(ids),
        clock=lambda: NOW,
    )


def test_generation_requires_a_confirmed_theory_plan_snapshot() -> None:
    service = _service()

    with pytest.raises(TypeError, match="confirmed theory plan"):
        service.create_draft(input=replace(_input(), theory_plan=None))  # type: ignore[arg-type]


def test_revision_is_append_only_and_invalidates_the_old_review() -> None:
    service = _service()
    initial = service.create_draft(input=_input())
    review = service.start_review(
        framework_id=initial.framework_id,
        expected_version=initial.version,
    )
    finding = review.audit.findings[0]

    revised = service.revise(
        framework_id=initial.framework_id,
        expected_version=initial.version,
        audit_id=review.audit.audit_id,
        revised_draft=replace(initial.draft, unresolved_items=()),
        resolutions=(
            AuditResolution(
                finding_id=finding.finding_id,
                action=AuditResolutionAction.ACCEPT,
                reason="已按建议补充区分材料",
            ),
        ),
        revision_reason="处理区分性证据意见",
    )

    assert initial.version == 1
    assert revised.version == 2
    assert revised.previous_revision_id == initial.revision_id
    assert revised.content_origin is FrameworkContentOrigin.USER_MODIFIED
    assert service.get(initial.framework_id).version == 2
    assert service.list_versions(initial.framework_id) == (initial, revised)
    assert service.get_audit(review.audit.audit_id).is_stale is True


def test_stale_revision_cannot_overwrite_a_newer_version() -> None:
    service = _service()
    initial = service.create_draft(input=_input())
    review = service.start_review(
        framework_id=initial.framework_id,
        expected_version=initial.version,
    )

    service.revise(
        framework_id=initial.framework_id,
        expected_version=1,
        audit_id=review.audit.audit_id,
        revised_draft=replace(initial.draft, next_actions=("补充时间序列",)),
        resolutions=(),
        revision_reason="补充行动",
    )
    with pytest.raises(FrameworkRevisionConflict):
        service.revise(
            framework_id=initial.framework_id,
            expected_version=1,
            audit_id=review.audit.audit_id,
            revised_draft=initial.draft,
            resolutions=(),
            revision_reason="过期编辑",
        )


def test_blocking_finding_requires_override_before_confirmation() -> None:
    service = _service()
    framework = service.create_draft(input=_input())
    review = service.start_review(
        framework_id=framework.framework_id,
        expected_version=framework.version,
    )
    finding = review.audit.findings[0]

    with pytest.raises(FrameworkConfirmationBlocked):
        service.confirm(
            framework_id=framework.framework_id,
            expected_version=framework.version,
            audit_id=review.audit.audit_id,
            resolutions=(
                AuditResolution(
                    finding_id=finding.finding_id,
                    action=AuditResolutionAction.DEFER,
                    reason="等待补充材料",
                ),
            ),
        )

    confirmed = service.confirm(
        framework_id=framework.framework_id,
        expected_version=framework.version,
        audit_id=review.audit.audit_id,
        resolutions=(
            AuditResolution(
                finding_id=finding.finding_id,
                action=AuditResolutionAction.OVERRIDE,
                reason="在探索性研究范围内接受该限制",
            ),
        ),
    )

    assert confirmed.framework == framework
    assert confirmed.unresolved_finding_ids == (finding.finding_id,)
    assert confirmed.resolutions[0].reason.startswith("在探索性")
