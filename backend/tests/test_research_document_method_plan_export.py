from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from qunxue_api.api.contracts.research_documents import ResearchDocumentExportManifest
from qunxue_api.application.research_documents import (
    ResearchDocumentApplication,
    _export_manifest,
    _export_markdown,
)
from qunxue_api.modules.research_framework import (
    ResearchDocumentCompletionGate,
    ResearchDocumentMarkdownExport,
)
from qunxue_api.modules.research_intake import EntryType, ResearchTask, ResearchTaskStatus
from qunxue_api.modules.research_method import (
    MethodKind,
    MethodPlanConstraints,
    MethodPlanSection,
    MethodPlanSnapshot,
    MethodPlanStatus,
)

NOW = datetime(2026, 8, 31, 8, 0, tzinfo=UTC)
DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000201")
TASK_ID = UUID("00000000-0000-0000-0000-000000000202")
THEORY_PLAN_ID = UUID("00000000-0000-0000-0000-000000000203")
METHOD_PLAN_ID = UUID("00000000-0000-0000-0000-000000000204")


def _method_plan() -> MethodPlanSnapshot:
    return MethodPlanSnapshot(
        plan_id=METHOD_PLAN_ID,
        task_id=TASK_ID,
        framework_id=DOCUMENT_ID,
        framework_version=2,
        theory_plan_id=THEORY_PLAN_ID,
        theory_plan_version=3,
        method_kind=MethodKind.QUALITATIVE,
        decision_source="user_decision",
        rationale="以质性比较理解照护协商机制。",
        research_question="迁移如何改变家庭照护责任？",
        theory_summary="关注资源与协商机制。",
        shared_constraints=MethodPlanConstraints(
            material_constraints=("仅使用已获授权的个人材料。",),
            ethical_constraints=("去标识化并允许撤回。",),
            theory_concepts=("照护协商",),
            evidence_ref_ids=("evidence-1",),
            knowledge_release_id="release-final-1",
        ),
        sections=(
            MethodPlanSection("design", "研究设计", "开展跨案例质性比较。", "user"),
        ),
        reviews=(),
        status=MethodPlanStatus.CONFIRMED,
        version=4,
        revision_id=UUID("00000000-0000-0000-0000-000000000205"),
        change_summary="用户确认质性研究方法。",
        actor="user",
        created_at=NOW,
        confirmed_at=NOW,
    )


def _document() -> SimpleNamespace:
    return SimpleNamespace(
        document_id=DOCUMENT_ID,
        task_id=TASK_ID,
        theory_plan_id=THEORY_PLAN_ID,
        knowledge_release_id="release-final-1",
        version=2,
        title="家庭照护研究框架",
        status=SimpleNamespace(value="confirmed"),
        sections=(),
        confirmed_at=NOW,
        created_at=NOW,
        analysis_handoff=None,
        formatting=SimpleNamespace(
            template_id="chinese-social-science",
            csl_style_id="china-national-standard-gb-t-7714-2015-author-date",
            locale="zh-CN",
            custom_csl=None,
            custom_css=None,
        ),
        revision_id=UUID("00000000-0000-0000-0000-000000000207"),
        change_summary="确认研究框架。",
        actor="user",
        restored_from_version=None,
    )


def _theory_plan() -> SimpleNamespace:
    return SimpleNamespace(
        theory_plan_id=THEORY_PLAN_ID,
        task_id=TASK_ID,
        match_run_id=UUID("00000000-0000-0000-0000-000000000208"),
        version=3,
        phenomenon=SimpleNamespace(
            phenomenon_query_id=UUID("00000000-0000-0000-0000-000000000206"),
            version=1,
            phenomenon="迁移如何改变家庭照护责任？",
            research_intent="解释照护责任变化。",
            context="家庭迁移",
            content_hash="sha256:phenomenon",
            evidence_refs=(),
        ),
        knowledge_release=SimpleNamespace(
            knowledge_release_id="release-final-1",
            level=SimpleNamespace(value="final"),
            content_hash="sha256:release",
        ),
        evidence_bundle=SimpleNamespace(evidence_items=()),
        decisions=(),
        use_assignments=(),
        relations=(),
    )


class _ExportDocuments:
    def __init__(self, document: SimpleNamespace) -> None:
        self.document = document

    def get(self, _document_id: UUID, version: int | None = None) -> SimpleNamespace:
        return self.document

    def export_markdown(
        self, *, document_id: UUID, version: int | None = None
    ) -> ResearchDocumentMarkdownExport:
        return ResearchDocumentMarkdownExport(
            document_id=document_id,
            task_id=TASK_ID,
            theory_plan_id=THEORY_PLAN_ID,
            knowledge_release_id="release-final-1",
            version=2,
            filename="research-framework-v2.md",
            media_type="text/markdown",
            markdown="",
        )

    def list_versions(self, _document_id: UUID) -> tuple[SimpleNamespace, ...]:
        return (self.document,)

    def completion_gate(
        self, *, document_id: UUID, pending_proposal_count: int
    ) -> ResearchDocumentCompletionGate:
        return ResearchDocumentCompletionGate(
            document_id=document_id,
            version=2,
            ready=True,
            pending_proposal_count=pending_proposal_count,
            blockers=(),
            checks=(),
        )


class _ExportTasks:
    def __init__(self) -> None:
        self.task = ResearchTask(
            task_id=TASK_ID,
            user_id=UUID("00000000-0000-0000-0000-000000000209"),
            entry_type=EntryType.DIRECT_INPUT,
            status=ResearchTaskStatus.FRAMEWORK_CONFIRMED,
            version=1,
            idempotency_key="export-task",
            created_at=NOW,
            updated_at=NOW,
            current_theory_plan_id=THEORY_PLAN_ID,
            current_framework_id=DOCUMENT_ID,
        )

    def get(self, task_id: UUID, user_id: UUID) -> ResearchTask | None:
        return self.task if (task_id, user_id) == (TASK_ID, self.task.user_id) else None


def _export_application(method_plan: MethodPlanSnapshot) -> ResearchDocumentApplication:
    return ResearchDocumentApplication(
        documents=_ExportDocuments(_document()),
        research_tasks=_ExportTasks(),
        mutations=SimpleNamespace(),
        get_theory_plan=lambda value: _theory_plan() if value == THEORY_PLAN_ID else None,
        get_match_run=lambda _value: SimpleNamespace(model=None, candidates=()),
        list_proposals_for_task=lambda _value: (),
        list_actionable_proposals_for_task=lambda _value: (),
        owns_match_run=lambda **_kwargs: True,
        get_method_plan=lambda _task_id: method_plan,
    )


def test_export_manifest_contains_confirmed_method_plan_and_markdown_section() -> None:
    manifest = _export_manifest(
        document=_document(),
        plan=_theory_plan(),
        match_run=SimpleNamespace(model=None, candidates=()),
        proposals=(),
        versions=(_document(),),
        method_plan=_method_plan(),
    )

    exported = manifest["method_plan"]
    assert isinstance(exported, dict)
    assert exported["plan_id"] == str(METHOD_PLAN_ID)
    assert exported["status"] == "confirmed"
    assert exported["decision_source"] == "user_decision"
    assert exported["theory_concepts"] == ["照护协商"]
    assert exported["sections"][0]["source"] == "user"
    contract = ResearchDocumentExportManifest.model_validate(manifest)
    assert contract.method_plan is not None
    assert contract.method_plan.status is MethodPlanStatus.CONFIRMED

    markdown = _export_markdown(
        base=ResearchDocumentMarkdownExport(
            document_id=DOCUMENT_ID,
            task_id=TASK_ID,
            theory_plan_id=THEORY_PLAN_ID,
            knowledge_release_id="release-final-1",
            version=2,
            filename="research-framework-v2.md",
            media_type="text/markdown",
            markdown="",
        ),
        manifest=manifest,
    )
    assert "## 正式研究方法计划" in markdown
    assert "用户决定" in markdown
    assert "照护协商" in markdown


def test_export_rejects_unconfirmed_method_plan_without_creating_a_package() -> None:
    application = _export_application(
        replace(_method_plan(), status=MethodPlanStatus.DRAFT)
    )

    with pytest.raises(ValueError, match="confirmed method plan"):
        application.export_markdown(
            user_id=UUID("00000000-0000-0000-0000-000000000209"),
            document_id=DOCUMENT_ID,
            version=None,
        )


def test_completion_gate_reports_unconfirmed_method_plan_as_delivery_blocker() -> None:
    application = _export_application(
        replace(_method_plan(), status=MethodPlanStatus.UNDER_REVIEW)
    )

    gate = application.completion_gate(
        user_id=UUID("00000000-0000-0000-0000-000000000209"),
        document_id=DOCUMENT_ID,
    )

    delivery = next(item for item in gate.checks if item.code == "delivery_package")
    assert gate.ready is False
    assert delivery.passed is False
    assert "方法计划" in gate.blockers[-1]


def test_export_rejects_method_plan_from_a_different_framework_version() -> None:
    method_plan = _method_plan()
    application = _export_application(
        replace(method_plan, framework_version=method_plan.framework_version + 1)
    )

    with pytest.raises(ValueError, match="does not match"):
        application.export_markdown(
            user_id=UUID("00000000-0000-0000-0000-000000000209"),
            document_id=DOCUMENT_ID,
            version=None,
        )
