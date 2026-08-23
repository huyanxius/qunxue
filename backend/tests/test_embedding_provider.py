import json

import pytest

import qunxue_api.adapters.research_agent.embedding as embedding
from qunxue_api.adapters.research_agent.embedding import (
    EmbeddingProviderError,
    OpenAICompatibleEmbeddingProvider,
)


def test_openai_compatible_embedding_provider_posts_documents_to_configured_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {"data": [{"embedding": [1.0, 0.0]}, {"embedding": [0.0, 1.0]}]}
            ).encode()

    def fake_urlopen(request, *, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data)
        return Response()

    monkeypatch.setattr(embedding, "urlopen", fake_urlopen)
    provider = OpenAICompatibleEmbeddingProvider(
        base_url="http://embedding.internal/v1",
        api_key="test-key",
        model="BAAI/bge-m3",
        timeout_seconds=2,
    )

    assert provider.embed_documents(["问题一", "问题二"]) == [[1.0, 0.0], [0.0, 1.0]]
    assert captured["url"] == "http://embedding.internal/v1/embeddings"
    assert captured["body"] == {"input": ["问题一", "问题二"], "model": "BAAI/bge-m3"}


@pytest.mark.parametrize(
    "payload",
    (
        b"{invalid-json",
        b'{"data":[{"embedding":[NaN,0.0]}]}',
    ),
)
def test_embedding_provider_rejects_unusable_provider_payloads(
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return payload

    monkeypatch.setattr(embedding, "urlopen", lambda *_args, **_kwargs: Response())
    provider = OpenAICompatibleEmbeddingProvider(
        base_url="http://embedding.internal/v1",
        api_key="test-key",
        model="BAAI/bge-m3",
        timeout_seconds=2,
    )

    with pytest.raises(EmbeddingProviderError):
        provider.embed_query("问题")
