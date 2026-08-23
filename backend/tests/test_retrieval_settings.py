from pathlib import Path

import pytest

from qunxue_api.settings import Settings


def test_retrieval_models_have_independent_provider_settings_without_remote_vector_store() -> None:
    settings = Settings(
        _env_file=None,
        model_name="spark-disciplinary",
        embedding_base_url="http://embedding.internal/v1",
        embedding_model="BAAI/bge-m3",
        reranker_base_url="http://reranker.internal",
        reranker_model="BAAI/bge-reranker-v2-m3",
    )

    assert settings.model_name == "spark-disciplinary"
    assert settings.embedding_model == "BAAI/bge-m3"
    assert settings.reranker_model == "BAAI/bge-reranker-v2-m3"
    assert not hasattr(settings, "vector_store_url")


def test_retrieval_config_resolves_the_local_index_and_keeps_pipeline_parameters() -> None:
    settings = Settings(
        _env_file=None,
        retrieval_index_path="var/competition-retrieval.db",
        retrieval_embedding_batch_size=12,
        retrieval_min_rerank_score=0.42,
        retrieval_min_lexical_score=0.18,
        retrieval_recall_limit=24,
        embedding_base_url="https://api.siliconflow.cn/v1",
        embedding_api_key="embedding-test-key",
        embedding_model="Pro/BAAI/bge-m3",
        embedding_timeout_seconds=11,
        reranker_base_url="https://api.siliconflow.cn/v1",
        reranker_api_key="reranker-test-key",
        reranker_model="Pro/BAAI/bge-reranker-v2-m3",
        reranker_timeout_seconds=13,
    )

    config = settings.require_retrieval_config()

    assert config.index_path == Path(__file__).parents[1] / "var/competition-retrieval.db"
    assert config.embedding_model == "Pro/BAAI/bge-m3"
    assert config.embedding_api_key.get_secret_value() == "embedding-test-key"
    assert config.embedding_batch_size == 12
    assert config.reranker_model == "Pro/BAAI/bge-reranker-v2-m3"
    assert config.reranker_api_key.get_secret_value() == "reranker-test-key"
    assert config.min_rerank_score == 0.42
    assert config.min_lexical_score == 0.18
    assert config.recall_limit == 24


def test_retrieval_config_reports_every_missing_provider_value() -> None:
    settings = Settings(
        _env_file=None,
        embedding_base_url=" ",
        embedding_api_key="",
        embedding_model=None,
        reranker_base_url=None,
        reranker_api_key=" ",
        reranker_model="",
    )

    with pytest.raises(ValueError) as error:
        settings.require_retrieval_config()

    for field_name in (
        "embedding_base_url",
        "embedding_api_key",
        "embedding_model",
        "reranker_base_url",
        "reranker_api_key",
        "reranker_model",
    ):
        assert field_name in str(error.value)


@pytest.mark.parametrize(
    ("override", "invalid_field"),
    (
        ({"embedding_model": "BAAI/bge-small-zh-v1.5"}, "embedding_model"),
        ({"reranker_model": "BAAI/bge-reranker-base"}, "reranker_model"),
    ),
)
def test_retrieval_config_rejects_models_outside_the_frozen_siliconflow_pair(
    override: dict[str, str],
    invalid_field: str,
) -> None:
    values = {
        "embedding_base_url": "https://api.siliconflow.cn/v1",
        "embedding_api_key": "embedding-test-key",
        "embedding_model": "Pro/BAAI/bge-m3",
        "reranker_base_url": "https://api.siliconflow.cn/v1",
        "reranker_api_key": "reranker-test-key",
        "reranker_model": "Pro/BAAI/bge-reranker-v2-m3",
        **override,
    }

    with pytest.raises(ValueError, match=invalid_field):
        Settings(_env_file=None, **values).require_retrieval_config()
