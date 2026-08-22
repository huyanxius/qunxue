from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.research_document import (
    SqliteResearchDocumentRepository,
)
from qunxue_api.modules.research_framework import (
    ResearchDocumentSection,
    ResearchDocumentSectionStatus,
    ResearchDocumentSnapshot,
    ResearchDocumentStatus,
)


def _document() -> ResearchDocumentSnapshot:
    return ResearchDocumentSnapshot(
        document_id=UUID(int=1),
        task_id=UUID(int=2),
        theory_plan_id=UUID(int=3),
        knowledge_release_id="release-final-1",
        revision_id=UUID(int=4),
        version=1,
        title="社区互助研究框架",
        sections=(
            ResearchDocumentSection(
                section_id="research_question",
                key="research_question",
                title="研究问题",
                content="社区成员流动如何改变互助网络？",
                status=ResearchDocumentSectionStatus.DRAFT,
                evidence_refs=(),
            ),
        ),
        status=ResearchDocumentStatus.DRAFT,
        change_summary="创建研究框架",
        actor="user",
        created_at=datetime(2026, 8, 22, 8, 0, tzinfo=UTC),
    )


def _create_document_table(engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE research_document_versions (
                document_id VARCHAR(36) NOT NULL,
                version INTEGER NOT NULL,
                task_id VARCHAR(36) NOT NULL,
                theory_plan_id VARCHAR(36) NOT NULL,
                knowledge_release_id VARCHAR(128) NOT NULL,
                revision_id VARCHAR(36) NOT NULL UNIQUE,
                title VARCHAR(512) NOT NULL,
                sections JSON NOT NULL,
                status VARCHAR(32) NOT NULL,
                change_summary TEXT NOT NULL,
                actor VARCHAR(64) NOT NULL,
                restored_from_version INTEGER,
                created_at DATETIME NOT NULL,
                confirmed_at DATETIME,
                PRIMARY KEY (document_id, version)
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE research_document_identities (
                task_id VARCHAR(36) NOT NULL,
                theory_plan_id VARCHAR(36) NOT NULL,
                document_id VARCHAR(36) NOT NULL UNIQUE,
                PRIMARY KEY (task_id, theory_plan_id)
            )
            """
        )


def test_repository_replays_the_winning_document_after_a_unique_identity_conflict() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_document_table(engine)
    first = _document()
    concurrent_retry = replace(
        first,
        document_id=UUID(int=11),
        revision_id=UUID(int=12),
    )

    with Session(engine) as session:
        assert SqliteResearchDocumentRepository(session).add(first) == first
        session.commit()
    with Session(engine) as session:
        replayed = SqliteResearchDocumentRepository(session).add(concurrent_retry)
        session.commit()

    assert replayed == first
    engine.dispose()
