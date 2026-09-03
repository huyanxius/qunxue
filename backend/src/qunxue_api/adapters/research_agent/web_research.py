import json
import re
from collections.abc import Callable, Iterable, Mapping
from functools import partial
from hashlib import sha256
from html import unescape
from ipaddress import ip_address
from typing import Literal, Protocol
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from qunxue_api.adapters.retrieval.errors import RetrievalPipelineUnavailable
from qunxue_api.adapters.retrieval.sqlite_index import RetrievalChunk


class WebCandidateReranker(Protocol):
    """The existing knowledge retriever's transient-chunk ranking seam."""

    def search_chunks(
        self,
        *,
        query: str,
        chunks: tuple[RetrievalChunk, ...],
        limit: int,
    ) -> object: ...


SearchFunction = Callable[[str, int], Iterable[Mapping[str, object]]]
FetchFunction = Callable[[str], str | None]
ExtractFunction = Callable[[str], str | None]
SearchTransport = Callable[[str, float], Mapping[str, object]]
SearchProfile = Literal["generic", "sociology"]

_USER_AGENT = "QunxueResearchAgent/2.0"
_TRACKING_PREFIXES = ("utm_", "gclid", "fbclid", "msclkid")
_OFFICIAL_SUFFIXES = (".gov.cn", ".edu.cn", ".ac.cn", ".org.cn", ".gov", ".edu")
_AUTHORITATIVE_DOMAINS = {
    "gov.cn": 1.0,
    "stats.gov.cn": 1.0,
    "npc.gov.cn": 1.0,
    "mca.gov.cn": 1.0,
    "moe.gov.cn": 1.0,
    "cass.cn": 0.95,
    "cssn.cn": 0.9,
    "cnki.net": 0.9,
    "doi.org": 0.9,
}


def _download_json(url: str, timeout: float) -> Mapping[str, object]:
    request = Request(url, headers={"User-Agent": _USER_AGENT})
    with build_opener().open(request, timeout=timeout) as response:
        payload = response.read(5_000_001)
    if len(payload) > 5_000_000:
        raise RuntimeError("搜索结果超过读取上限")
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise RuntimeError("搜索服务返回了无效数据")
    return parsed


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def _search_tavily(
    query: str, max_results: int, *, api_key: str, timeout: float, language: str | None = None
) -> Iterable[Mapping[str, object]]:
    # Adapted from STORM's MIT-licensed TavilySearchRM and Open Deep
    # Research's MIT-licensed Tavily async search: use the provider SDK,
    # request raw content, and let the caller normalize/dedupe URLs.
    from tavily import TavilyClient

    search_options: dict[str, object] = {
        "max_results": max_results,
        "include_raw_content": True,
        "topic": "general",
        "timeout": timeout,
    }
    if language:
        search_options["language"] = language
    response = TavilyClient(api_key=api_key).search(query, **search_options)
    values = response.get("results") if isinstance(response, Mapping) else None
    if not isinstance(values, list):
        raise RuntimeError("Tavily 返回了无效结果")
    return (
        {
            **item,
            "content": item.get("raw_content") or item.get("content") or "",
        }
        for item in values
        if isinstance(item, Mapping)
    )


def plan_web_queries(query: str, *, profile: SearchProfile = "sociology") -> list[str]:
    """Clean the Agent's search-box query using STORM's bounded-query convention."""

    del profile

    normalized = re.sub(r"\s+", " ", query).strip()
    if not normalized:
        raise ValueError("联网搜索词不能为空")
    cleaned = normalized.replace("-", "").strip().strip('"').strip("'").strip()
    if not cleaned:
        raise ValueError("联网搜索词不能为空")
    return [cleaned]


def _fetch_page(url: str) -> str | None:
    _ensure_public_url(url)
    return _download_page(url)


def _download_page(url: str) -> str:
    opener = build_opener(_PublicRedirectHandler())
    request = Request(url, headers={"User-Agent": _USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"})
    with opener.open(request, timeout=15) as response:
        payload = response.read(2_000_001)
        if len(payload) > 2_000_000:
            raise RuntimeError("网页正文超过读取上限")
        charset = response.headers.get_content_charset() or _html_charset(payload) or "utf-8"
        return payload.decode(charset, errors="replace")


def _html_charset(payload: bytes) -> str | None:
    """Honor legacy Chinese pages that declare GBK in HTML rather than headers."""

    head = payload[:8192].decode("ascii", errors="ignore")
    match = re.search(r"(?:charset|encoding)\s*=\s*[\"']?\s*([A-Za-z0-9._-]+)", head, re.I)
    return match.group(1) if match else None


class _PublicRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _ensure_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _ensure_public_url(url: str) -> None:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise ValueError("只支持公开的 HTTP 或 HTTPS 网页")
    if hostname.lower() == "localhost":
        raise ValueError("不能读取本机或内网地址")
    try:
        literal = ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise ValueError("不能读取本机或内网地址")


def _canonical_url(url: str) -> str:
    parsed = urlparse(url)
    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith(_TRACKING_PREFIXES)
    ]
    return urlunparse(parsed._replace(fragment="", query=urlencode(filtered_query, doseq=True)))


def _tokenize(value: str) -> set[str]:
    lowered = value.lower()
    tokens = set(re.findall(r"[\w-]{2,}", lowered, flags=re.UNICODE))
    cjk = re.findall(r"[\u4e00-\u9fff]", lowered)
    tokens.update("".join(cjk[index : index + 2]) for index in range(len(cjk) - 1))
    return tokens


def _authority_score(url: str) -> float:
    hostname = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if hostname in _AUTHORITATIVE_DOMAINS:
        return _AUTHORITATIVE_DOMAINS[hostname]
    for domain, score in _AUTHORITATIVE_DOMAINS.items():
        if hostname.endswith("." + domain):
            return score
    return 0.75 if hostname.endswith(_OFFICIAL_SUFFIXES) else 0.0


def _relevance_score(query: str, item: Mapping[str, str]) -> float:
    query_tokens = _tokenize(query)
    result_tokens = _tokenize(f"{item.get('title', '')} {item.get('snippet', '')}")
    return len(query_tokens & result_tokens) / len(query_tokens) if query_tokens else 0.0


def _extract_page(html: str) -> str | None:
    from trafilatura import extract

    return extract(
        html,
        include_comments=False,
        include_images=False,
        include_links=False,
        favor_precision=True,
    )


def _extract_title(html: str) -> str | None:
    from trafilatura.metadata import extract_metadata

    metadata = extract_metadata(html)
    return metadata.title if metadata is not None else None


class OpenWebResearchClient:
    """Open-web adapter using a pluggable provider and bounded research queries."""

    def __init__(
        self,
        *,
        search: SearchFunction | None = None,
        search_provider: str = "tavily",
        search_api_key: str | None = None,
        search_base_url: str | None = None,
        search_engines: tuple[str, ...] = (),
        search_timeout_seconds: float = 12,
        search_transport: SearchTransport | None = None,
        profile: SearchProfile = "sociology",
        allowed_domains: tuple[str, ...] = (),
        reranker: WebCandidateReranker | None = None,
        fetch: FetchFunction = _fetch_page,
        extract: ExtractFunction = _extract_page,
        extract_title: ExtractFunction = _extract_title,
    ) -> None:
        del search_engines
        if profile not in {"generic", "sociology"}:
            raise ValueError("未知联网搜索语境")
        if search is not None:
            self._search = search
        elif search_provider == "custom":
            self._search = partial(
                self._search_custom,
                search_base_url=search_base_url,
                timeout=search_timeout_seconds,
                transport=search_transport or _download_json,
            )
        elif search_transport is not None:
            self._search = partial(
                self._search_custom,
                search_base_url=search_base_url,
                timeout=search_timeout_seconds,
                transport=search_transport,
            )
        else:
            self._search = partial(
                self._search_provider,
                provider=search_provider,
                api_key=search_api_key,
                timeout=search_timeout_seconds,
                language="zh" if profile == "sociology" else None,
            )
        self._provider = search_provider
        self._profile = profile
        self._allowed_domains = tuple(
            domain.lower().removeprefix("www.") for domain in allowed_domains if domain.strip()
        )
        self._reranker = reranker
        self._fetch = fetch
        self._extract = extract
        self._extract_title = extract_title

    @property
    def search_provider_name(self) -> str:
        return self._provider

    @staticmethod
    def _search_custom(
        query: str,
        max_results: int,
        *,
        search_base_url: str | None,
        timeout: float,
        transport: SearchTransport,
    ) -> Iterable[Mapping[str, object]]:
        if not search_base_url:
            raise ValueError("自定义搜索提供方缺少地址")
        parsed = urlparse(search_base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("搜索服务地址必须是 HTTP 或 HTTPS URL")
        endpoint = (
            f"{search_base_url.rstrip('/')}/search?{urlencode({'q': query, 'limit': max_results})}"
        )
        payload = transport(endpoint, timeout)
        values = payload.get("results")
        if not isinstance(values, list):
            raise RuntimeError("自定义搜索服务返回了无效结果")
        return (item for item in values[:max_results] if isinstance(item, Mapping))

    @staticmethod
    def _search_provider(
        query: str,
        max_results: int,
        *,
        provider: str,
        api_key: str | None,
        timeout: float,
        language: str | None,
    ) -> Iterable[Mapping[str, object]]:
        if provider == "tavily" and api_key:
            return _search_tavily(
                query, max_results, api_key=api_key, timeout=timeout, language=language
            )
        raise ValueError(f"搜索提供方 {provider} 缺少有效配置")

    def search(self, query: str, *, limit: int = 5) -> list[dict[str, str]]:
        safe_limit = max(1, min(limit, 8))
        candidates: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for planned_query in plan_web_queries(query, profile=self._profile):
            recall_limit = max(8, min(32, safe_limit * 4))
            for item in self._search(planned_query, recall_limit):
                title = str(item.get("title") or item.get("name") or "").strip()
                url = str(item.get("href") or item.get("url") or "").strip()
                snippet = str(
                    item.get("body")
                    or item.get("snippet")
                    or item.get("content")
                    or item.get("description")
                    or ""
                ).strip()
                if not title or not url:
                    continue
                try:
                    _ensure_public_url(url)
                except ValueError:
                    continue
                canonical_url = _canonical_url(url)
                hostname = (urlparse(url).hostname or "").lower().removeprefix("www.")
                if self._allowed_domains and not any(
                    hostname == domain or hostname.endswith("." + domain)
                    for domain in self._allowed_domains
                ):
                    continue
                if canonical_url in seen_urls:
                    continue
                seen_urls.add(canonical_url)
                candidates.append({"title": title, "url": url, "snippet": snippet})
        candidates.sort(
            key=lambda item: (-_authority_score(item["url"]), -_relevance_score(query, item))
        )
        return self._rerank_candidates(query, candidates, safe_limit)[:safe_limit]

    def _rerank_candidates(
        self, query: str, candidates: list[dict[str, str]], limit: int
    ) -> list[dict[str, str]]:
        if self._reranker is None or not candidates:
            return candidates
        chunks = tuple(
            RetrievalChunk(
                chunk_id=f"web:{index}",
                document_kind="web_search_result",
                knowledge_id=None,
                theory_id=None,
                content_version=1,
                content_hash=sha256(f"{item['title']}\n{item['snippet']}".encode()).hexdigest(),
                title=item["title"],
                text=f"{item['title']}\n{item['snippet']}",
                source_ids=(item["url"],),
            )
            for index, item in enumerate(candidates)
        )
        try:
            outcome = self._reranker.search_chunks(query=query, chunks=chunks, limit=limit)
            ranked_ids = [
                chunk.chunk_id
                for hit in getattr(outcome, "hits", ())
                if (chunk := getattr(hit, "chunk", None)) is not None
            ]
        except (AttributeError, RetrievalPipelineUnavailable, TypeError, ValueError):
            return candidates
        by_id = {f"web:{index}": item for index, item in enumerate(candidates)}
        ranked = [by_id[chunk_id] for chunk_id in ranked_ids if chunk_id in by_id]
        ranked_ids_set = set(ranked_ids)
        ranked.extend(
            item for index, item in enumerate(candidates) if f"web:{index}" not in ranked_ids_set
        )
        return ranked

    def read(self, url: str) -> dict[str, str]:
        _ensure_public_url(url)
        html = self._fetch(url)
        if not html:
            raise RuntimeError("网页暂时无法读取")
        content = (self._extract(html) or "").strip()
        if not content:
            raise RuntimeError("网页没有可读取的正文")
        return {
            "title": (self._extract_title(html) or "").strip(),
            "url": url,
            "content": content[:12_000],
        }
