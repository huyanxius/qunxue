import json
import re
from collections.abc import Callable, Iterable, Mapping
from functools import partial
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
from ipaddress import ip_address
from typing import Literal, Protocol
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree

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


class _DuckDuckGoParser(HTMLParser):
    """Parse public result cards without scraping answer prose."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._in_result = False
        self._depth = 0
        self._link: dict[str, str] | None = None
        self._snippet = False
        self._text: list[str] = []

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        return set((dict(attrs).get("class") or "").split())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = self._classes(attrs)
        if tag == "div" and "result" in classes:
            self._in_result = True
            self._depth = 1
            return
        if not self._in_result:
            return
        if tag == "div":
            self._depth += 1
        if tag == "a" and "result__a" in classes:
            self._link = {"url": _decode_search_url(dict(attrs).get("href") or ""), "title": ""}
            self._text = []
        elif tag in {"a", "span", "div"} and "result__snippet" in classes:
            self._snippet = True
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        if not self._in_result:
            return
        if tag == "a" and self._link is not None:
            self._link["title"] = _clean_text("".join(self._text))
            self._text = []
        elif tag in {"a", "span", "div"} and self._snippet:
            if self._link is not None:
                self._link["snippet"] = _clean_text("".join(self._text))
            self._snippet = False
            self._text = []
        if tag == "div":
            self._depth -= 1
            if self._depth == 0:
                if self._link is not None and self._link.get("url"):
                    self.results.append(self._link)
                self._link = None
                self._in_result = False

    def handle_data(self, data: str) -> None:
        if self._in_result and (self._link is not None or self._snippet):
            self._text.append(data)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def _decode_search_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.path == "/l/" and parsed.query:
        target = dict(parse_qsl(parsed.query)).get("uddg")
        if target:
            return unquote(target)
    return url


def _search_duckduckgo(
    query: str, max_results: int, *, timeout: float
) -> Iterable[Mapping[str, object]]:
    url = "https://html.duckduckgo.com/html/?" + urlencode({"q": query, "kl": "cn-zh"})
    request = Request(url, headers={"User-Agent": _USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"})
    with build_opener().open(request, timeout=timeout) as response:
        html = response.read(5_000_001).decode(
            response.headers.get_content_charset() or "utf-8", "replace"
        )
    parser = _DuckDuckGoParser()
    parser.feed(html)
    if parser.results:
        return parser.results[:max_results]
    # DDG may present a browser challenge to server-side callers. Bing's
    # public RSS endpoint is a bounded fallback, not a second query family.
    return _search_bing_rss(query, max_results, timeout=timeout)


def _search_bing_rss(
    query: str, max_results: int, *, timeout: float
) -> Iterable[Mapping[str, object]]:
    url = "https://www.bing.com/search?" + urlencode({"format": "rss", "q": query})
    request = Request(url, headers={"User-Agent": _USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"})
    with build_opener().open(request, timeout=timeout) as response:
        payload = response.read(5_000_001)
    root = ElementTree.fromstring(payload)
    results: list[dict[str, str]] = []
    for item in root.findall("./channel/item"):
        title = _clean_text(item.findtext("title") or "")
        link = _clean_text(item.findtext("link") or "")
        snippet = _clean_text(item.findtext("description") or "")
        if title and link:
            results.append({"title": title, "url": link, "snippet": snippet})
    return results[:max_results]


def _search_tavily(
    query: str, max_results: int, *, api_key: str, timeout: float
) -> Iterable[Mapping[str, object]]:
    payload = json.dumps(
        {"api_key": api_key, "query": query, "max_results": max_results, "include_answer": False}
    ).encode()
    request = Request(
        "https://api.tavily.com/search",
        data=payload,
        headers={"User-Agent": _USER_AGENT, "Content-Type": "application/json"},
    )
    with build_opener().open(request, timeout=timeout) as response:
        parsed = json.loads(response.read(5_000_001))
    values = parsed.get("results") if isinstance(parsed, Mapping) else None
    if not isinstance(values, list):
        raise RuntimeError("Tavily 返回了无效结果")
    return (item for item in values if isinstance(item, Mapping))


def _search_brave(
    query: str, max_results: int, *, api_key: str, timeout: float
) -> Iterable[Mapping[str, object]]:
    endpoint = "https://api.search.brave.com/res/v1/web/search?" + urlencode(
        {"q": query, "count": max_results}
    )
    request = Request(
        endpoint,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
        },
    )
    with build_opener().open(request, timeout=timeout) as response:
        parsed = json.loads(response.read(5_000_001))
    web = parsed.get("web") if isinstance(parsed, Mapping) else None
    values = web.get("results") if isinstance(web, Mapping) else None
    if not isinstance(values, list):
        raise RuntimeError("Brave 返回了无效结果")
    return (item for item in values if isinstance(item, Mapping))


def plan_web_queries(query: str, *, profile: SearchProfile = "sociology") -> list[str]:
    """Create bounded generic queries, then add sociology-specific context."""

    normalized = re.sub(r"\s+", " ", query).strip()
    if not normalized:
        raise ValueError("联网搜索词不能为空")
    queries = [normalized]
    if profile == "sociology" and "社会学" not in normalized:
        queries.append(f"{normalized} 社会学")
        if any(
            marker in normalized
            for marker in ("政策", "就业", "教育", "住房", "迁移", "人口", "劳动", "孤独")
        ):
            queries.append(f"{normalized} 官方 数据 报告")
    return list(dict.fromkeys(queries))


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
        search_provider: str = "bing",
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
        query: str, max_results: int, *, provider: str, api_key: str | None, timeout: float
    ) -> Iterable[Mapping[str, object]]:
        if provider == "duckduckgo":
            return _search_duckduckgo(query, max_results, timeout=timeout)
        if provider == "bing":
            return _search_bing_rss(query, max_results, timeout=timeout)
        if provider == "tavily" and api_key:
            return _search_tavily(query, max_results, api_key=api_key, timeout=timeout)
        if provider == "brave" and api_key:
            return _search_brave(query, max_results, api_key=api_key, timeout=timeout)
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
