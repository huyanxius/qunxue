from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from qunxue_api.application.research_document_mutations import (
    ResearchDocumentMutationReceipt,
)
from qunxue_api.application.research_documents import ResearchDocumentApplication
from qunxue_api.modules.research_framework import (
    ResearchDocumentProposalKind,
    ResearchDocumentProposalSnapshot,
    ResearchDocumentProposalStatus,
    ResearchDocumentSection,
    ResearchDocumentSectionStatus,
    ResearchDocumentService,
)
from qunxue_api.modules.research_intake import EntryType, ResearchTask, ResearchTaskStatus


class MemoryDocuments:
    def __init__(self) -> None:
        self.items = {}

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
    def __init__(self, task) -> None:
        self.task = task

    def get(self, task_id, user_id):
        if self.task.task_id == task_id and self.task.user_id == user_id:
            return self.task
        return None

    def save_progress(self, snapshot):
        self.task = snapshot
        return snapshot


class UnusedMutations:
    def claim(self, *, user_id, idempotency_key, operation, request_hash):
        return ResearchDocumentMutationReceipt(
            request_id=UUID(int=99),
            user_id=user_id,
            idempotency_key=idempotency_key,
            operation=operation,
            request_hash=request_hash,
            status="pending",
        )

    def fail(self, *, request_id):
        return request_id

    def complete(self, **_kwargs):
        raise AssertionError("blocked completion must not finish its receipt")


def _sections() -> tuple[ResearchDocumentSection, ...]:
    values = (
        ("research_question", "研究问题"),
        ("research_object_and_field", "研究对象与场域"),
        ("theoretical_perspective", "理论视角"),
        ("core_concepts", "核心概念"),
        ("mechanisms", "作用机制"),
        ("questions_or_hypotheses", "研究假设"),
        ("methodology", "研究方法"),
        ("sample_and_sources", "样本与来源"),
        ("analysis_steps", "分析步骤"),
        ("ethics", "伦理"),
        ("limitations", "局限"),
        ("evidence_gaps", "证据缺口"),
    )
    critical = {
        "theoretical_perspective",
        "core_concepts",
        "mechanisms",
        "questions_or_hypotheses",
        "methodology",
        "analysis_steps",
    }
    return tuple(
        ResearchDocumentSection(
            section_id=key,
            key=key,
            title=title,
            content=f"{title}的正式说明。",
            status=(
                ResearchDocumentSectionStatus.EVIDENCE_GAP
                if key in critical
                else ResearchDocumentSectionStatus.REVIEWED
            ),
            evidence_refs=(),
        )
        for key, title in values
    )


def test_completion_gate_reports_when_the_delivery_package_cannot_be_built() -> None:
    user_id = UUID(int=1)
    task_id = UUID(int=2)
    plan_id = UUID(int=3)
    match_run_id = UUID(int=4)
    documents = ResearchDocumentService(repository=MemoryDocuments())
    document = documents.create(
        task_id=task_id,
        theory_plan_id=plan_id,
        knowledge_release_id="release-final-1",
        title="社区互助研究框架",
        sections=_sections(),
    )
    task = ResearchTask(
        task_id=task_id,
        user_id=user_id,
        entry_type=EntryType.DIRECT_INPUT,
        status=ResearchTaskStatus.FRAMEWORK_DRAFT,
        version=7,
        idempotency_key="task-1",
        created_at=datetime(2026, 8, 22, 8, 0, tzinfo=UTC),
        updated_at=datetime(2026, 8, 22, 8, 0, tzinfo=UTC),
        current_theory_plan_id=plan_id,
        current_framework_id=document.document_id,
    )
    application = ResearchDocumentApplication(
        documents=documents,
        research_tasks=Tasks(task),
        mutations=UnusedMutations(),
        get_theory_plan=lambda value: (
            SimpleNamespace(
                theory_plan_id=plan_id,
                task_id=task_id,
                match_run_id=match_run_id,
            )
            if value == plan_id
            else None
        ),
        get_match_run=lambda _value: None,
        list_proposals_for_task=lambda _value: (),
        list_actionable_proposals_for_task=lambda _value: (),
        owns_match_run=lambda **_kwargs: True,
    )

    gate = application.completion_gate(
        user_id=user_id,
        document_id=document.document_id,
    )

    delivery = next(check for check in gate.checks if check.code == "delivery_package")
    assert gate.ready is False
    assert delivery.passed is False
    assert "成果包" in gate.blockers[-1]

    with pytest.raises(ValueError, match="成果包"):
        application.confirm(
            user_id=user_id,
            document_id=document.document_id,
            expected_version=document.version,
            idempotency_key="confirm-without-package",
        )
    assert documents.get(document.document_id).status.value == "draft"


def test_export_audit_keeps_noncanonical_revision_proposals_for_same_plan() -> None:
    user_id = UUID(int=11)
    task_id = UUID(int=12)
    plan_id = UUID(int=13)
    documents = ResearchDocumentService(repository=MemoryDocuments())
    document = documents.create(
        task_id=task_id,
        theory_plan_id=plan_id,
        knowledge_release_id="release-final-1",
        title="社区互助研究框架",
        sections=_sections(),
    )
    historical = ResearchDocumentProposalSnapshot(
        proposal_id=UUID(int=14),
        kind=ResearchDocumentProposalKind.REVISE_SECTION,
        status=ResearchDocumentProposalStatus.PENDING,
        user_id=user_id,
        conversation_id=UUID(int=15),
        agent_run_id=UUID(int=16),
        task_id=task_id,
        theory_plan_id=plan_id,
        knowledge_release_id="release-final-1",
        title="历史非 canonical 修订",
        proposed_sections=(_sections()[0],),
        rationale="保留已发生的 Agent 审计记录。",
        created_at=datetime(2026, 8, 22, 9, 0, tzinfo=UTC),
        document_id=UUID(int=17),
        base_document_version=1,
        target_section_id="research_question",
        request_hash="sha256:historical",
    )
    other_plan = ResearchDocumentProposalSnapshot(
        proposal_id=UUID(int=18),
        kind=ResearchDocumentProposalKind.REVISE_SECTION,
        status=ResearchDocumentProposalStatus.PENDING,
        user_id=user_id,
        conversation_id=UUID(int=19),
        agent_run_id=UUID(int=20),
        task_id=task_id,
        theory_plan_id=UUID(int=21),
        knowledge_release_id="release-final-1",
        title="其他理论方案的修订",
        proposed_sections=(_sections()[0],),
        rationale="不应进入当前方案的导出。",
        created_at=datetime(2026, 8, 22, 9, 1, tzinfo=UTC),
        document_id=document.document_id,
        base_document_version=1,
        target_section_id="research_question",
        request_hash="sha256:other-plan",
    )
    application = ResearchDocumentApplication(
        documents=documents,
        research_tasks=Tasks(
            ResearchTask(
                task_id=task_id,
                user_id=user_id,
                entry_type=EntryType.DIRECT_INPUT,
                status=ResearchTaskStatus.FRAMEWORK_DRAFT,
                version=1,
                idempotency_key="task-audit",
                created_at=datetime(2026, 8, 22, 8, 0, tzinfo=UTC),
                updated_at=datetime(2026, 8, 22, 8, 0, tzinfo=UTC),
                current_theory_plan_id=plan_id,
                current_framework_id=document.document_id,
            )
        ),
        mutations=UnusedMutations(),
        get_theory_plan=lambda _value: None,
        get_match_run=lambda _value: None,
        list_proposals_for_task=lambda _value: (historical, other_plan),
        list_actionable_proposals_for_task=lambda _value: (),
        owns_match_run=lambda **_kwargs: True,
    )

    audit_proposals = application._document_proposals(document)

    assert tuple(item.proposal_id for item in audit_proposals) == (
        historical.proposal_id,
    )
    assert application._pending_proposal_count(document) == 0
