from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

import qunxue_api.modules.research_framework as framework

NOW = datetime(2026, 8, 20, 2, 0, tzinfo=UTC)
DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000101")
REVISION_IDS = (
    UUID("00000000-0000-0000-0000-000000000201"),
    UUID("00000000-0000-0000-0000-000000000202"),
    UUID("00000000-0000-0000-0000-000000000203"),
    UUID("00000000-0000-0000-0000-000000000204"),
)


class MemoryDocumentRepository:
    def __init__(self) -> None:
        self.versions: dict[UUID, list[object]] = {}

    def add(self, snapshot):
        self.versions.setdefault(snapshot.document_id, []).append(snapshot)
        return snapshot

    def latest(self, document_id):
        items = self.versions.get(document_id, [])
        return items[-1] if items else None

    def get_version(self, document_id, version):
        return next(
            (item for item in self.versions.get(document_id, []) if item.version == version),
            None,
        )

    def list_versions(self, document_id):
        return tuple(self.versions.get(document_id, []))

    def list_for_task(self, task_id):
        return tuple(
            items[-1]
            for items in self.versions.values()
            if items and items[-1].task_id == task_id
        )

    def find_for_task_and_plan(self, task_id, theory_plan_id):
        return next(
            (
                items[-1]
                for items in self.versions.values()
                if items
                and items[-1].task_id == task_id
                and items[-1].theory_plan_id == theory_plan_id
            ),
            None,
        )


def section(
    key: str,
    title: str,
    content: str,
    *,
    status: str = "reviewed",
    with_evidence: bool = False,
):
    section_type = framework.ResearchDocumentSection
    status_type = framework.ResearchDocumentSectionStatus
    return section_type(
        section_id=key,
        key=key,
        title=title,
        content=content,
        status=status_type(status),
        evidence_refs=(
            (
                framework.ResearchDocumentEvidenceRef(
                    evidence_ref_id="evidence-1",
                    source_id="source-1",
                    knowledge_release_id="release-final-1",
                ),
            )
            if with_evidence
            else ()
        ),
    )


def required_sections():
    values = (
        ("research_question", "研究问题"),
        ("research_object_and_field", "研究对象与场域"),
        ("theoretical_perspective", "理论视角"),
        ("core_concepts", "核心概念"),
        ("mechanisms", "作用机制"),
        ("questions_or_hypotheses", "研究假设与质性问题"),
        ("methodology", "研究方法"),
        ("sample_and_sources", "样本与资料来源"),
        ("analysis_steps", "分析步骤"),
        ("ethics", "伦理风险"),
        ("limitations", "局限"),
        ("evidence_gaps", "证据缺口"),
    )
    return tuple(
        section(
            key,
            title,
            f"{title}的可编辑正文。",
            with_evidence=key
            in {
                "theoretical_perspective",
                "core_concepts",
                "mechanisms",
                "questions_or_hypotheses",
                "methodology",
                "analysis_steps",
            },
        )
        for key, title in values
    )


def service(repository: MemoryDocumentRepository):
    service_type = framework.ResearchDocumentService
    ids = iter((DOCUMENT_ID, *REVISION_IDS))
    return service_type(
        repository=repository,
        id_factory=lambda: next(ids),
        clock=lambda: NOW,
    )


def test_revisions_are_immutable_and_an_older_version_can_be_restored() -> None:
    repository = MemoryDocumentRepository()
    workflow = service(repository)
    created = workflow.create(
        task_id=UUID(int=1),
        theory_plan_id=UUID(int=2),
        knowledge_release_id="release-final-1",
        title="社区互助研究框架",
        sections=required_sections(),
    )

    revised_sections = list(created.sections)
    revised_sections[0] = section(
        "research_question",
        "研究问题",
        "成员流动如何影响社区互助的持续性？",
    )
    revised = workflow.revise(
        document_id=created.document_id,
        expected_version=1,
        sections=tuple(revised_sections),
        change_summary="收窄研究问题",
        actor="user",
    )
    restored = workflow.restore(
        document_id=created.document_id,
        source_version=1,
        expected_version=2,
        reason="恢复首次草稿",
    )

    assert created.version == 1
    assert created.actor == "user"
    assert revised.version == 2
    assert (
        workflow.get(created.document_id, version=1).sections[0].content == "研究问题的可编辑正文。"
    )
    assert restored.version == 3
    assert restored.restored_from_version == 1
    assert restored.sections == created.sections


def test_revision_rejects_stale_versions_and_cross_release_evidence() -> None:
    repository = MemoryDocumentRepository()
    workflow = service(repository)
    created = workflow.create(
        task_id=UUID(int=1),
        theory_plan_id=UUID(int=2),
        knowledge_release_id="release-final-1",
        title="社区互助研究框架",
        sections=required_sections(),
    )

    with pytest.raises(ValueError, match="stale"):
        workflow.revise(
            document_id=created.document_id,
            expected_version=2,
            sections=created.sections,
            change_summary="错误的并发保存",
            actor="user",
        )

    evidence_type = framework.ResearchDocumentEvidenceRef
    mismatched = list(created.sections)
    mismatched[0] = framework.ResearchDocumentSection(
        section_id="research_question",
        key="research_question",
        title="研究问题",
        content="成员流动如何影响互助？",
        status=framework.ResearchDocumentSectionStatus.REVIEWED,
        evidence_refs=(
            evidence_type(
                evidence_ref_id="evidence-1",
                source_id="source-1",
                knowledge_release_id="release-other",
            ),
        ),
    )
    with pytest.raises(ValueError, match="knowledge release"):
        workflow.revise(
            document_id=created.document_id,
            expected_version=1,
            sections=tuple(mismatched),
            change_summary="绑定证据",
            actor="user",
        )


def test_personal_material_evidence_and_analysis_handoff_follow_document_versions() -> None:
    repository = MemoryDocumentRepository()
    workflow = service(repository)
    personal_ref = framework.ResearchDocumentEvidenceRef(
        evidence_ref_id="analysis-annotation:00000000-0000-0000-0000-000000000301",
        source_id="material-segment:segment-1",
        knowledge_release_id=None,
        source_kind=framework.ResearchDocumentEvidenceSourceKind.PERSONAL_MATERIAL,
        annotation_id=UUID("00000000-0000-0000-0000-000000000301"),
        material_id=UUID("00000000-0000-0000-0000-000000000302"),
        parse_id=UUID("00000000-0000-0000-0000-000000000303"),
        segment_id="segment-1",
        locator={"page": 4, "paragraph": 12},
    )
    sections = list(required_sections())
    sections[0] = replace(sections[0], evidence_refs=(personal_ref,))
    first_analysis = {
        "schema_version": "research-analysis-v1",
        "content_hash": "analysis-v1",
        "annotations": [
            {
                "annotation_id": str(personal_ref.annotation_id),
                "material_id": str(personal_ref.material_id),
                "parse_id": str(personal_ref.parse_id),
                "segment_id": personal_ref.segment_id,
                "quote_hash": "a" * 64,
                "locator": personal_ref.locator,
                "source_available": True,
            }
        ],
        "codes": [],
        "memos": [],
        "comparisons": [],
        "unavailable_annotation_ids": [],
    }
    created = workflow.create(
        task_id=UUID(int=1),
        theory_plan_id=UUID(int=2),
        knowledge_release_id="release-final-1",
        title="社区互助研究框架",
        sections=tuple(sections),
        analysis_handoff=first_analysis,
    )
    second_analysis = {**first_analysis, "content_hash": "analysis-v2"}
    revised = workflow.revise(
        document_id=created.document_id,
        expected_version=created.version,
        sections=created.sections,
        change_summary="纳入新确认的分析备忘",
        actor="user",
        analysis_handoff=second_analysis,
    )
    restored = workflow.restore(
        document_id=created.document_id,
        source_version=created.version,
        expected_version=revised.version,
        reason="恢复首次分析快照",
    )

    assert created.analysis_handoff == first_analysis
    assert revised.analysis_handoff == second_analysis
    assert restored.analysis_handoff == first_analysis
    assert restored.sections[0].evidence_refs == (personal_ref,)


def test_confirmed_export_is_rendered_from_the_same_formal_version() -> None:
    repository = MemoryDocumentRepository()
    workflow = service(repository)
    sections = list(required_sections())
    sections[0] = framework.ResearchDocumentSection(
        section_id="research_question",
        key="research_question",
        title="研究问题",
        content="研究问题的可编辑正文。",
        status=framework.ResearchDocumentSectionStatus.REVIEWED,
        evidence_refs=(
            framework.ResearchDocumentEvidenceRef(
                evidence_ref_id="evidence-1",
                source_id="source-1",
                knowledge_release_id="release-final-1",
            ),
        ),
    )
    created = workflow.create(
        task_id=UUID(int=1),
        theory_plan_id=UUID(int=2),
        knowledge_release_id="release-final-1",
        title="社区互助研究框架",
        sections=tuple(sections),
    )
    confirmed = workflow.confirm(
        document_id=created.document_id,
        expected_version=1,
    )
    exported = workflow.export_markdown(
        document_id=created.document_id,
        version=confirmed.version,
    )

    assert confirmed.version == 2
    assert confirmed.status.value == "confirmed"
    assert exported.version == confirmed.version
    assert exported.knowledge_release_id == "release-final-1"
    assert exported.markdown.startswith("---\n")
    assert "---\n\n# 社区互助研究框架\n" in exported.markdown
    assert "## 研究问题\n\n研究问题的可编辑正文。" in exported.markdown
    assert "evidence-1" in exported.markdown
    assert "source-1" in exported.markdown
    assert f"document_id: {DOCUMENT_ID}" in exported.markdown


def test_confirmation_requires_every_framework_section_and_no_pending_user_decision() -> None:
    repository = MemoryDocumentRepository()
    workflow = service(repository)
    incomplete = workflow.create(
        task_id=UUID(int=1),
        theory_plan_id=UUID(int=2),
        knowledge_release_id="release-final-1",
        title="不完整框架",
        sections=(section("research_question", "研究问题", "一个问题"),),
    )
    with pytest.raises(ValueError, match="required sections"):
        workflow.confirm(document_id=incomplete.document_id, expected_version=1)

    pending_sections = list(required_sections())
    pending_sections[2] = section(
        "theoretical_perspective",
        "理论视角",
        "需要用户选择主理论。",
        status="needs_user_decision",
    )
    another_repository = MemoryDocumentRepository()
    another_workflow = service(another_repository)
    pending = another_workflow.create(
        task_id=UUID(int=1),
        theory_plan_id=UUID(int=2),
        knowledge_release_id="release-final-1",
        title="待决定框架",
        sections=tuple(pending_sections),
    )
    with pytest.raises(ValueError, match="user decisions"):
        another_workflow.confirm(document_id=pending.document_id, expected_version=1)


def test_one_confirmed_theory_plan_can_create_only_one_research_document() -> None:
    repository = MemoryDocumentRepository()
    workflow = service(repository)
    first = workflow.create(
        task_id=UUID(int=1),
        theory_plan_id=UUID(int=2),
        knowledge_release_id="release-final-1",
        title="社区互助研究框架",
        sections=required_sections(),
    )

    replayed = workflow.create(
        task_id=UUID(int=1),
        theory_plan_id=UUID(int=2),
        knowledge_release_id="release-final-1",
        title="社区互助研究框架",
        sections=required_sections(),
    )

    assert replayed.document_id == first.document_id
    assert replayed.revision_id == first.revision_id
    assert len(repository.versions) == 1


def test_completion_gate_explains_unreviewed_sections_and_pending_agent_suggestions() -> None:
    repository = MemoryDocumentRepository()
    workflow = service(repository)
    draft_sections = list(required_sections())
    draft_sections[6] = section(
        "methodology",
        "研究方法",
        "方法仍待审阅。",
        status="draft",
        with_evidence=True,
    )
    created = workflow.create(
        task_id=UUID(int=1),
        theory_plan_id=UUID(int=2),
        knowledge_release_id="release-final-1",
        title="社区互助研究框架",
        sections=tuple(draft_sections),
    )

    gate = workflow.completion_gate(
        document_id=created.document_id,
        pending_proposal_count=2,
    )

    checks = {check.code: check for check in gate.checks}
    assert gate.ready is False
    assert checks["required_sections"].passed is True
    assert checks["section_review"].passed is False
    assert checks["pending_proposals"].passed is False
    assert checks["evidence_gaps_disclosed"].passed is True
    assert checks["exportable"].passed is False
    assert gate.blockers == (
        "章节“研究方法”仍待审阅。",
        "还有 2 条 Agent 建议待处理。",
    )

    with pytest.raises(ValueError, match="completion gate"):
        workflow.confirm(
            document_id=created.document_id,
            expected_version=created.version,
            pending_proposal_count=2,
        )


def test_completion_gate_requires_provenance_or_an_explicit_gap_for_key_judgments() -> None:
    repository = MemoryDocumentRepository()
    workflow = service(repository)
    created = workflow.create(
        task_id=UUID(int=1),
        theory_plan_id=UUID(int=2),
        knowledge_release_id="release-final-1",
        title="社区互助研究框架",
        sections=tuple(
            replace(item, evidence_refs=()) for item in required_sections()
        ),
    )

    gate = workflow.completion_gate(document_id=created.document_id)

    provenance = next(check for check in gate.checks if check.code == "critical_provenance")
    assert provenance.passed is False
    assert "理论视角" in provenance.detail
    assert any("需要引用" in blocker for blocker in gate.blockers)


def test_restoring_a_formal_version_revokes_its_latest_export_status() -> None:
    repository = MemoryDocumentRepository()
    workflow = service(repository)
    created = workflow.create(
        task_id=UUID(int=1),
        theory_plan_id=UUID(int=2),
        knowledge_release_id="release-final-1",
        title="社区互助研究框架",
        sections=required_sections(),
    )
    confirmed = workflow.confirm(
        document_id=created.document_id,
        expected_version=created.version,
    )
    workflow.restore(
        document_id=created.document_id,
        source_version=confirmed.version,
        expected_version=confirmed.version,
        reason="继续修改正式框架",
    )

    with pytest.raises(ValueError, match="latest confirmed"):
        workflow.export_markdown(
            document_id=confirmed.document_id,
            version=confirmed.version,
        )
