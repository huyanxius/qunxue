from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.research_document_proposal import (
    SqliteResearchDocumentProposalRepository,
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
                document_id VARCHAR(36),
                base_document_version INTEGER,
                target_section_id VARCHAR(128),
                decision_reason TEXT,
                result_document_id VARCHAR(36),
                result_document_version INTEGER,
                created_at DATETIME NOT NULL,
                decided_at DATETIME
            )
            """
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
