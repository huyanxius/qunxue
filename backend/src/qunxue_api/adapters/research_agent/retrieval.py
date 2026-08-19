"""Small, provider-independent retrieval primitives used by the Agent adapter.

The module deliberately does not know about SQLAlchemy, a vector database, or a
specific embedding vendor.  It provides the deterministic pieces that every
retrieval backend needs: query normalization, fuzzy lexical scoring, and rank
fusion.  Dense retrieval can be added behind the same ``RetrievalCandidate``
shape without changing Agent tools.
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

_LATIN_WORD = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    citation_id: str
    score: float
    source: str
    sources: tuple[str, ...] = ()


def normalize_query(value: str) -> str:
    """Normalize user text while preserving Chinese characters for matching."""

    folded = "".join(value.casefold().split())
    return "".join(char for char in folded if char.isalnum() or "\u4e00" <= char <= "\u9fff")


def fuzzy_match_score(
    query: str,
    *,
    title: str,
    aliases: tuple[str, ...] = (),
    text: str = "",
) -> float:
    """Return a bounded relevance score for lexical and fuzzy matching.

    Titles and aliases carry more weight than body text.  Character n-grams are
    used for Chinese because whitespace tokenization is not reliable for short
    Chinese concepts; Latin words are compared as normalized tokens as well.
    This is a first-stage recall score, not the final answer-grounding score.
    """

    normalized_query = normalize_query(query)
    if not normalized_query:
        return 0.0

    fields = (title, *aliases, text[:1600])
    field_scores = [
        _field_similarity(normalized_query, normalize_query(field)) for field in fields
    ]
    title_score = field_scores[0]
    alias_score = max(field_scores[1:-1], default=0.0)
    body_score = field_scores[-1]
    return min(1.0, max(title_score, alias_score * 0.92, body_score * 0.72))


def lexical_relevance_score(
    query: str,
    *,
    title: str,
    aliases: tuple[str, ...] = (),
    text: str = "",
) -> float:
    """Rank a catalog hit while keeping exact concept names ahead of noise.

    SQLite FTS can return a broad body-text hit for a short fragment such as
    ``什么是社``.  The score therefore gives the longest title/alias overlap a
    deliberate priority, while retaining the existing fuzzy body score as a
    recall fallback.  Dense retrieval and a reranker can later emit the same
    ``RetrievalCandidate`` shape and be fused without changing the tool API.
    """

    normalized_query = normalize_query(query)
    if not normalized_query:
        return 0.0

    title_overlap = max(
        (_overlap_score(normalized_query, normalize_query(field)) for field in (title, *aliases)),
        default=0.0,
    )
    fuzzy_score = fuzzy_match_score(
        normalized_query,
        title=title,
        aliases=aliases,
        text=text,
    )
    return min(1.0, max(title_overlap, fuzzy_score * 0.72))


def rrf_fuse(
    ranked_lists: tuple[list[RetrievalCandidate], ...],
    *,
    limit: int,
    rank_constant: int = 60,
) -> list[RetrievalCandidate]:
    """Fuse ranked lists using Reciprocal Rank Fusion.

    Raw scores from lexical and dense retrievers have incompatible scales, so
    only rank positions contribute to the fused score.  A candidate keeps the
    retrieval sources that found it for traceability in the UI.
    """

    fused: dict[str, tuple[float, set[str]]] = {}
    for ranked in ranked_lists:
        for rank, candidate in enumerate(ranked, start=1):
            score, sources = fused.get(candidate.citation_id, (0.0, set()))
            sources.add(candidate.source)
            fused[candidate.citation_id] = (
                score + 1 / (rank_constant + rank),
                sources,
            )

    ordered = sorted(
        fused.items(),
        key=lambda item: (-item[1][0], item[0]),
    )
    return [
        RetrievalCandidate(
            citation_id=citation_id,
            score=score,
            source="hybrid",
            sources=tuple(
                source
                for source in ("lexical", "semantic", "fuzzy", "rerank")
                if source in sources
            ),
        )
        for citation_id, (score, sources) in ordered[:limit]
    ]


def _field_similarity(query: str, field: str) -> float:
    if not field:
        return 0.0
    if query in field:
        return 1.0

    query_ngrams = _ngrams(query)
    field_ngrams = _ngrams(field)
    ngram_score = (
        len(query_ngrams & field_ngrams) / len(query_ngrams) if query_ngrams else 0.0
    )
    sequence_score = SequenceMatcher(None, query, field).ratio()
    common_blocks = SequenceMatcher(None, query, field).get_matching_blocks()
    longest_common = max((block.size for block in common_blocks), default=0)
    common_substring_score = longest_common / min(len(query), len(field))
    token_score = _token_overlap(query, field)
    return max(ngram_score, sequence_score, common_substring_score, token_score)


def _overlap_score(query: str, field: str) -> float:
    """Return the relative length of the longest meaningful shared substring."""

    if not query or not field:
        return 0.0
    longest = max(
        (block.size for block in SequenceMatcher(None, query, field).get_matching_blocks()),
        default=0,
    )
    # One-character overlaps are common in Chinese and are not useful evidence.
    if longest < 2:
        return 0.0
    return longest / min(len(query), len(field))


def _ngrams(value: str) -> set[str]:
    if len(value) < 2:
        return {value} if value else set()
    return {value[index : index + 2] for index in range(len(value) - 1)}


def _token_overlap(query: str, field: str) -> float:
    query_tokens = set(_LATIN_WORD.findall(query)) | set(_CJK_RUN.findall(query))
    field_tokens = set(_LATIN_WORD.findall(field)) | set(_CJK_RUN.findall(field))
    if not query_tokens:
        return 0.0
    return len(query_tokens & field_tokens) / len(query_tokens)
