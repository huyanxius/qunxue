import json

import pytest

import qunxue_api.adapters.research_agent.reranker as reranker
from qunxue_api.adapters.research_agent.reranker import (
    RerankerProviderError,
    SiliconFlowRerankerProvider,
)


def test_siliconflow_reranker_posts_candidates_and_preserves_provider_ranking(
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
                {
                    "results": [
                        {"index": 1, "relevance_score": 0.91},
                        {"index": 0, "relevance_score": 0.63},
                    ]
                }
            ).encode()

    def fake_urlopen(request, *, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data)
        return Response()

    monkeypatch.setattr(reranker, "urlopen", fake_urlopen)
    provider = SiliconFlowRerankerProvider(
        base_url="https://api.siliconflow.cn/v1",
        api_key="test-key",
        model="Pro/BAAI/bge-reranker-v2-m3",
        timeout_seconds=3,
    )

    ranked = provider.rerank(
        query="流动社区中的互助为何减弱？",
        documents=("互惠规范依赖重复互动。", "社会资本会随关系流动而变化。"),
        top_n=2,
    )

    assert [(item.index, item.score) for item in ranked] == [(1, 0.91), (0, 0.63)]
    assert captured["url"] == "https://api.siliconflow.cn/v1/rerank"
    assert captured["timeout"] == 3
    assert captured["body"] == {
        "model": "Pro/BAAI/bge-reranker-v2-m3",
        "query": "流动社区中的互助为何减弱？",
        "documents": ["互惠规范依赖重复互动。", "社会资本会随关系流动而变化。"],
        "top_n": 2,
        "return_documents": False,
    }
    assert captured["headers"]["Authorization"] == "Bearer test-key"


def test_siliconflow_reranker_rejects_non_finite_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"results":[{"index":0,"relevance_score":NaN}]}'

    monkeypatch.setattr(reranker, "urlopen", lambda *_args, **_kwargs: Response())
    provider = SiliconFlowRerankerProvider(
        base_url="https://api.siliconflow.cn/v1",
        api_key="test-key",
        model="Pro/BAAI/bge-reranker-v2-m3",
        timeout_seconds=3,
    )

    with pytest.raises(RerankerProviderError):
        provider.rerank(query="问题", documents=("候选",), top_n=1)
