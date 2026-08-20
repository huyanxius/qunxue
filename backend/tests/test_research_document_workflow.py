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


def section(key: str, title: str, content: str, *, status: str = "reviewed"):
    section_type = framework.ResearchDocumentSection
    status_type = framework.ResearchDocumentSectionStatus
    return section_type(
        section_id=key,
        key=key,
        title=title,
        content=content,
        status=status_type(status),
        evidence_refs=(),
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
    return tuple(section(key, title, f"{title}的可编辑正文。") for key, title in values)


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
