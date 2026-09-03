from types import SimpleNamespace

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
        assert max_results == 2
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
