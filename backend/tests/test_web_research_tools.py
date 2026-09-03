from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from qunxue_api.adapters.research_agent.catalog_tools import KnowledgeToolRegistry
from qunxue_api.adapters.research_agent.web_research import OpenWebResearchClient


class _Catalog:
    def current_release(self, *, purpose):
        del purpose
        return SimpleNamespace(knowledge_release_id="release-web", content_hash="hash-web")


class _WebResearch:
    def __init__(self) -> None:
        self.read_urls: list[str] = []

    def search(self, query: str, *, limit: int = 5) -> list[dict[str, str]]:
        assert query == "青年就业 政策"
        assert limit == 3
        return [
            {
                "title": "促进高校毕业生就业政策",
                "url": "https://www.gov.cn/zhengce/example.html",
                "snippet": "国务院有关部门发布的就业政策摘要。",
            }
        ]

    def read(self, url: str) -> dict[str, str]:
        self.read_urls.append(url)
        return {
            "title": "促进高校毕业生就业政策",
            "url": url,
            "content": "政策正文说明了高校毕业生就业支持措施。",
        }


def test_web_tools_are_opt_in_and_keep_results_inside_the_evidence_set() -> None:
    client = _WebResearch()
    tools = KnowledgeToolRegistry(_Catalog(), web_research=client)

    with pytest.raises(ValueError, match="联网搜索未开启"):
        tools.search_web("青年就业 政策", limit=3)

    tools.enable_web_search()
    results = tools.search_web("青年就业 政策", limit=3)

    assert results == [{
        "citation_id": "web:https://www.gov.cn/zhengce/example.html",
        "title": "促进高校毕业生就业政策",
        "url": "https://www.gov.cn/zhengce/example.html",
        "excerpt": "国务院有关部门发布的就业政策摘要。",
        "source_kind": "web",
        "evidence_status": "retrieved",
    }]
    evidence = tools.evidence[results[0]["citation_id"]]
    assert evidence.label == "促进高校毕业生就业政策"
    assert evidence.source_id == "https://www.gov.cn/zhengce/example.html"
    assert evidence.source_kind == "web"

    page = tools.read_web_page("https://www.gov.cn/zhengce/example.html")

    assert page["content"] == "政策正文说明了高校毕业生就业支持措施。"
    assert client.read_urls == ["https://www.gov.cn/zhengce/example.html"]
    assert tools.evidence[results[0]["citation_id"]].excerpt == page["content"]


def test_web_page_reader_rejects_urls_outside_the_current_search_results() -> None:
    tools = KnowledgeToolRegistry(_Catalog(), web_research=_WebResearch())
    tools.enable_web_search()

    with pytest.raises(ValueError, match="先通过联网搜索取得网页地址"):
        tools.read_web_page("http://127.0.0.1/private")


def test_open_web_client_normalizes_search_results_and_extracts_page_text() -> None:
    def search(query: str, max_results: int):
        assert query == "社会工作 政策"
        assert max_results == 8
        return [{
            "title": " 社会工作政策文件 ",
            "href": "https://example.gov.cn/policy",
            "body": " 政策摘要 ",
        }]

    client = OpenWebResearchClient(
        search=search,
        fetch=lambda url: f"<html><title>政策原文</title><body>{url} 正文</body></html>",
        extract=lambda html: "政策完整正文" if "example.gov.cn" in html else None,
        extract_title=lambda html: "政策原文" if html else None,
    )

    assert client.search("社会工作 政策", limit=2) == [{
        "title": "社会工作政策文件",
        "url": "https://example.gov.cn/policy",
        "snippet": "政策摘要",
    }]
    assert client.read("https://example.gov.cn/policy") == {
        "title": "政策原文",
        "url": "https://example.gov.cn/policy",
        "content": "政策完整正文",
    }


def test_open_web_client_queries_bing_and_baidu_through_searxng() -> None:
    requests: list[tuple[str, float]] = []

    def search_transport(url: str, timeout: float):
        requests.append((url, timeout))
        return {
            "query": "青年就业 政策",
            "number_of_results": 2,
            "results": [
                {
                    "title": "国务院政策文件",
                    "url": "https://www.gov.cn/zhengce/example.html",
                    "content": "高校毕业生就业支持政策。",
                    "engine": "bing",
                    "engines": ["bing", "baidu"],
                    "score": 4.0,
                }
            ],
            "answers": [],
            "corrections": [],
            "infoboxes": [],
            "suggestions": [],
            "unresponsive_engines": [],
        }

    client = OpenWebResearchClient(
        search_base_url="http://127.0.0.1:8093",
        search_engines=("bing", "baidu"),
        search_timeout_seconds=6,
        search_transport=search_transport,
    )

    assert client.search("青年就业 政策", limit=2) == [{
        "title": "国务院政策文件",
        "url": "https://www.gov.cn/zhengce/example.html",
        "snippet": "高校毕业生就业支持政策。",
    }]
    assert len(requests) == 1
    request_url, timeout = requests[0]
    assert timeout == 6
    assert urlparse(request_url).path == "/search"
    assert parse_qs(urlparse(request_url).query) == {
        "q": ["青年就业 政策"],
        "format": ["json"],
        "categories": ["general"],
        "language": ["zh-CN"],
        "engines": ["bing,baidu"],
    }


def test_open_web_client_deduplicates_and_reranks_a_recall_pool_before_limiting() -> None:
    calls: list[int] = []

    def search(query: str, max_results: int):
        assert query == "青年就业 政策"
        calls.append(max_results)
        return [
            {
                "title": "泛泛讨论",
                "href": "https://example.com/article?utm_source=search",
                "body": "就业背景",
            },
            {
                "title": "官方政策",
                "href": "https://www.gov.cn/policy#top",
                "body": "高校毕业生就业支持政策原文",
            },
            {
                "title": "官方政策重复",
                "href": "https://www.gov.cn/policy?utm_medium=search",
                "body": "重复结果",
            },
        ]

    class Reranker:
        def search_chunks(self, *, query, chunks, limit):
            assert query == "青年就业 政策"
            assert limit == 2
            by_id = {chunk.chunk_id: chunk for chunk in chunks}
            return SimpleNamespace(
                hits=tuple(
                    SimpleNamespace(chunk=by_id[chunk_id])
                    for chunk_id in ("web:1", "web:0")
                )
            )

    client = OpenWebResearchClient(search=search, reranker=Reranker())

    assert client.search("青年就业 政策", limit=2) == [
        {
            "title": "官方政策",
            "url": "https://www.gov.cn/policy#top",
            "snippet": "高校毕业生就业支持政策原文",
        },
        {
            "title": "泛泛讨论",
            "url": "https://example.com/article?utm_source=search",
            "snippet": "就业背景",
        },
    ]
    assert calls == [8]


def test_open_web_client_falls_back_to_provider_order_without_vector_retriever() -> None:
    def search(_query: str, _max_results: int):
        return [
            {
                "title": "第一条",
                "href": "https://example.com/one",
                "body": "摘要一",
            },
            {
                "title": "第一条重复",
                "href": "https://example.com/one?utm_source=search",
                "body": "摘要一重复",
            },
            {
                "title": "第二条",
                "href": "https://example.com/two",
                "body": "摘要二",
            },
        ]

    client = OpenWebResearchClient(search=search)

    assert client.search("社会政策", limit=2) == [
        {
            "title": "第一条",
            "url": "https://example.com/one",
            "snippet": "摘要一",
        },
        {
            "title": "第二条",
            "url": "https://example.com/two",
            "snippet": "摘要二",
        },
    ]
