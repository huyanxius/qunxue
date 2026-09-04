from types import SimpleNamespace

import pytest

from qunxue_api.adapters.research_agent.catalog_tools import KnowledgeToolRegistry
from qunxue_api.adapters.research_agent.retrieval import (
    RetrievalCandidate,
    fuzzy_match_score,
    normalize_query,
    rrf_fuse,
)
from qunxue_api.adapters.retrieval import RetrievalChunk
from qunxue_api.adapters.retrieval.hybrid import (
    HybridRetrievalHit,
    HybridRetrievalResult,
    RetrievalPipelineUnavailable,
)
from qunxue_api.adapters.theory_evidence import CatalogTheoryLexicalRetriever


def test_normalize_query_collapses_punctuation_and_case_for_fuzzy_matching() -> None:
    assert normalize_query("  符号互动论？  ") == "符号互动论"
    assert normalize_query("Symbolic-Interactionism") == "symbolicinteractionism"


def test_fuzzy_match_score_accepts_typo_and_alias_without_exact_keyword() -> None:
    score = fuzzy_match_score(
        "那个研究人如何通过互动形成自我理解的理论",
        title="符号互动论",
        aliases=("Symbolic Interactionism", "互动论"),
        text="关注符号、互动与自我意义建构。",
    )

    assert score >= 0.35


def test_rrf_fuse_merges_lexical_and_semantic_rankings_without_score_scale_assumptions() -> None:
    lexical = [
        RetrievalCandidate("knowledge:a", 0.98, "lexical"),
        RetrievalCandidate("knowledge:b", 0.80, "lexical"),
    ]
    semantic = [
        RetrievalCandidate("knowledge:b", 0.91, "semantic"),
        RetrievalCandidate("knowledge:c", 0.89, "semantic"),
    ]

    fused = rrf_fuse((lexical, semantic), limit=3)

    assert [item.citation_id for item in fused] == [
        "knowledge:b",
        "knowledge:a",
        "knowledge:c",
    ]
    assert fused[0].sources == ("lexical", "semantic")


def test_lexical_fallback_returns_no_hits_when_query_has_no_relevance() -> None:
    chunk = RetrievalChunk(
        chunk_id="knowledge:alienation",
        document_kind="knowledge_entry",
        knowledge_id="D1:C001",
        theory_id=None,
        content_version=1,
        content_hash="sha256:alienation",
        title="异化劳动",
        text="劳动者与劳动产品之间的结构性分离。",
        source_ids=(),
    )

    result = CatalogTheoryLexicalRetriever._lexical_result(
        query="qzxv",
        chunks=(chunk,),
        limit=3,
        retrieval_index_id="catalog-lexical:test",
    )

    assert result.hits == ()


def test_knowledge_search_requires_the_release_bound_hybrid_retriever() -> None:
    release = SimpleNamespace(
        knowledge_release_id="release-reviewed-v1",
        content_hash="sha256:release-reviewed-v1",
    )

    class Catalog:
        def current_release(self, *, purpose):
            del purpose
            return release

        def browse(self, **kwargs):
            del kwargs
            return SimpleNamespace(entries=(), next_cursor=None)

    with pytest.raises(RetrievalPipelineUnavailable, match="hybrid retriever"):
        KnowledgeToolRegistry(Catalog()).search_knowledge("青年孤独的结构成因")


def test_knowledge_registry_does_not_fall_back_to_a_preview_release() -> None:
    calls = []

    class Catalog:
        def current_release(self, *, purpose):
            calls.append(purpose.value)
            if purpose.value == "match":
                raise LookupError("no final MATCH release")
            return SimpleNamespace(knowledge_release_id="preview-release")

    with pytest.raises(RetrievalPipelineUnavailable, match="final MATCH"):
        KnowledgeToolRegistry(Catalog(), retriever=object())

    assert calls == ["match"]


def test_knowledge_search_maps_hybrid_chunks_to_auditable_evidence() -> None:
    release = SimpleNamespace(
        knowledge_release_id="release-reviewed-v1",
        content_hash="sha256:release-reviewed-v1",
    )
    source = SimpleNamespace(
        source_id="source:putnam",
        title="Bowling Alone",
        locator="Chapter 1",
        url="https://example.com/bowling-alone",
        verification_status=SimpleNamespace(value="verified"),
        use_boundary="仅支持社会资本与持续关系网络的命题。",
    )
    summary = SimpleNamespace(
        knowledge_id="D2:P001",
        content_version=2,
        title="社会资本理论",
        category="中层理论",
        dimension="关系结构",
        eligibility=SimpleNamespace(rag_eligible=True),
    )
    detail = SimpleNamespace(
        summary=summary,
        aliases=("社会资本",),
        content="信任、互惠规范和持续关系网络支持集体行动。",
        sources=(source,),
    )
    calls: list[dict[str, object]] = []

    class Catalog:
        def current_release(self, *, purpose):
            del purpose
            return release

        def get_entry(self, *, knowledge_id, release_id):
            assert knowledge_id == summary.knowledge_id
            assert release_id == release.knowledge_release_id
            return detail

    class Retriever:
        def search(self, **kwargs):
            calls.append(kwargs)
            return HybridRetrievalResult(
                retrieval_index_id="retrieval-index:reviewed-v1",
                mode="hybrid_reranked",
                embedding_model="Pro/BAAI/bge-m3",
                reranker_model="Pro/BAAI/bge-reranker-v2-m3",
                degraded_reason=None,
                hits=(
                    HybridRetrievalHit(
                        chunk=RetrievalChunk(
                            chunk_id="theory-profile:social-capital:v2",
                            document_kind="theory_profile",
                            knowledge_id=summary.knowledge_id,
                            theory_id="social-capital",
                            content_version=2,
                            content_hash="sha256:social-capital-v2",
                            title=summary.title,
                            text="社会资本理论解释持续关系如何支持社区互助。",
                            source_ids=(source.source_id,),
                        ),
                        fused_score=0.031,
                        retrieval_sources=("lexical", "semantic"),
                        rerank_score=0.93,
                    ),
                ),
            )

    registry = KnowledgeToolRegistry(Catalog(), retriever=Retriever())
    results = registry.search_knowledge("成员流动后社区互助为什么减少？")

    assert calls == [
        {
            "query": "成员流动后社区互助为什么减少？",
            "knowledge_release_id": release.knowledge_release_id,
            "release_content_hash": release.content_hash,
            "document_kind": None,
            "limit": 5,
        }
    ]
    assert results == [
        {
            "citation_id": "retrieval:theory-profile:social-capital:v2",
            "knowledge_id": "D2:P001",
            "theory_id": "social-capital",
            "chunk_id": "theory-profile:social-capital:v2",
            "title": "社会资本理论",
            "excerpt": "社会资本理论解释持续关系如何支持社区互助。",
            "retrieval_index_id": "retrieval-index:reviewed-v1",
            "retrieval_mode": "hybrid_reranked",
            "retrieval_sources": ["lexical", "semantic"],
            "rerank_score": 0.93,
            "embedding_model": "Pro/BAAI/bge-m3",
            "reranker_model": "Pro/BAAI/bge-reranker-v2-m3",
            "source_citation_ids": ["source:source:putnam"],
            "evidence_status": "verified",
        }
    ]
    assert registry.evidence["retrieval:theory-profile:social-capital:v2"].kind == "theory"
    assert registry.evidence["source:source:putnam"].label == "Bowling Alone"
