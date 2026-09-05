from types import SimpleNamespace
from uuid import UUID

import pytest
from alembic import command
from sqlalchemy import text

from qunxue_api.adapters.research_agent.catalog_tools import KnowledgeToolRegistry
from qunxue_api.adapters.retrieval import PublishedReleaseCorpusCollector
from qunxue_api.adapters.retrieval.errors import RetrievalPipelineUnavailable
from qunxue_api.adapters.sqlite.knowledge_catalog import SqliteKnowledgeCatalog
from qunxue_api.modules.agent_conversation import AgentRunResult
from qunxue_api.modules.knowledge_catalog import KnowledgeReviewStatus, KnowledgeUsePurpose
from qunxue_api.settings import KNOWLEDGE_ROOT


@pytest.fixture
def imported_catalog(plain_client, tmp_path):
    root = tmp_path / "knowledge"
    dimension = root / "本体论"
    dimension.mkdir(parents=True)
    source = KNOWLEDGE_ROOT / "本体论/01-02-1. 古典社会学奠基.md"
    (dimension / source.name).symlink_to(source)
    return SqliteKnowledgeCatalog(plain_client.app.state.database, knowledge_root=root)


def test_uploaded_library_is_reviewed_and_searchable_without_theory_bundle(imported_catalog):
    release = imported_catalog.current_release(purpose=KnowledgeUsePurpose.BROWSE)
    entry = imported_catalog.get_entry(
        release_id=release.knowledge_release_id, knowledge_id="D1:C001"
    )
    assert entry.summary.review_status == KnowledgeReviewStatus.REVIEWED
    assert entry.summary.eligibility.rag_eligible
    assert entry.sources[0].verification_status == "verified"
    assert entry.sources[0].locator
    assert imported_catalog.list_rag_entries(release_id=release.knowledge_release_id)
    registry = KnowledgeToolRegistry(imported_catalog)
    assert registry.release == release
    hits = registry.search_knowledge("历史唯物主义")
    assert hits
    assert hits[0]["knowledge_id"] == "D1:C001"
    assert registry.read_knowledge_entry(hits[0]["knowledge_id"])["content"]
    assert registry.read_sources([entry.sources[0].source_id])
    corpus = PublishedReleaseCorpusCollector(catalog=imported_catalog).collect(
        release_id=release.knowledge_release_id,
    )
    assert corpus.knowledge_entry_count > 3
    assert corpus.chunks


def test_missing_vector_index_uses_uploaded_text_without_blocking_agent(imported_catalog):
    def unavailable(**kwargs):
        raise RetrievalPipelineUnavailable("retrieval index is unavailable")

    retriever = SimpleNamespace(require_ready_manifest=unavailable)
    registry = KnowledgeToolRegistry(imported_catalog, retriever=retriever)
    assert registry.search_knowledge("历史唯物主义")[0]["retrieval_mode"] == "catalog_lexical"


def test_upgrade_corrects_existing_imports_without_changing_content(
    imported_catalog,
    plain_client,
    alembic_config,
):
    release = imported_catalog.current_release(purpose=KnowledgeUsePurpose.BROWSE)
    database = plain_client.app.state.database
    before = imported_catalog.get_entry(
        release_id=release.knowledge_release_id, knowledge_id="D1:C001"
    )
    with database.session() as session:
        session.execute(
            text("UPDATE knowledge_entry_revisions SET review_status='pending', rag_eligible=0")
        )
        session.execute(
            text(
                "UPDATE knowledge_sources SET verification_status='pending' "
                "WHERE source_type='repository_markdown'"
            )
        )
    command.stamp(alembic_config, "20260905_0340")
    command.upgrade(alembic_config, "head")
    after = imported_catalog.get_entry(
        release_id=release.knowledge_release_id, knowledge_id="D1:C001"
    )
    assert after.summary.review_status == KnowledgeReviewStatus.REVIEWED
    assert after.summary.eligibility.rag_eligible
    assert after.sources[0].verification_status == "verified"
    assert after.content == before.content
    assert after.summary.content_version == before.summary.content_version
    assert after.release == before.release


def test_title_does_not_lock_the_following_model_telemetry(plain_client):
    response = plain_client.post(
        "/api/session/register",
        json={"email": "title-lock@example.com", "password": "password-123"},
        headers={"Idempotency-Key": "register-title-lock"},
    )
    user_id = UUID(response.json()["user"]["user_id"])
    database = plain_client.app.state.database

    class Runner:
        def prepare_research(self, *, on_title=None, **kwargs):
            on_title("日常问候")

        def run(self, *, tools, **kwargs):
            # Model route telemetry acquires its own SQLite writer during the answer.
            with database.session() as session:
                session.execute(text("UPDATE users SET display_name = display_name WHERE 1 = 0"))
            return AgentRunResult(
                answer="你好", citations=(), release_id=tools.release.knowledge_release_id,
                provider="test", model="test",
            )

    with plain_client.app.state.disciplinary_agent_scope() as application:
        application._runner = Runner()
        result = application.run_turn(
            user_id=user_id, conversation_id=None, prompt="你好",
            idempotency_key="title-model-telemetry",
        )
    assert result.conversation.title == "日常问候"
    assert result.result.answer == "你好"


def test_upload_and_legacy_defaults_allow_agent_read_and_citation(
    imported_catalog, plain_client, alembic_config,
):
    from uuid import uuid4

    from qunxue_api.adapters.research_agent.document_tools import ResearchDocumentToolRegistry
    from qunxue_api.adapters.sqlite.research_material_repository import (
        SqliteResearchMaterialRepository,
    )

    client = plain_client
    user = client.post(
        "/api/session/register", headers={"Idempotency-Key": str(uuid4())},
        json={"email": "material-reader@example.com", "password": "password-123"},
    ).json()["user"]
    task = client.post(
        "/api/research-tasks", headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "direct_input"},
    ).json()
    task_id = task["task_id"]
    uploaded = client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "interview_transcript"},
        files={"file": ("访谈.txt", "迁移之后的照护变化。".encode(), "text/plain")},
    )
    assert uploaded.status_code == 201
    material_id = uploaded.json()["material_id"]
    detail = client.get(f"/api/research-tasks/{task_id}/materials/{material_id}").json()
    segment_id = detail["segments"][0]["segment_id"]
    database = client.app.state.database

    def read():
        with database.session() as session:
            registry = ResearchDocumentToolRegistry(
                catalog=imported_catalog, documents=SimpleNamespace(), proposals=SimpleNamespace(),
                materials=SqliteResearchMaterialRepository(session),
            )
            registry.bind_agent_context(
                user_id=UUID(user["user_id"]), task_id=UUID(task_id),
                conversation_id=uuid4(), agent_run_id=uuid4(),
            )
            registry.enable_research_material_tools()
            result = registry.read_research_material_context(material_id, segment_id)
            assert result["context"][0]["text"] == "迁移之后的照护变化。"
            assert registry.evidence[result["citation_id"]].material_id == material_id

    read()
    with database.session() as session:
        session.execute(text(
            "UPDATE research_material_archive_profiles SET model_processing_scope='not_assessed', "
            "deidentification_status='pending'"
        ))
    command.stamp(alembic_config, "20260905_0340")
    command.upgrade(alembic_config, "head")
    read()
    with database.session() as session:
        session.execute(text(
            "UPDATE research_material_archive_profiles SET model_processing_scope='manual_only'"
        ))
    command.stamp(alembic_config, "20260905_0340")
    command.upgrade(alembic_config, "head")
    with database.session() as session:
        assert session.execute(text(
            "SELECT model_processing_scope FROM research_material_archive_profiles"
        )).scalar_one() == "manual_only"
