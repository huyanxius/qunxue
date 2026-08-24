import json
from collections.abc import Iterator
from pathlib import Path
from shutil import copyfile

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
    database_path = tmp_path / "test.db"
    database_url = f"sqlite:///{database_path}"
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
    app = create_app(
        settings=settings,
        database=database,
        require_email_verification=False,
    )

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        database.engine.dispose()
        # Each catalog fixture is large; release its private database after the
        # connections close instead of retaining gigabytes until pytest exits.
        for suffix in ("", "-shm", "-wal"):
            Path(f"{database_path}{suffix}").unlink(missing_ok=True)


@pytest.fixture(scope="session")
def knowledge_database_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build a representative catalog once; per-test copies keep mutations isolated."""

    template_root = tmp_path_factory.mktemp("knowledge-database")
    template_path = template_root / "template.db"
    database_url = f"sqlite:///{template_path}"
    alembic_config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)
        command.upgrade(alembic_config, "head")

    database = Database(database_url)
    sample_root = template_root / "knowledge"
    sample_dimension = sample_root / "本体论"
    sample_dimension.mkdir(parents=True)
    sample_source = KNOWLEDGE_ROOT / "本体论" / "01-02-1. 古典社会学奠基.md"
    (sample_dimension / sample_source.name).symlink_to(sample_source)
    catalog = SqliteKnowledgeCatalog(
        database,
        knowledge_root=sample_root,
    )
    preview = catalog.current_release(purpose=KnowledgeUsePurpose.BROWSE)
    bundle_payload = json.loads(
        (KNOWLEDGE_ROOT / "review-packets" / "first-match-theories.pre-reviewed.json")
        .read_text(encoding="utf-8")
    )
    bundle_payload["base_release_id"] = preview.knowledge_release_id
    bundle_path = template_root / "first-match-theories.pre-reviewed.json"
    bundle_path.write_text(
        json.dumps(bundle_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    catalog.install_pre_reviewed_bundle(bundle_path)
    database.engine.dispose()
    return template_path


@pytest.fixture
def client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    knowledge_database_template: Path,
) -> Iterator[TestClient]:
    database_path = tmp_path / "test.db"
    copyfile(knowledge_database_template, database_path)
    database_url = f"sqlite:///{database_path}"
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
    database = Database(settings.database_url)
    app = create_app(
        settings=settings,
        database=database,
        require_email_verification=False,
    )
    catalog = app.state.knowledge_catalog
    app.state.knowledge_retriever = _TestReleaseRetriever(catalog)

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        database.engine.dispose()
        for suffix in ("", "-shm", "-wal"):
            Path(f"{database_path}{suffix}").unlink(missing_ok=True)
