from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from qunxue_api.application.research_document_mutations import (
    ResearchDocumentMutationReceipt,
)
from qunxue_api.application.research_documents import (
    ResearchDocumentApplication,
    _export_manifest,
    _export_markdown,
)
from qunxue_api.modules.knowledge_catalog import (
    SourceRecordSnapshot,
    SourceVerificationStatus,
)
from qunxue_api.modules.research_analysis import (
    AnalysisAnnotation,
    AnalysisAnnotationKind,
    AnalysisCode,
    AnalysisCodeStatus,
    ResearchAnalysisHandoff,
)
from qunxue_api.modules.research_framework import (
    ResearchDocumentEvidenceRef,
    ResearchDocumentEvidenceSourceKind,
    ResearchDocumentMarkdownExport,
    ResearchDocumentSection,
    ResearchDocumentSectionStatus,
    ResearchDocumentService,
)
from qunxue_api.modules.research_intake import EntryType, ResearchTask, ResearchTaskStatus
from qunxue_api.modules.research_materials import MaterialLocator
from qunxue_api.modules.theory_matching import EvidenceItemSnapshot

NOW = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)
USER_ID = UUID("00000000-0000-0000-0000-000000000101")
TASK_ID = UUID("00000000-0000-0000-0000-000000000102")
PLAN_ID = UUID("00000000-0000-0000-0000-000000000103")
MATCH_RUN_ID = UUID("00000000-0000-0000-0000-000000000104")
ANNOTATION_ID = UUID("00000000-0000-0000-0000-000000000105")
MATERIAL_ID = UUID("00000000-0000-0000-0000-000000000106")
PARSE_ID = UUID("00000000-0000-0000-0000-000000000107")


class MemoryDocuments:
    def __init__(self) -> None:
        self.items: dict[UUID, list[object]] = {}

    def add(self, snapshot):
        self.items.setdefault(snapshot.document_id, []).append(snapshot)
        return snapshot

    def latest(self, document_id):
        values = self.items.get(document_id, [])
        return values[-1] if values else None

    def get_version(self, document_id, version):
        return next(
            (item for item in self.items.get(document_id, []) if item.version == version),
            None,
        )

    def list_versions(self, document_id):
        return tuple(reversed(self.items.get(document_id, [])))

    def list_for_task(self, task_id):
        return tuple(
            values[-1]
            for values in self.items.values()
            if values and values[-1].task_id == task_id
        )


class Tasks:
    def __init__(self) -> None:
        self.task = ResearchTask(
            task_id=TASK_ID,
            user_id=USER_ID,
            entry_type=EntryType.DIRECT_INPUT,
            status=ResearchTaskStatus.THEORY_PLAN_CONFIRMED,
            version=1,
            idempotency_key="task-analysis-handoff",
            created_at=NOW,
            updated_at=NOW,
            current_theory_plan_id=PLAN_ID,
        )

    def get(self, task_id, user_id):
        if self.task.task_id == task_id and self.task.user_id == user_id:
            return self.task
        return None

    def save_progress(self, snapshot):
        self.task = snapshot
        return snapshot


class Mutations:
    def __init__(self) -> None:
        self.completed: dict[UUID, tuple[UUID, int]] = {}

    def claim(self, *, user_id, idempotency_key, operation, request_hash):
        del idempotency_key, operation, request_hash
        return ResearchDocumentMutationReceipt(
            request_id=UUID(int=len(self.completed) + 1),
            user_id=user_id,
            idempotency_key="request",
            operation="document",
            request_hash="hash",
            status="pending",
        )

    def fail(self, *, request_id):
        return request_id

    def complete(self, *, request_id, result_id, result_version):
        self.completed[request_id] = (result_id, result_version)


def _annotation() -> AnalysisAnnotation:
    return AnalysisAnnotation.create(
        annotation_id=ANNOTATION_ID,
        user_id=USER_ID,
        task_id=TASK_ID,
        material_id=MATERIAL_ID,
        parse_id=PARSE_ID,
        segment_id="segment-1",
        segment_content_hash="a" * 64,
        quote="姐姐承担主要照护。",
        quote_start=0,
        quote_end=9,
        locator=MaterialLocator(page=4, paragraph=12, block_index=3),
        annotation_kind=AnalysisAnnotationKind.DESCRIPTIVE,
        case_label="家庭 A",
        note="迁移后照护责任集中到姐姐。",
        now=NOW,
    )


def _handoff(*, label: str = "照护责任性别化") -> ResearchAnalysisHandoff:
    annotation = _annotation()
    code = AnalysisCode.candidate(
        code_id=UUID("00000000-0000-0000-0000-000000000108"),
        user_id=USER_ID,
        task_id=TASK_ID,
        label=label,
        definition="照护劳动按性别集中分配。",
        annotation_ids=(annotation.annotation_id,),
        rationale="研究者核对原文后建立。",
        source="user",
        now=NOW,
    ).confirm(
        user_confirmed=True,
        expected_version=1,
        reason="用户确认",
        now=NOW,
    )
    return ResearchAnalysisHandoff.create(
        task_id=TASK_ID,
        annotations=(annotation,),
        codes=(code,),
        memos=(),
        comparisons=(),
    )


def _personal_ref() -> ResearchDocumentEvidenceRef:
    return ResearchDocumentEvidenceRef(
        evidence_ref_id=f"analysis-annotation:{ANNOTATION_ID}",
        source_id="material-segment:segment-1",
        knowledge_release_id=None,
        source_kind=ResearchDocumentEvidenceSourceKind.PERSONAL_MATERIAL,
        annotation_id=ANNOTATION_ID,
        material_id=MATERIAL_ID,
        parse_id=PARSE_ID,
        segment_id="segment-1",
        locator={
            "page": 4,
            "section_path": [],
            "paragraph": 12,
            "line_start": None,
            "line_end": None,
            "char_start": None,
            "char_end": None,
            "block_index": 3,
        },
    )


def _sections() -> tuple[ResearchDocumentSection, ...]:
    return (
        ResearchDocumentSection(
            section_id="research_question",
            key="research_question",
            title="研究问题",
            content="迁移如何改变家庭照护责任？",
            status=ResearchDocumentSectionStatus.REVIEWED,
            evidence_refs=(_personal_ref(),),
        ),
    )


def _application(handoff_provider):
    repository = MemoryDocuments()
    tasks = Tasks()
    documents = ResearchDocumentService(
        repository=repository,
        id_factory=iter(UUID(int=value) for value in range(201, 208)).__next__,
        clock=lambda: NOW,
    )
    plan = SimpleNamespace(
        theory_plan_id=PLAN_ID,
        task_id=TASK_ID,
        match_run_id=MATCH_RUN_ID,
        knowledge_release=SimpleNamespace(knowledge_release_id="release-final-1"),
        evidence_bundle=SimpleNamespace(evidence_items=()),
    )
    application = ResearchDocumentApplication(
        documents=documents,
        research_tasks=tasks,
        mutations=Mutations(),
        get_theory_plan=lambda value: plan if value == PLAN_ID else None,
        get_match_run=lambda _value: None,
        list_proposals_for_task=lambda _value: (),
        list_actionable_proposals_for_task=lambda _value: (),
        owns_match_run=lambda **_kwargs: True,
        formal_analysis_handoff=handoff_provider,
    )
    return application, documents, tasks


def test_document_version_pins_sanitized_analysis_and_restore_does_not_read_live() -> None:
    current = [_handoff()]
    calls: list[str] = []

    def handoff_provider(*, user_id, task_id):
        assert (user_id, task_id) == (USER_ID, TASK_ID)
        calls.append(current[0].content_hash)
        return current[0]

    application, documents, tasks = _application(handoff_provider)
    created = application.create(
        user_id=USER_ID,
        task=tasks.task,
        theory_plan_id=PLAN_ID,
        title="家庭照护研究",
        sections=_sections(),
        idempotency_key="create-analysis-document",
    )

    assert created.analysis_handoff is not None
    assert created.analysis_handoff["content_hash"] == current[0].content_hash
    assert created.analysis_handoff["annotations"][0]["annotation_id"] == str(
        ANNOTATION_ID
    )
    assert "quote" not in created.analysis_handoff["annotations"][0]
    assert created.analysis_handoff["codes"][0]["status"] == "confirmed"

    first_hash = created.analysis_handoff["content_hash"]
    current[0] = _handoff(label="迁移后的照护协商")
    revised = application.revise(
        user_id=USER_ID,
        document_id=created.document_id,
        expected_version=created.version,
        sections=created.sections,
        change_summary="纳入新的已确认编码",
        actor="user",
        idempotency_key="revise-analysis-document",
    )
    assert revised.analysis_handoff["content_hash"] == current[0].content_hash
    assert revised.analysis_handoff["content_hash"] != first_hash

    calls_before_restore = len(calls)
    restored = application.restore(
        user_id=USER_ID,
        document_id=created.document_id,
        source_version=created.version,
        expected_version=revised.version,
        reason="恢复第一版分析依据",
        idempotency_key="restore-analysis-document",
    )

    assert len(calls) == calls_before_restore
    assert restored.analysis_handoff["content_hash"] == first_hash
    assert documents.get(created.document_id).analysis_handoff["content_hash"] == first_hash


def test_deleted_source_is_exposed_only_as_a_tombstone_without_changing_pinned_decisions() -> None:
    original = _handoff()
    current = [original]
    application, _, tasks = _application(
        lambda **_kwargs: current[0]
    )
    created = application.create(
        user_id=USER_ID,
        task=tasks.task,
        theory_plan_id=PLAN_ID,
        title="家庭照护研究",
        sections=_sections(),
        idempotency_key="create-before-delete",
    )
    current[0] = ResearchAnalysisHandoff.create(
        task_id=TASK_ID,
        annotations=(),
        codes=original.codes,
        memos=(),
        comparisons=(),
        unavailable_annotation_ids=(ANNOTATION_ID,),
    )

    historical = application.get(
        user_id=USER_ID,
        document_id=created.document_id,
        version=created.version,
    )

    assert historical.analysis_handoff["content_hash"] == original.content_hash
    assert historical.analysis_handoff["codes"] == created.analysis_handoff["codes"]
    assert historical.analysis_handoff["unavailable_annotation_ids"] == [
        str(ANNOTATION_ID)
    ]
    tombstone = historical.analysis_handoff["annotations"][0]
    assert tombstone["source_available"] is False
    assert tombstone["unavailable_reason"] == "source_deleted"
    assert "quote" not in tombstone


def test_export_redacts_deleted_personal_evidence_without_changing_public_evidence() -> None:
    deleted_excerpt = "姐姐承担主要照护。"
    public_excerpt = "照护责任会随家庭资源配置变化。"
    original = _handoff()
    current = [original]
    application, _, tasks = _application(lambda **_kwargs: current[0])
    created = application.create(
        user_id=USER_ID,
        task=tasks.task,
        theory_plan_id=PLAN_ID,
        title="家庭照护研究",
        sections=_sections(),
        idempotency_key="create-before-export-delete",
    )
    current[0] = ResearchAnalysisHandoff.create(
        task_id=TASK_ID,
        annotations=(),
        codes=original.codes,
        memos=(),
        comparisons=(),
        unavailable_annotation_ids=(ANNOTATION_ID,),
    )
    tombstoned = application.get(
        user_id=USER_ID,
        document_id=created.document_id,
        version=created.version,
    )

    personal_source_id = (
        f"research-material:{MATERIAL_ID}:{PARSE_ID}:segment-1"
    )
    personal_evidence = EvidenceItemSnapshot(
        evidence_ref_id="analysis-comparison:1:finding:0:annotation:1",
        claim="迁移后照护责任集中到姐姐。",
        excerpt=deleted_excerpt,
        locator="第4页，第12段",
        source=SourceRecordSnapshot(
            source_id=personal_source_id,
            source_type="personal_research_material",
            title="家庭 A · 个人研究材料",
            authors_or_institution=(),
            year=None,
            publication=None,
            locator="第4页，第12段",
            url=None,
            verification_status=SourceVerificationStatus.VERIFIED,
            use_boundary="用户已确认的案例比较证据。",
        ),
        verification_status=SourceVerificationStatus.VERIFIED,
        use_boundary="用户已确认的案例比较证据。",
    )
    public_evidence = EvidenceItemSnapshot(
        evidence_ref_id="knowledge:evidence-1",
        claim="家庭资源影响照护分工。",
        excerpt=public_excerpt,
        locator="第18页",
        source=SourceRecordSnapshot(
            source_id="source-public-1",
            source_type="reviewed_publication",
            title="家庭资源与照护分工",
            authors_or_institution=("研究者甲",),
            year=2024,
            publication="社会学研究",
            locator="第18页",
            url="https://example.test/public-1",
            verification_status=SourceVerificationStatus.VERIFIED,
            use_boundary="仅支持家庭资源与照护分工的关系。",
        ),
        verification_status=SourceVerificationStatus.VERIFIED,
        use_boundary="仅支持家庭资源与照护分工的关系。",
    )
    plan = SimpleNamespace(
        phenomenon=SimpleNamespace(
            phenomenon_query_id=UUID(int=301),
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
        evidence_bundle=SimpleNamespace(
            evidence_items=(personal_evidence, public_evidence),
        ),
        decisions=(),
        use_assignments=(),
        relations=(),
    )
    manifest = _export_manifest(
        document=tombstoned,
        plan=plan,
        match_run=SimpleNamespace(model=None, candidates=()),
        proposals=(),
        versions=(tombstoned,),
    )

    exported_evidence = {
        item["evidence_ref_id"]: item for item in manifest["evidence"]
    }
    deleted = exported_evidence[personal_evidence.evidence_ref_id]
    assert deleted["excerpt"] is None
    assert deleted["locator"] == personal_evidence.locator
    assert deleted["source"]["source_id"] == personal_source_id
    assert deleted["source_available"] is False
    assert deleted["unavailable_reason"] == "source_deleted"
    assert exported_evidence[public_evidence.evidence_ref_id] == {
        "evidence_ref_id": public_evidence.evidence_ref_id,
        "claim": public_evidence.claim,
        "excerpt": public_excerpt,
        "locator": public_evidence.locator,
        "verification_status": "verified",
        "use_boundary": public_evidence.use_boundary,
        "source": {
            "source_id": "source-public-1",
            "source_type": "reviewed_publication",
            "title": "家庭资源与照护分工",
            "authors_or_institution": ["研究者甲"],
            "year": 2024,
            "publication": "社会学研究",
            "locator": "第18页",
            "url": "https://example.test/public-1",
            "verification_status": "verified",
            "use_boundary": "仅支持家庭资源与照护分工的关系。",
        },
    }

    markdown = _export_markdown(
        base=ResearchDocumentMarkdownExport(
            document_id=tombstoned.document_id,
            task_id=tombstoned.task_id,
            theory_plan_id=tombstoned.theory_plan_id,
            knowledge_release_id=tombstoned.knowledge_release_id,
            version=tombstoned.version,
            filename="research-framework-v1.md",
            media_type="text/markdown",
            markdown="",
        ),
        manifest=manifest,
    )
    assert "来源已删除（已保留引用定位，不包含原文）" in markdown
    assert deleted_excerpt not in markdown
    assert public_excerpt in markdown


def test_export_redacts_personal_evidence_when_handoff_keeps_only_unavailable_id() -> None:
    deleted_excerpt = "仅在原始访谈中出现的删除片段。"
    original = _handoff()
    current = [original]
    application, _, tasks = _application(lambda **_kwargs: current[0])
    created = application.create(
        user_id=USER_ID,
        task=tasks.task,
        theory_plan_id=PLAN_ID,
        title="家庭照护研究",
        sections=_sections(),
        idempotency_key="create-before-filtered-export-delete",
    )
    current[0] = ResearchAnalysisHandoff.create(
        task_id=TASK_ID,
        annotations=(),
        codes=original.codes,
        memos=(),
        comparisons=(),
        unavailable_annotation_ids=(ANNOTATION_ID,),
    )
    tombstoned = application.get(
        user_id=USER_ID,
        document_id=created.document_id,
        version=created.version,
    )
    assert tombstoned.analysis_handoff is not None
    filtered_handoff = {
        **tombstoned.analysis_handoff,
        "annotations": [],
        "comparisons": [
            {
                "comparison_id": "00000000-0000-0000-0000-000000000109",
                "findings": [
                    {"annotation_ids": [str(ANNOTATION_ID)]},
                ],
            },
        ],
        "unavailable_annotation_ids": [str(ANNOTATION_ID)],
    }
    filtered_document = replace(
        tombstoned,
        analysis_handoff=filtered_handoff,
    )
    personal_evidence = EvidenceItemSnapshot(
        evidence_ref_id=(
            "analysis:00000000-0000-0000-0000-000000000109:"
            f"finding-1:{ANNOTATION_ID}"
        ),
        claim="迁移后照护责任集中到姐姐。",
        excerpt=deleted_excerpt,
        locator="第4页，第12段",
        source=SourceRecordSnapshot(
            source_id=(
                f"research-material:{MATERIAL_ID}:{PARSE_ID}:segment-1"
            ),
            source_type="personal_research_material",
            title="家庭 A · 个人研究材料",
            authors_or_institution=(),
            year=None,
            publication=None,
            locator="第4页，第12段",
            url=None,
            verification_status=SourceVerificationStatus.VERIFIED,
            use_boundary="用户已确认的案例比较证据。",
        ),
        verification_status=SourceVerificationStatus.VERIFIED,
        use_boundary="用户已确认的案例比较证据。",
    )
    plan = SimpleNamespace(
        phenomenon=SimpleNamespace(
            phenomenon_query_id=UUID(int=301),
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
        evidence_bundle=SimpleNamespace(evidence_items=(personal_evidence,)),
        decisions=(),
        use_assignments=(),
        relations=(),
    )

    manifest = _export_manifest(
        document=filtered_document,
        plan=plan,
        match_run=SimpleNamespace(model=None, candidates=()),
        proposals=(),
        versions=(filtered_document,),
    )
    exported = manifest["evidence"][0]
    assert exported["excerpt"] is None
    assert exported["source_available"] is False
    assert exported["unavailable_reason"] == "source_deleted"
    assert exported["locator"] == "第4页，第12段"
    assert deleted_excerpt not in _export_markdown(
        base=ResearchDocumentMarkdownExport(
            document_id=filtered_document.document_id,
            task_id=filtered_document.task_id,
            theory_plan_id=filtered_document.theory_plan_id,
            knowledge_release_id=filtered_document.knowledge_release_id,
            version=filtered_document.version,
            filename="research-framework-v1.md",
            media_type="text/markdown",
            markdown="",
        ),
        manifest=manifest,
    )


@pytest.mark.parametrize("status", [AnalysisCodeStatus.CANDIDATE, AnalysisCodeStatus.REJECTED])
def test_document_rejects_unconfirmed_analysis_records(status: AnalysisCodeStatus) -> None:
    confirmed = _handoff()
    code = replace(
        confirmed.codes[0],
        status=status,
        version=1 if status is AnalysisCodeStatus.CANDIDATE else 2,
    )
    unsafe = replace(confirmed, codes=(code,))
    application, _, tasks = _application(lambda **_kwargs: unsafe)

    with pytest.raises(ValueError, match="confirmed analysis"):
        application.create(
            user_id=USER_ID,
            task=tasks.task,
            theory_plan_id=PLAN_ID,
            title="家庭照护研究",
            sections=_sections(),
            idempotency_key=f"reject-{status.value}",
        )
