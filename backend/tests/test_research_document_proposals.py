from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID

import pytest

import qunxue_api.modules.research_framework as framework

NOW = datetime(2026, 8, 20, 3, 0, tzinfo=UTC)


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


class MemoryProposals:
    def __init__(self) -> None:
        self.items: dict[UUID, object] = {}
        self.agent_context_valid = True

    def add(self, snapshot):
        self.items[snapshot.proposal_id] = snapshot
        return snapshot

    def get(self, proposal_id):
        return self.items.get(proposal_id)

    def save(self, snapshot):
        self.items[snapshot.proposal_id] = snapshot
        return snapshot

    def list_for_document(self, document_id):
        return tuple(
            item for item in self.items.values() if item.document_id == document_id
        )

    def list_for_task(self, task_id):
        return tuple(item for item in self.items.values() if item.task_id == task_id)

    def validate_agent_context(self, **_kwargs):
        return self.agent_context_valid

    def find_revision_for_agent_target(
        self,
        *,
        agent_run_id,
        document_id,
        base_document_version,
        target_section_id,
    ):
        return next(
            (
                item
                for item in self.items.values()
                if item.agent_run_id == agent_run_id
                and item.document_id == document_id
                and item.base_document_version == base_document_version
                and item.target_section_id == target_section_id
            ),
            None,
        )


class ConflictMemoryProposals(MemoryProposals):
    def save(self, snapshot):
        current = self.items[snapshot.proposal_id]
        return current


def section(content: str):
    return framework.ResearchDocumentSection(
        section_id="research_question",
        key="research_question",
        title="研究问题",
        content=content,
        status=framework.ResearchDocumentSectionStatus.REVIEWED,
        evidence_refs=(),
    )


def document_service(repository: MemoryDocuments):
    ids = iter(UUID(int=value) for value in range(10, 30))
    return framework.ResearchDocumentService(
        repository=repository,
        id_factory=lambda: next(ids),
        clock=lambda: NOW,
    )


def proposal_service(
    documents: framework.ResearchDocumentService,
    repository: MemoryProposals,
    atomic=None,
):
    service_type = framework.ResearchDocumentProposalService
    ids = iter(UUID(int=value) for value in range(100, 120))
    return service_type(
        repository=repository,
        documents=documents,
        id_factory=lambda: next(ids),
        clock=lambda: NOW,
        atomic=atomic,
    )


def test_accept_rolls_back_document_when_proposal_decision_loses_race() -> None:
    document_repository = MemoryDocuments()
    documents = document_service(document_repository)
    created = documents.create(
        task_id=UUID(int=1), theory_plan_id=UUID(int=2), knowledge_release_id="release-final-1",
        title="理论判断", sections=(section("原始研究问题"),),
    )
    proposal_repository = ConflictMemoryProposals()
    snapshots = document_repository.items

    @contextmanager
    def atomic():
        before = {key: list(value) for key, value in snapshots.items()}
        try:
            yield
        except Exception:
            snapshots.clear()
            snapshots.update({key: list(value) for key, value in before.items()})
            raise

    proposals = proposal_service(documents, proposal_repository, atomic=atomic)
    proposed = proposals.propose_revision(
        user_id=UUID(int=3), conversation_id=UUID(int=4), agent_run_id=UUID(int=5),
        document_id=created.document_id, expected_version=1,
        section=section("竞态建议"), rationale="局部改写",
    )
    with pytest.raises(ValueError, match="proposal decision conflict"):
        proposals.accept(
            proposal_id=proposed.proposal_id,
            user_id=UUID(int=3),
            expected_document_version=1,
        )
    assert documents.get(created.document_id).version == 1


def test_agent_revision_stays_pending_until_the_user_accepts_it() -> None:
    document_repository = MemoryDocuments()
    documents = document_service(document_repository)
    created = documents.create(
        task_id=UUID(int=1),
        theory_plan_id=UUID(int=2),
        knowledge_release_id="release-final-1",
        title="理论判断",
        sections=(section("原始研究问题"),),
    )
    proposal_repository = MemoryProposals()
    proposals = proposal_service(documents, proposal_repository)

    proposed = proposals.propose_revision(
        user_id=UUID(int=3),
        conversation_id=UUID(int=4),
        agent_run_id=UUID(int=5),
        document_id=created.document_id,
        expected_version=created.version,
        section=section("成员流动如何改变社区互助的持续性？"),
        rationale="把问题收窄到可观察机制",
    )

    assert proposed.status.value == "pending"
    assert documents.get(created.document_id).version == 1
    assert documents.get(created.document_id).sections[0].content == "原始研究问题"

    accepted = proposals.accept(
        proposal_id=proposed.proposal_id,
        user_id=UUID(int=3),
        expected_document_version=1,
    )

    assert accepted.proposal.status.value == "accepted"
    assert accepted.document.version == 2
    assert accepted.document.actor == "agent_suggestion_accepted"
    assert accepted.document.sections[0].content == "成员流动如何改变社区互助的持续性？"
    replayed = proposals.accept(
        proposal_id=proposed.proposal_id,
        user_id=UUID(int=3),
        expected_document_version=1,
    )
    assert replayed.document.revision_id == accepted.document.revision_id


def test_rejected_or_stale_agent_revision_never_changes_the_document() -> None:
    document_repository = MemoryDocuments()
    documents = document_service(document_repository)
    created = documents.create(
        task_id=UUID(int=1),
        theory_plan_id=UUID(int=2),
        knowledge_release_id="release-final-1",
        title="理论判断",
        sections=(section("原始研究问题"),),
    )
    proposal_repository = MemoryProposals()
    proposals = proposal_service(documents, proposal_repository)
    proposed = proposals.propose_revision(
        user_id=UUID(int=3),
        conversation_id=UUID(int=4),
        agent_run_id=UUID(int=5),
        document_id=created.document_id,
        expected_version=1,
        section=section("建议改写"),
        rationale="局部改写",
    )
    rejected = proposals.reject(
        proposal_id=proposed.proposal_id,
        user_id=UUID(int=3),
        reason="保留原文",
    )
    assert rejected.status.value == "rejected"
    assert documents.get(created.document_id).version == 1
    with pytest.raises(ValueError, match="rejected"):
        proposals.accept(
            proposal_id=proposed.proposal_id,
            user_id=UUID(int=3),
            expected_document_version=1,
        )

    another = proposals.propose_revision(
        user_id=UUID(int=3),
        conversation_id=UUID(int=4),
        agent_run_id=UUID(int=6),
        document_id=created.document_id,
        expected_version=1,
        section=section("另一个建议"),
        rationale="补充边界",
    )
    documents.revise(
        document_id=created.document_id,
        expected_version=1,
        sections=(section("用户已经自行修改"),),
        change_summary="用户编辑",
        actor="user",
    )
    with pytest.raises(ValueError, match="stale"):
        proposals.accept(
            proposal_id=another.proposal_id,
            user_id=UUID(int=3),
            expected_document_version=1,
        )


def test_agent_can_propose_a_complete_framework_without_creating_it() -> None:
    document_repository = MemoryDocuments()
    documents = document_service(document_repository)
    proposal_repository = MemoryProposals()
    proposals = proposal_service(documents, proposal_repository)
    proposed = proposals.propose_create(
        user_id=UUID(int=3),
        conversation_id=UUID(int=4),
        agent_run_id=UUID(int=5),
        task_id=UUID(int=1),
        theory_plan_id=UUID(int=2),
        knowledge_release_id="release-final-1",
        title="社区互助研究框架",
        sections=(section("Agent 提议的问题"),),
        rationale="依据已确认理论方案生成草稿",
    )
    assert proposed.status.value == "pending"
    assert document_repository.items == {}

    accepted = proposals.accept(
        proposal_id=proposed.proposal_id,
        user_id=UUID(int=3),
        expected_document_version=None,
    )
    assert accepted.document.version == 1
    assert accepted.document.actor == "agent_suggestion_accepted"
    assert accepted.document.knowledge_release_id == "release-final-1"


def test_agent_cannot_create_an_unactionable_proposal_for_a_confirmed_document() -> None:
    document_repository = MemoryDocuments()
    documents = document_service(document_repository)
    section_keys = (
        "research_question",
        "research_object_and_field",
        "theoretical_perspective",
        "core_concepts",
        "mechanisms",
        "questions_or_hypotheses",
        "methodology",
        "sample_and_sources",
        "analysis_steps",
        "ethics",
        "limitations",
        "evidence_gaps",
    )
    created = documents.create(
        task_id=UUID(int=1),
        theory_plan_id=UUID(int=2),
        knowledge_release_id="release-final-1",
        title="研究框架",
        sections=tuple(
            framework.ResearchDocumentSection(
                section_id=key,
                key=key,
                title=key,
                content=f"{key} 正文",
                status=framework.ResearchDocumentSectionStatus.REVIEWED,
                evidence_refs=(),
            )
            for key in section_keys
        ),
    )
    confirmed = documents.confirm(
        document_id=created.document_id,
        expected_version=created.version,
    )
    proposals = proposal_service(documents, MemoryProposals())

    with pytest.raises(ValueError, match="confirmed"):
        proposals.propose_revision(
            user_id=UUID(int=3),
            conversation_id=UUID(int=4),
            agent_run_id=UUID(int=5),
            document_id=confirmed.document_id,
            expected_version=confirmed.version,
            section=framework.ResearchDocumentSection(
                section_id="research_question",
                key="research_question",
                title="研究问题",
                content="不会形成僵尸建议",
                status=framework.ResearchDocumentSectionStatus.REVIEWED,
                evidence_refs=(),
            ),
            rationale="正式文档必须先显式恢复",
        )


def test_proposal_requires_real_agent_provenance_and_deduplicates_one_run_target() -> None:
    document_repository = MemoryDocuments()
    documents = document_service(document_repository)
    created = documents.create(
        task_id=UUID(int=1),
        theory_plan_id=UUID(int=2),
        knowledge_release_id="release-final-1",
        title="研究框架",
        sections=(section("原文"),),
    )
    repository = MemoryProposals()
    repository.agent_context_valid = False
    proposals = proposal_service(documents, repository)
    arguments = {
        "user_id": UUID(int=3),
        "conversation_id": UUID(int=4),
        "agent_run_id": UUID(int=5),
        "document_id": created.document_id,
        "expected_version": 1,
        "section": section("建议正文"),
        "rationale": "局部收窄",
    }
    with pytest.raises(ValueError, match="provenance"):
        proposals.propose_revision(**arguments)

    repository.agent_context_valid = True
    first = proposals.propose_revision(**arguments)
    replayed = proposals.propose_revision(**arguments)
    assert replayed.proposal_id == first.proposal_id
    with pytest.raises(ValueError, match="already proposed"):
        proposals.propose_revision(
            **{
                **arguments,
                "section": section("同一运行里的另一版建议"),
            }
        )
