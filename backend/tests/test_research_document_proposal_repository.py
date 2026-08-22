from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.research_document_proposal import (
    SqliteResearchDocumentProposalRepository,
)
from qunxue_api.adapters.sqlite.research_document_proposal_model import (
    ResearchDocumentProposalRow,
)
from qunxue_api.modules.research_framework import (
    ResearchDocumentProposalKind,
    ResearchDocumentProposalSnapshot,
    ResearchDocumentProposalStatus,
    ResearchDocumentSection,
    ResearchDocumentSectionStatus,
)


def _pending_proposal() -> ResearchDocumentProposalSnapshot:
    return ResearchDocumentProposalSnapshot(
        proposal_id=UUID(int=1),
        kind=ResearchDocumentProposalKind.REVISE_SECTION,
        status=ResearchDocumentProposalStatus.PENDING,
        user_id=UUID(int=2),
        conversation_id=UUID(int=3),
        agent_run_id=UUID(int=4),
        task_id=UUID(int=5),
        theory_plan_id=UUID(int=6),
        knowledge_release_id="release-final-1",
        title="研究框架",
        proposed_sections=(
            ResearchDocumentSection(
                section_id="research_question",
                key="research_question",
                title="研究问题",
                content="建议修改后的研究问题",
                status=ResearchDocumentSectionStatus.REVIEWED,
                evidence_refs=(),
            ),
        ),
        rationale="局部收窄研究问题",
        created_at=datetime(2026, 8, 20, 4, 0, tzinfo=UTC),
        document_id=UUID(int=7),
        base_document_version=1,
        target_section_id="research_question",
        request_hash="sha256:proposal",
    )


def _create_proposal_table(engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE research_document_proposals (
                proposal_id VARCHAR(36) PRIMARY KEY,
                kind VARCHAR(32) NOT NULL,
                status VARCHAR(32) NOT NULL,
                user_id VARCHAR(36) NOT NULL,
                conversation_id VARCHAR(36) NOT NULL,
                agent_run_id VARCHAR(36) NOT NULL,
                task_id VARCHAR(36) NOT NULL,
                theory_plan_id VARCHAR(36) NOT NULL,
                knowledge_release_id VARCHAR(128) NOT NULL,
                title VARCHAR(512) NOT NULL,
                proposed_sections JSON NOT NULL,
                rationale TEXT NOT NULL,
                request_hash VARCHAR(72) NOT NULL,
                model_provider VARCHAR(64),
                model_name VARCHAR(128),
                document_id VARCHAR(36),
                base_document_version INTEGER,
                target_section_id VARCHAR(128),
                decision_reason TEXT,
                result_document_id VARCHAR(36),
                result_document_version INTEGER,
                created_at DATETIME NOT NULL,
                decided_at DATETIME,
                UNIQUE (
                    agent_run_id, document_id,
                    base_document_version, target_section_id
                )
            )
            """
        )


def _create_handoff_table(engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE research_document_handoffs (
                user_id VARCHAR(36) NOT NULL,
                task_id VARCHAR(36) NOT NULL,
                theory_plan_id VARCHAR(36) NOT NULL,
                proposal_id VARCHAR(36) NOT NULL UNIQUE,
                PRIMARY KEY (user_id, task_id, theory_plan_id)
            )
            """
        )


def _create_task_pointer_table(engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE research_tasks (
                task_id VARCHAR(36) PRIMARY KEY,
                current_framework_id VARCHAR(36)
            )
            """
        )


def _proposal_row(snapshot: ResearchDocumentProposalSnapshot) -> ResearchDocumentProposalRow:
    return ResearchDocumentProposalRow(
        proposal_id=str(snapshot.proposal_id),
        kind=snapshot.kind.value,
        status=snapshot.status.value,
        user_id=str(snapshot.user_id),
        conversation_id=str(snapshot.conversation_id),
        agent_run_id=str(snapshot.agent_run_id),
        task_id=str(snapshot.task_id),
        theory_plan_id=str(snapshot.theory_plan_id),
        knowledge_release_id=snapshot.knowledge_release_id,
        title=snapshot.title,
        proposed_sections=[
            {
                "section_id": section.section_id,
                "key": section.key,
                "title": section.title,
                "content": section.content,
                "status": section.status.value,
                "evidence_refs": [],
            }
            for section in snapshot.proposed_sections
        ],
        rationale=snapshot.rationale,
        request_hash=snapshot.request_hash,
        model_provider=snapshot.model_provider,
        model_name=snapshot.model_name,
        document_id=str(snapshot.document_id) if snapshot.document_id else None,
        base_document_version=snapshot.base_document_version,
        target_section_id=snapshot.target_section_id,
        decision_reason=snapshot.decision_reason,
        result_document_id=(
            str(snapshot.result_document_id) if snapshot.result_document_id else None
        ),
        result_document_version=snapshot.result_document_version,
        created_at=snapshot.created_at,
        decided_at=snapshot.decided_at,
    )


def test_repository_keeps_the_first_proposal_decision_when_a_stale_decision_arrives() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_proposal_table(engine)
    pending = _pending_proposal()
    accepted = replace(
        pending,
        status=ResearchDocumentProposalStatus.ACCEPTED,
        decision_reason="用户接受 Agent 建议",
        decided_at=datetime(2026, 8, 20, 4, 1, tzinfo=UTC),
        result_document_id=pending.document_id,
        result_document_version=2,
    )
    stale_rejection = replace(
        pending,
        status=ResearchDocumentProposalStatus.REJECTED,
        decision_reason="稍后到达的拒绝",
        decided_at=datetime(2026, 8, 20, 4, 2, tzinfo=UTC),
    )

    with Session(engine) as session:
        SqliteResearchDocumentProposalRepository(session).add(pending)
        session.commit()
    with Session(engine) as session:
        assert SqliteResearchDocumentProposalRepository(session).save(accepted) == accepted
        session.commit()
    with Session(engine) as session:
        persisted = SqliteResearchDocumentProposalRepository(session).save(stale_rejection)
        session.commit()

    assert persisted == accepted
    with Session(engine) as session:
        assert (
            SqliteResearchDocumentProposalRepository(session).get(pending.proposal_id)
            == accepted
        )
    engine.dispose()


def test_repository_replays_the_winning_create_handoff_after_a_unique_conflict() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_proposal_table(engine)
    _create_handoff_table(engine)
    first = replace(
        _pending_proposal(),
        proposal_id=UUID(int=11),
        kind=ResearchDocumentProposalKind.CREATE,
        document_id=None,
        base_document_version=None,
        target_section_id=None,
        request_hash="sha256:same-create",
    )
    concurrent_retry = replace(
        first,
        proposal_id=UUID(int=12),
        conversation_id=UUID(int=13),
        agent_run_id=UUID(int=14),
    )

    with Session(engine) as session:
        assert SqliteResearchDocumentProposalRepository(session).add(first) == first
        session.commit()
    with Session(engine) as session:
        replayed = SqliteResearchDocumentProposalRepository(session).add(concurrent_retry)
        session.commit()

    assert replayed == first
    engine.dispose()


def test_accepted_create_keeps_the_handoff_and_rejected_create_releases_it() -> None:
    first = replace(
        _pending_proposal(),
        proposal_id=UUID(int=21),
        kind=ResearchDocumentProposalKind.CREATE,
        document_id=None,
        base_document_version=None,
        target_section_id=None,
        request_hash="sha256:first-create",
    )
    another = replace(
        first,
        proposal_id=UUID(int=23),
        conversation_id=UUID(int=24),
        agent_run_id=UUID(int=25),
        request_hash="sha256:another-create",
    )

    accepted_engine = create_engine("sqlite:///:memory:")
    _create_proposal_table(accepted_engine)
    _create_handoff_table(accepted_engine)
    accepted = replace(
        first,
        status=ResearchDocumentProposalStatus.ACCEPTED,
        decision_reason="用户接受 Agent 建议",
        decided_at=datetime(2026, 8, 20, 4, 1, tzinfo=UTC),
        result_document_id=UUID(int=22),
        result_document_version=1,
    )
    with Session(accepted_engine) as session:
        repository = SqliteResearchDocumentProposalRepository(session)
        repository.add(first)
        assert repository.save(accepted) == accepted
        assert repository.add(another) == accepted
        session.commit()

    rejected_engine = create_engine("sqlite:///:memory:")
    _create_proposal_table(rejected_engine)
    _create_handoff_table(rejected_engine)
    rejected = replace(
        first,
        status=ResearchDocumentProposalStatus.REJECTED,
        decision_reason="用户拒绝",
        decided_at=datetime(2026, 8, 20, 4, 2, tzinfo=UTC),
    )
    with Session(rejected_engine) as session:
        repository = SqliteResearchDocumentProposalRepository(session)
        repository.add(first)
        assert repository.save(rejected) == rejected
        assert repository.add(another) == another
        session.commit()

    accepted_engine.dispose()
    rejected_engine.dispose()


def test_actionable_projection_ignores_orphan_create_and_stale_document_revision() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_proposal_table(engine)
    _create_handoff_table(engine)
    _create_task_pointer_table(engine)
    base = _pending_proposal()
    canonical_create = replace(
        base,
        proposal_id=UUID(int=31),
        kind=ResearchDocumentProposalKind.CREATE,
        document_id=None,
        base_document_version=None,
        target_section_id=None,
    )
    orphan_create = replace(
        canonical_create,
        proposal_id=UUID(int=32),
        conversation_id=UUID(int=32),
        agent_run_id=UUID(int=32),
    )
    current_revision = replace(base, proposal_id=UUID(int=33), agent_run_id=UUID(int=33))
    stale_revision = replace(
        base,
        proposal_id=UUID(int=34),
        agent_run_id=UUID(int=34),
        document_id=UUID(int=8),
    )

    with Session(engine) as session:
        session.connection().exec_driver_sql(
            "INSERT INTO research_tasks (task_id, current_framework_id) VALUES (?, ?)",
            (str(base.task_id), str(base.document_id)),
        )
        session.connection().exec_driver_sql(
            """
            INSERT INTO research_document_handoffs (
                user_id, task_id, theory_plan_id, proposal_id
            ) VALUES (?, ?, ?, ?)
            """,
            (
                str(base.user_id),
                str(base.task_id),
                str(base.theory_plan_id),
                str(canonical_create.proposal_id),
            ),
        )
        session.add_all(
            [
                _proposal_row(canonical_create),
                _proposal_row(orphan_create),
                _proposal_row(current_revision),
                _proposal_row(stale_revision),
            ]
        )
        session.commit()

    with Session(engine) as session:
        repository = SqliteResearchDocumentProposalRepository(session)
        actionable = repository.list_actionable_for_task(base.task_id)
        audit = repository.list_for_task(base.task_id)

    assert {item.proposal_id for item in actionable} == {
        canonical_create.proposal_id,
        current_revision.proposal_id,
    }
    assert {item.proposal_id for item in audit} == {
        canonical_create.proposal_id,
        orphan_create.proposal_id,
        current_revision.proposal_id,
        stale_revision.proposal_id,
    }
    engine.dispose()
