from qunxue_api.settings import Settings


def test_retrieval_models_have_independent_provider_settings() -> None:
    settings = Settings(
        _env_file=None,
        model_name="spark-disciplinary",
        embedding_base_url="http://embedding.internal/v1",
        embedding_model="BAAI/bge-m3",
        reranker_base_url="http://reranker.internal",
        reranker_model="BAAI/bge-reranker-v2-m3",
        vector_store_url="http://qdrant.internal:6333",
    )

    assert settings.model_name == "spark-disciplinary"
    assert settings.embedding_model == "BAAI/bge-m3"
    assert settings.reranker_model == "BAAI/bge-reranker-v2-m3"
    assert settings.vector_store_url.endswith(":6333")
