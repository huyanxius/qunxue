from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from qunxue_api.adapters.retrieval import RetrievalChunk
from qunxue_api.adapters.retrieval.hybrid import (
    HybridRetrievalHit,
    HybridRetrievalResult,
)
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.knowledge_catalog import SqliteKnowledgeCatalog
from qunxue_api.bootstrap import create_app
from qunxue_api.modules.knowledge_catalog import KnowledgeUsePurpose
from qunxue_api.settings import KNOWLEDGE_ROOT, Settings


class _TestReleaseRetriever:
    """Explicit test double; production bootstrap never selects this implementation."""

    def __init__(self, catalog: SqliteKnowledgeCatalog) -> None:
        self._catalog = catalog

    def search(self, **kwargs) -> HybridRetrievalResult:
        profiles = self._catalog.list_match_profiles(
            release_id=kwargs["knowledge_release_id"]
        )
        hits = tuple(
            HybridRetrievalHit(
                chunk=RetrievalChunk(
                    chunk_id=f"theory-profile:{profile.theory_id}:v{profile.content_version}",
                    document_kind="theory_profile",
                    knowledge_id=profile.related_knowledge_ids[0],
                    theory_id=profile.theory_id,
                    content_version=profile.content_version,
                    content_hash=f"test:{profile.theory_id}:v{profile.content_version}",
                    title=profile.title,
                    text="\n".join((profile.title, *profile.core_propositions)),
                    source_ids=profile.source_ids,
                ),
                fused_score=1.0,
                retrieval_sources=("test",),
                rerank_score=1.0,
            )
            for profile in profiles[: kwargs["limit"]]
            if kwargs["document_kind"] in {None, "theory_profile"}
        )
        return HybridRetrievalResult(
            retrieval_index_id="test-release-bound-index",
            mode="deterministic_test",
            embedding_model="test-embedding",
            reranker_model="test-reranker",
            degraded_reason=None,
            hits=hits,
        )


@pytest.fixture
def alembic_config() -> Config:
    return Config(str(Path(__file__).parents[1] / "alembic.ini"))


@pytest.fixture
def plain_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_config: Config,
) -> Iterator[TestClient]:
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        runtime_mode="mock",
        model_base_url=None,
        model_api_key=None,
        model_name=None,
        model_extra_headers={},
        model_sft_resource_id=None,
    )
    command.upgrade(alembic_config, "head")
    database = Database(settings.database_url)
    app = create_app(settings=settings, database=database)

    with TestClient(app) as test_client:
        yield test_client

    database.engine.dispose()


@pytest.fixture
def client(plain_client: TestClient) -> Iterator[TestClient]:
    catalog = plain_client.app.state.knowledge_catalog
    catalog.current_release(purpose=KnowledgeUsePurpose.BROWSE)
    catalog.install_pre_reviewed_bundle(
        KNOWLEDGE_ROOT / "review-packets" / "first-match-theories.pre-reviewed.json"
    )
    plain_client.app.state.knowledge_retriever = _TestReleaseRetriever(catalog)
    yield plain_client
