import re
from collections.abc import Mapping, Sequence

from qunxue_api.modules.agent_conversation import (
    AgentEvidence,
    apply_research_map_patch,
    empty_research_map,
    normalize_research_map_patch,
)
from qunxue_api.modules.knowledge_catalog import KnowledgeCatalog, KnowledgeUsePurpose

from .retrieval import RetrievalCandidate, fuzzy_match_score, lexical_relevance_score

KnowledgeEvidence = AgentEvidence


class KnowledgeToolRegistry:
    """The only capabilities exposed to the natural-language Agent in phase one."""

    def __init__(self, catalog: KnowledgeCatalog) -> None:
        self._catalog = catalog
        # Agent runs pin the release used by M4/M5 provenance. MATCH selects a
        # reviewed final release when one exists, while retaining the honest
        # preview fallback when the catalog has not published one yet.
        self.release = catalog.current_release(purpose=KnowledgeUsePurpose.MATCH)
        self.evidence: dict[str, KnowledgeEvidence] = {}
        self._allowed_source_ids: set[str] = set()
        self.research_map_enabled = False
        self.research_map: dict[str, object] = empty_research_map()

    def enable_research_map(self, current: Mapping[str, object] | None = None) -> None:
        """Opt this turn into the research workspace's structured-map tool set."""

        self.research_map_enabled = True
        if current is not None:
            self.research_map = {
                "schema_version": 1,
                "nodes": [
                    dict(item) for item in current.get("nodes", []) if isinstance(item, Mapping)
                ],
                "relations": [
                    dict(item) for item in current.get("relations", []) if isinstance(item, Mapping)
                ],
            }

    def update_research_map(
        self,
        *,
        nodes: Sequence[Mapping[str, object]] | None = None,
        relations: Sequence[Mapping[str, object]] | None = None,
        remove_node_ids: Sequence[str] | None = None,
        remove_relation_ids: Sequence[str] | None = None,
    ) -> dict[str, object]:
        if not self.research_map_enabled:
            raise ValueError("research map is only available in the research workspace")
        patch = normalize_research_map_patch(
            nodes=nodes,
            relations=relations,
            remove_node_ids=remove_node_ids,
            remove_relation_ids=remove_relation_ids,
            known_node_ids={
                str(item["id"])
                for item in self.research_map.get("nodes", [])
                if isinstance(item, Mapping) and item.get("id")
            },
            evidence_ids=set(self.evidence),
        )
        self.research_map = apply_research_map_patch(self.research_map, patch)
        return patch

    def search_knowledge(self, query: str, *, limit: int = 5) -> list[dict[str, object]]:
        pages = []
        for candidate in _query_candidates(query):
            page = self._catalog.browse(
                release_id=self.release.knowledge_release_id,
                query=candidate,
                category=None,
                category_id=None,
                dimension_id=None,
                cursor=None,
                limit=max(1, min(limit, 8)),
            )
            pages.append(page)
            if any(item.eligibility.rag_eligible for item in page.entries):
                break
        results = self._results_from_pages(pages, query=query, limit=limit)
        if results:
            return results

        preview_results = self._results_from_pages(
            pages,
            query=query,
            limit=limit,
            allow_preview=True,
        )
        if preview_results:
            return preview_results

        fuzzy_entries = self._fuzzy_candidates(query)
        results = self._results_from_items(
            fuzzy_entries,
            limit=limit,
            retrieval_source="fuzzy",
        )
        if results:
            return results
        preview_entries = self._fuzzy_candidates(query, include_preview=True)
        return self._results_from_items(
            preview_entries,
            limit=limit,
            retrieval_source="fuzzy",
            allow_preview=True,
        )

    def _results_from_pages(
        self,
        pages,
        *,
        query: str,
        limit: int,
        allow_preview: bool = False,
    ) -> list[dict[str, object]]:
        items = _rank_page_items(query, [item for page in pages for item in page.entries])
        return self._results_from_items(
            items,
            limit=limit,
            retrieval_source="lexical",
            allow_preview=allow_preview,
        )

    def _results_from_items(
        self,
        items,
        *,
        limit: int,
        retrieval_source: str,
        allow_preview: bool = False,
    ) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        seen_ids: set[str] = set()
        for value in items:
            if isinstance(value, tuple):
                candidate, item = value
            else:
                candidate, item = None, value
            if item.knowledge_id in seen_ids:
                continue
            seen_ids.add(item.knowledge_id)
            if len(results) >= limit:
                break
            if not item.eligibility.rag_eligible and not allow_preview:
                continue
            try:
                detail = self._catalog.get_entry(
                    knowledge_id=item.knowledge_id,
                    release_id=self.release.knowledge_release_id,
                )
                excerpt = _excerpt(detail.content)
                self._allowed_source_ids.update(source.source_id for source in detail.sources)
            except LookupError:
                detail = None
                excerpt = item.title
            citation_id = f"knowledge:{item.knowledge_id}"
            evidence_status = "verified" if item.eligibility.rag_eligible else "preview_unverified"
            self.evidence[citation_id] = KnowledgeEvidence(
                citation_id=citation_id,
                label=item.title,
                kind="entry" if item.eligibility.rag_eligible else "preview",
                excerpt=excerpt,
                knowledge_id=item.knowledge_id,
            )
            result: dict[str, object] = {
                "citation_id": citation_id,
                "knowledge_id": item.knowledge_id,
                "title": item.title,
                "category": item.category,
                "dimension": item.dimension,
                "excerpt": excerpt,
                "retrieval_source": retrieval_source,
                "evidence_status": evidence_status,
            }
            if isinstance(candidate, RetrievalCandidate):
                result["retrieval_score"] = round(candidate.score, 4)
            if detail is not None and retrieval_source == "fuzzy":
                result["matched_aliases"] = list(detail.aliases)
            results.append(result)
        return results

    def _fuzzy_candidates(
        self,
        query: str,
        *,
        include_preview: bool = False,
    ) -> list[tuple[RetrievalCandidate, object]]:
        entries = []
        cursor = None
        while True:
            page = self._catalog.browse(
                release_id=self.release.knowledge_release_id,
                query=None,
                category=None,
                category_id=None,
                dimension_id=None,
                cursor=cursor,
                limit=200,
            )
            entries.extend(page.entries)
            cursor = getattr(page, "next_cursor", None)
            if not cursor:
                break
        ranked: list[tuple[RetrievalCandidate, object]] = []
        for item in entries:
            if not item.eligibility.rag_eligible and not include_preview:
                continue
            try:
                detail = self._catalog.get_entry(
                    knowledge_id=item.knowledge_id,
                    release_id=self.release.knowledge_release_id,
                )
            except LookupError:
                continue
            score = fuzzy_match_score(
                query,
                title=item.title,
                aliases=tuple(detail.aliases),
                text=detail.content,
            )
            if score < 0.18:
                continue
            ranked.append(
                (
                    RetrievalCandidate(
                        citation_id=f"knowledge:{item.knowledge_id}",
                        score=score,
                        source="fuzzy",
                    ),
                    item,
                )
            )
        return sorted(ranked, key=lambda pair: (-pair[0].score, pair[0].citation_id))

    def read_knowledge_entry(self, knowledge_id: str) -> dict[str, object]:
        try:
            detail = self._catalog.get_entry(
                knowledge_id=knowledge_id,
                release_id=self.release.knowledge_release_id,
            )
        except LookupError:
            return {
                "error": "knowledge_entry_not_found",
                "knowledge_id": knowledge_id,
                "message": "当前知识库版本中没有找到这个条目。",
            }
        self._allowed_source_ids.update(source.source_id for source in detail.sources)
        citation_id = f"knowledge:{knowledge_id}"
        is_preview = not detail.summary.eligibility.rag_eligible
        self.evidence[citation_id] = KnowledgeEvidence(
            citation_id=citation_id,
            label=detail.summary.title,
            kind="preview" if is_preview else "entry",
            excerpt=_excerpt(detail.content, length=1200),
            knowledge_id=knowledge_id,
        )
        return {
            "citation_id": citation_id,
            "knowledge_id": knowledge_id,
            "title": detail.summary.title,
            "content": detail.content,
            "aliases": detail.aliases,
            "source_ids": [source.source_id for source in detail.sources],
            "evidence_status": "preview_unverified" if is_preview else "verified",
        }

    def read_sources(self, source_ids: list[str]) -> list[dict[str, object]]:
        requested = [
            source_id for source_id in source_ids[:8] if source_id in self._allowed_source_ids
        ]
        sources = self._catalog.get_sources(
            source_ids=tuple(requested),
            release_id=self.release.knowledge_release_id,
        )
        values: list[dict[str, object]] = []
        for source in sources:
            citation_id = f"source:{source.source_id}"
            self.evidence[citation_id] = KnowledgeEvidence(
                citation_id=citation_id,
                label=source.title,
                kind="source",
                excerpt=source.use_boundary,
                source_id=source.source_id,
            )
            values.append(
                {
                    "citation_id": citation_id,
                    "source_id": source.source_id,
                    "title": source.title,
                    "authors_or_institution": source.authors_or_institution,
                    "year": source.year,
                    "url": source.url,
                    "verification_status": source.verification_status,
                }
            )
        return values

    def browse_knowledge_directory(
        self,
        query: str | None = None,
        *,
        limit: int = 24,
    ) -> list[dict[str, object]]:
        directory = self._catalog.get_directory(release_id=self.release.knowledge_release_id)
        safe_limit = max(1, min(limit, 40))
        if query and query.strip():
            ranked_nodes = sorted(
                ((fuzzy_match_score(query, title=node.title), node) for node in directory.nodes),
                key=lambda item: (-item[0], item[1].node_id),
            )
            nodes = [node for score, node in ranked_nodes if score >= 0.18][:safe_limit]
        else:
            nodes = [node for node in directory.nodes if node.parent_node_id is None][:safe_limit]
        values: list[dict[str, object]] = []
        for node in nodes:
            citation_id = f"directory:{node.node_id}"
            self.evidence[citation_id] = KnowledgeEvidence(
                citation_id=citation_id,
                label=node.title,
                kind="directory",
                excerpt=f"{node.entry_count} 个知识条目",
            )
            value: dict[str, object] = {
                "citation_id": citation_id,
                "node_id": node.node_id,
                "title": node.title,
                "node_type": node.node_type,
                "parent_node_id": node.parent_node_id,
                "entry_count": node.entry_count,
                "entries": self._directory_entry_previews(node, limit=6)
                if query and query.strip()
                else [],
            }
            values.append(value)
        return values

    def _directory_entry_previews(self, node, *, limit: int) -> list[dict[str, object]]:
        browse = getattr(self._catalog, "browse", None)
        if not callable(browse):
            return []
        node_type = getattr(node.node_type, "value", node.node_type)
        page = browse(
            release_id=self.release.knowledge_release_id,
            query=None,
            category=None,
            category_id=node.node_id if node_type == "category" else None,
            dimension_id=node.node_id if node_type == "dimension" else None,
            cursor=None,
            limit=max(1, min(limit, 8)),
        )
        previews: list[dict[str, object]] = []
        for item in page.entries:
            try:
                detail = self._catalog.get_entry(
                    knowledge_id=item.knowledge_id,
                    release_id=self.release.knowledge_release_id,
                )
            except LookupError:
                continue
            is_preview = not item.eligibility.rag_eligible
            citation_id = f"knowledge:{item.knowledge_id}"
            self.evidence[citation_id] = KnowledgeEvidence(
                citation_id=citation_id,
                label=item.title,
                kind="preview" if is_preview else "entry",
                excerpt=_excerpt(detail.content),
                knowledge_id=item.knowledge_id,
            )
            previews.append(
                {
                    "knowledge_id": item.knowledge_id,
                    "title": item.title,
                    "excerpt": _excerpt(detail.content),
                    "evidence_status": "preview_unverified" if is_preview else "verified",
                }
            )
        return previews


def _excerpt(content: str, *, length: int = 480) -> str:
    plain = re.sub(r"(^|\s)[#>*_`]+", r"\1", content)
    plain = re.sub(r"\[[^\]]*\]\([^)]*\)", "", plain)
    normalized = " ".join(plain.split())
    return normalized if len(normalized) <= length else f"{normalized[:length].rstrip()}…"


def _query_candidates(query: str) -> list[str]:
    normalized = query.strip()
    candidates = [normalized] if normalized else []
    for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", normalized):
        if phrase not in candidates:
            candidates.append(phrase)
        for index in range(len(phrase) - 3):
            fragment = phrase[index : index + 4]
            if fragment not in candidates:
                candidates.append(fragment)
    return candidates


def _rank_page_items(query: str, items) -> list[tuple[RetrievalCandidate, object]]:
    """Rank FTS pages before the result limit is applied.

    A catalog query may return several pages for progressively shorter query
    fragments.  Ranking the union here prevents an early, broad fragment from
    hiding a later exact concept.  The tuple shape is intentionally the same
    as future dense/reranked candidates, so this remains a replaceable first
    stage rather than a second retrieval API.
    """

    best: dict[str, tuple[RetrievalCandidate, object]] = {}
    for item in items:
        score = lexical_relevance_score(
            query,
            title=item.title,
            text=" ".join(
                value
                for value in (getattr(item, "category", ""), getattr(item, "dimension", ""))
                if value
            ),
        )
        if score < 0.18:
            continue
        candidate = RetrievalCandidate(
            citation_id=f"knowledge:{item.knowledge_id}",
            score=score,
            source="lexical",
        )
        current = best.get(item.knowledge_id)
        if current is None or candidate.score > current[0].score:
            best[item.knowledge_id] = (candidate, item)
    return sorted(
        best.values(),
        key=lambda pair: (-pair[0].score, pair[0].citation_id),
    )
