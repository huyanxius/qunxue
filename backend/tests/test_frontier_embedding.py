# ruff: noqa: F811
from copy import deepcopy

import httpx
import pytest
from sqlalchemy import select
from test_frontier_store import SEED, seeded, store  # noqa: F401

from qunxue_api.adapters.frontier_embedding import (
    FrontierEmbeddingConfig,
    FrontierEmbeddingProvider,
    FrontierEmbeddingUnavailable,
    FrontierVectorIndex,
)
from qunxue_api.adapters.sqlite.frontier_models import FrontierRecordRow, FrontierVectorRow


class FakeEmbedding:
    status = "ready"
    model = "offline-test-model"

    def __init__(self):
        self.calls = []

    def embed(self, texts):
        self.calls.append(texts)
        return [[1.0, float(len(text) % 10 + 1)] for text in texts]


def test_default_missing_config_never_calls_network():
    called = []
    provider = FrontierEmbeddingProvider(
        FrontierEmbeddingConfig(),
        transport=httpx.MockTransport(lambda request: called.append(request)),
    )
    with pytest.raises(FrontierEmbeddingUnavailable, match="NotConfigured"):
        provider.embed(["test"])
    assert called == []


def test_configured_provider_still_requires_explicit_network_flag():
    provider = FrontierEmbeddingProvider(
        FrontierEmbeddingConfig("https://example.com/v1", "only-frontier-key", "test")
    )
    with pytest.raises(FrontierEmbeddingUnavailable, match="NetworkDisabled"):
        provider.embed(["test"])


def test_mock_embeddings_validate_and_sort_indices():
    def response(request):
        assert request.headers["authorization"] == "Bearer frontier-only"
        return httpx.Response(
            200,
            json={"data": [{"index": 1, "embedding": [0, 2]}, {"index": 0, "embedding": [3, 0]}]},
        )

    provider = FrontierEmbeddingProvider(
        FrontierEmbeddingConfig("https://example.com/v1", "frontier-only", "test", True),
        httpx.MockTransport(response),
    )
    assert provider.embed(["a", "b"]) == [[1, 0], [0, 1]]


def test_incremental_embedding_cache_zero_repeat_calls(seeded):
    provider = FakeEmbedding()
    index = FrontierVectorIndex(seeded, provider)
    record = seeded.list_records()[0]
    assert index.index_record(record["id"]) == 1
    assert index.index_record(record["id"]) == 0
    assert len(provider.calls) == 1
    changed = deepcopy(SEED)
    changed["records"] = [changed["records"][0]]
    # Unchanged text plus updated non-text metadata reuses cache across record versions.
    changed["records"][0]["editorial_caveat"] += " 更新来源说明"
    seeded.import_seed(changed)
    assert index.index_record(record["id"] + "@v2") == 0
    assert len(provider.calls) == 1
    changed["records"][0]["summary"] += " 修改内容"
    seeded.import_seed(changed)
    assert index.index_record(record["id"] + "@v3") == 1
    assert len(provider.calls) == 2


def test_practice_evidence_chunks_and_retraction_filter(seeded):
    provider = FakeEmbedding()
    index = FrontierVectorIndex(seeded, provider)
    record = next(r for r in seeded.list_records() if r["verification_status"] == "practice_signal")
    assert index.index_record(record["id"]) == 2
    assert index.search("社区")
    with seeded.database.session() as session:
        row = session.get(FrontierRecordRow, record["id"])
        row.structured_json = {
            **row.structured_json,
            "eligibility": {
                "browse": False,
                "rag": False,
                "match": False,
                "training_candidate": False,
            },
        }
    assert index.search("社区") == []
    assert index.index_record(record["id"]) == 0
    with seeded.database.session() as session:
        assert list(session.scalars(select(FrontierVectorRow))) == []


def test_no_config_keeps_lexical_index_only(seeded):
    index = FrontierVectorIndex(seeded, FrontierEmbeddingProvider(FrontierEmbeddingConfig()))
    assert index.index_record(seeded.list_records()[0]["id"]) == 0
    assert index.search("研究") == []


def test_public_search_never_embeds_even_when_private_agent_is_configured(seeded, monkeypatch):
    from fastapi.testclient import TestClient

    from qunxue_api.bootstrap import create_app
    from qunxue_api.settings import Settings

    def never_embed(*args, **kwargs):
        raise AssertionError("public search must not spend model credit")

    monkeypatch.setattr(FrontierEmbeddingProvider, "embed", never_embed)
    settings = Settings(
        _env_file=None,
        database_url=str(seeded.database.engine.url),
        memory_learning_enabled=False,
        frontier_embedding_base_url="https://example.com/v1",
        frontier_embedding_api_key="frontier-only-test-key",
        frontier_embedding_model="test",
        frontier_allow_model_network=True,
    )
    app = create_app(settings=settings, database=seeded.database)
    response = TestClient(app).get("/api/frontier/search?q=医院")
    assert response.status_code == 200
    assert response.json()["search_mode"] == "lexical"
