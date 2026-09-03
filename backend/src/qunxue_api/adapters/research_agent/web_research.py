from collections.abc import Callable, Iterable, Mapping
from ipaddress import ip_address
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

SearchFunction = Callable[[str, int], Iterable[Mapping[str, object]]]
FetchFunction = Callable[[str], str | None]
ExtractFunction = Callable[[str], str | None]


def _search_ddgs(query: str, max_results: int) -> Iterable[Mapping[str, object]]:
    from ddgs import DDGS

    # Yahoo is the default auto backend but is intermittently unreachable from
    # the production host; prefer engines that remain accessible there.
    return DDGS(timeout=8).text(query, backend="duckduckgo,bing", max_results=max_results)


def _fetch_page(url: str) -> str | None:
    _ensure_public_url(url)
    try:
        return _download_page(url)
    except Exception:
        parsed = urlparse(url)
        reader_url = f"https://r.jina.ai/http://{parsed.netloc}{parsed.path}"
        if parsed.query:
            reader_url = f"{reader_url}?{parsed.query}"
        return f"QUNXUE_READER_MARKDOWN\n{_download_page(reader_url)}"


def _download_page(url: str) -> str:
    opener = build_opener(_PublicRedirectHandler())
    request = Request(url, headers={"User-Agent": "QunxueResearchAgent/1.0"})
    with opener.open(request, timeout=10) as response:
        payload = response.read(2_000_001)
        if len(payload) > 2_000_000:
            raise RuntimeError("网页正文超过读取上限")
        charset = response.headers.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")


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


def _extract_page(html: str) -> str | None:
    if html.startswith("QUNXUE_READER_MARKDOWN\n"):
        markdown = html.removeprefix("QUNXUE_READER_MARKDOWN\n")
        _, separator, content = markdown.partition("Markdown Content:")
        return (content if separator else markdown).strip()
    from trafilatura import extract

    return extract(
        html,
        include_comments=False,
        include_images=False,
        include_links=False,
        favor_precision=True,
    )


def _extract_title(html: str) -> str | None:
    if html.startswith("QUNXUE_READER_MARKDOWN\n"):
        first_line = html.removeprefix("QUNXUE_READER_MARKDOWN\n").splitlines()[0]
        return first_line.removeprefix("Title:").strip() or None
    from trafilatura.metadata import extract_metadata

    metadata = extract_metadata(html)
    return metadata.title if metadata is not None else None


class OpenWebResearchClient:
    """Small open-web adapter backed by DDGS search and Trafilatura extraction."""

    def __init__(
        self,
        *,
        search: SearchFunction = _search_ddgs,
        fetch: FetchFunction = _fetch_page,
        extract: ExtractFunction = _extract_page,
        extract_title: ExtractFunction = _extract_title,
    ) -> None:
        self._search = search
        self._fetch = fetch
        self._extract = extract
        self._extract_title = extract_title

    def search(self, query: str, *, limit: int = 5) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        for item in self._search(query, max(1, min(limit, 8))):
            title = str(item.get("title") or "").strip()
            url = str(item.get("href") or item.get("url") or "").strip()
            snippet = str(item.get("body") or item.get("snippet") or "").strip()
            try:
                _ensure_public_url(url)
            except ValueError:
                continue
            if not title:
                continue
            results.append({"title": title, "url": url, "snippet": snippet})
        return results

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
