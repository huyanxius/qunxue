"""HTTP adapter for SiliconFlow's release-independent rerank endpoint."""

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class RerankerProviderError(RuntimeError):
    """The configured reranker failed or returned an invalid ranking."""


@dataclass(frozen=True, slots=True)
class RerankScore:
    index: int
    score: float


class SiliconFlowRerankerProvider:
    """Rerank a closed candidate list through SiliconFlow's ``/rerank`` API."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout_seconds: float,
    ) -> None:
        self._endpoint = _rerank_endpoint(base_url)
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds

    def rerank(
        self,
        *,
        query: str,
        documents: Sequence[str],
        top_n: int,
    ) -> tuple[RerankScore, ...]:
        values = tuple(documents)
        if not values:
            return ()
        safe_top_n = max(1, min(top_n, len(values)))
        body = json.dumps(
            {
                "model": self._model,
                "query": query,
                "documents": list(values),
                "top_n": safe_top_n,
                "return_documents": False,
            },
            ensure_ascii=False,
        ).encode()
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = Request(self._endpoint, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read())
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise RerankerProviderError("reranker service request failed") from error
        return _parse_rerank_scores(
            payload,
            document_count=len(values),
            expected_count=safe_top_n,
        )


def _rerank_endpoint(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    return normalized if normalized.endswith("/rerank") else f"{normalized}/rerank"


def _parse_rerank_scores(
    payload: object,
    *,
    document_count: int,
    expected_count: int,
) -> tuple[RerankScore, ...]:
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise RerankerProviderError("reranker response is missing results")
    scores: list[RerankScore] = []
    seen_indexes: set[int] = set()
    for item in payload["results"]:
        if not isinstance(item, dict):
            raise RerankerProviderError("reranker response contains an invalid result")
        index = item.get("index")
        score = item.get("relevance_score")
        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or not 0 <= index < document_count
            or index in seen_indexes
            or not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not math.isfinite(float(score))
        ):
            raise RerankerProviderError("reranker response contains an invalid score")
        seen_indexes.add(index)
        scores.append(RerankScore(index=index, score=float(score)))
    if len(scores) != expected_count:
        raise RerankerProviderError("reranker response count does not match request")
    return tuple(scores)
