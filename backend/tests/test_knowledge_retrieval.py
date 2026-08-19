from types import SimpleNamespace

from qunxue_api.adapters.research_agent.catalog_tools import KnowledgeToolRegistry, _rank_page_items
from qunxue_api.adapters.research_agent.retrieval import (
    RetrievalCandidate,
    fuzzy_match_score,
    normalize_query,
    rrf_fuse,
)


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


def test_knowledge_search_ranks_the_full_concept_above_a_short_phrase_hit() -> None:
    release = SimpleNamespace(knowledge_release_id="release-preview")
    noisy = SimpleNamespace(
        knowledge_id="D1:C138",
        title="权力平衡",
        category="古典社会学奠基",
        dimension="本体论",
        eligibility=SimpleNamespace(rag_eligible=False, browse_eligible=True),
    )
    target = SimpleNamespace(
        knowledge_id="D1:C029",
        title="社会行动四类型",
        category="古典社会学奠基",
        dimension="本体论",
        eligibility=SimpleNamespace(rag_eligible=False, browse_eligible=True),
    )
    details = {
        noisy.knowledge_id: SimpleNamespace(
            summary=noisy,
            aliases=(),
            content="社会关系中的权力平衡与资源配置。",
            sources=(),
        ),
        target.knowledge_id: SimpleNamespace(
            summary=target,
            aliases=(),
            content="韦伯将社会行动区分为目的理性、价值理性、情感和传统四类。",
            sources=(),
        ),
    }

    class Catalog:
        def current_release(self, *, purpose):
            del purpose
            return release

        def browse(self, **kwargs):
            query = kwargs["query"]
            if query is None:
                return SimpleNamespace(entries=(noisy, target), next_cursor=None)
            if "什么是社" in query:
                return SimpleNamespace(entries=(noisy,), next_cursor=None)
            if "社会行动" in query or "行动四" in query:
                return SimpleNamespace(entries=(target,), next_cursor=None)
            return SimpleNamespace(entries=(), next_cursor=None)

        def get_entry(self, *, knowledge_id, release_id):
            assert release_id == release.knowledge_release_id
            return details[knowledge_id]

    results = KnowledgeToolRegistry(Catalog()).search_knowledge(
        "请检索知识库，解释什么是社会行动四类型？"
    )

    assert results[0]["knowledge_id"] == "D1:C029"


def test_lexical_catalog_candidates_drop_zero_relevance_hits() -> None:
    unrelated = SimpleNamespace(
        knowledge_id="D1:unrelated",
        title="完全无关标题",
        category="别类",
        dimension="本体论",
    )

    assert _rank_page_items("青年孤独", [unrelated]) == []
