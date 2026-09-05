import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from qunxue_api.adapters.retrieval.errors import RetrievalPipelineUnavailable
from qunxue_api.modules.agent_conversation import (
    AgentEvidence,
    apply_research_map_patch,
    empty_research_map,
    normalize_research_map_patch,
)
from qunxue_api.modules.knowledge_catalog import KnowledgeCatalog, KnowledgeUsePurpose

from .retrieval import fuzzy_match_score

KnowledgeEvidence = AgentEvidence

if TYPE_CHECKING:
    from qunxue_api.adapters.retrieval.hybrid import HybridRetrievalResult


class KnowledgeRetriever(Protocol):
    def search(
        self,
        *,
        query: str,
        knowledge_release_id: str,
        release_content_hash: str,
        document_kind: str | None,
        limit: int,
    ) -> "HybridRetrievalResult": ...


class WebResearchClient(Protocol):
    def search(self, query: str, *, limit: int = 5) -> list[dict[str, str]]: ...

    def read(self, url: str) -> dict[str, str]: ...


class KnowledgeToolRegistry:
    """The only capabilities exposed to the natural-language Agent in phase one."""

    def __init__(
        self,
        catalog: KnowledgeCatalog,
        *,
        retriever: KnowledgeRetriever | None = None,
        web_research: WebResearchClient | None = None,
    ) -> None:
        self._catalog = catalog
        self._retriever = retriever
        self._web_research = web_research
        # Keep an installed theory release and its index usable. Uploads are already
        # reviewed, so the optional theory bundle must never gate ordinary Agent use.
        try:
            self.release = catalog.current_release(purpose=KnowledgeUsePurpose.MATCH)
        except LookupError:
            self.release = catalog.current_release(purpose=KnowledgeUsePurpose.BROWSE)
        require_ready = getattr(retriever, "require_ready_manifest", None)
        if callable(require_ready):
            try:
                require_ready(
                    knowledge_release_id=self.release.knowledge_release_id,
                    release_content_hash=self.release.content_hash,
                )
            except RetrievalPipelineUnavailable:
                self._retriever = None
        if self._retriever is None:
            from qunxue_api.adapters.theory_evidence import CatalogTheoryLexicalRetriever

            self._retriever = CatalogTheoryLexicalRetriever(catalog)
        self.evidence: dict[str, KnowledgeEvidence] = {}
        self.selected_evidence_ids: tuple[str, ...] = ()
        self._allowed_source_ids: set[str] = set()
        self.research_map_enabled = False
        self.deep_research_enabled = False
        self.web_search_enabled = False
        self.web_read_enabled = web_research is not None
        self._web_queries: set[str] = set()
        self.research_map: dict[str, object] = empty_research_map()

    def agent_route_context(self) -> Mapping[str, UUID | None]:
        """Expose only safe correlation identifiers for model-attempt routing."""

        return MappingProxyType(
            {
                "user_id": getattr(self, "_user_id", None),
                "task_id": getattr(self, "_task_id", None),
                "agent_run_id": getattr(self, "_agent_run_id", None),
            }
        )

    def select_evidence(self, citation_ids: Sequence[str]) -> tuple[str, ...]:
        """Bind this turn's source cards to a validated structured evidence set."""

        selected = tuple(dict.fromkeys(str(value) for value in citation_ids))
        if any(citation_id not in self.evidence for citation_id in selected):
            raise ValueError("selected evidence is outside this turn's retrieved closed set")
        self.selected_evidence_ids = selected
        return selected

    def enable_web_search(self) -> None:
        self.web_search_enabled = self._web_research is not None

    def enable_deep_research(self) -> None:
        """Select the long-running research execution policy for this turn."""

        self.deep_research_enabled = True

    def search_web(
        self, query: str, *, limit: int = 5
    ) -> list[dict[str, object]] | dict[str, object]:
        if not self.web_search_enabled or self._web_research is None:
            raise ValueError("联网搜索未开启")
        safe_query = query.strip()
        if not safe_query:
            raise ValueError("联网搜索词不能为空")
        query_key = " ".join(safe_query.casefold().split())
        if query_key in self._web_queries:
            return {
                "error": "duplicate_web_query",
                "message": "本轮已经搜索过相同问题，请直接使用已有网页证据。",
                "retryable": False,
            }
        self._web_queries.add(query_key)
        raw_results = self._web_research.search(safe_query, limit=max(1, min(limit, 50)))
        results: list[dict[str, object]] = []
        for item in raw_results:
            url = item.get("url", "").strip()
            title = item.get("title", "").strip()
            if not url.startswith(("https://", "http://")) or not title:
                continue
            excerpt = item.get("snippet", "").strip()
            citation_id = f"web:{url}"
            self.evidence[citation_id] = AgentEvidence(
                citation_id=citation_id,
                label=title,
                kind="source",
                excerpt=excerpt,
                source_id=url,
                source_kind="web",
            )
            results.append(
                {
                    "citation_id": citation_id,
                    "title": title,
                    "url": url,
                    "excerpt": excerpt,
                    "source_kind": "web",
                    "evidence_status": "retrieved",
                }
            )
        return results

    def read_web_page(self, url: str) -> dict[str, object]:
        if self._web_research is None:
            raise ValueError("网页读取服务不可用")
        from qunxue_api.adapters.research_agent.web_research import _ensure_public_url

        _ensure_public_url(url)
        page = self._web_research.read(url)
        content = page.get("content", "").strip()
        title = page.get("title", "").strip()
        citation_id = f"web:{url}"
        existing = self.evidence.get(citation_id) or AgentEvidence(
            citation_id=citation_id, label=title or url, kind="source",
            excerpt="", source_id=url, source_kind="web",
        )
        if content:
            self.evidence[citation_id] = replace(
                existing,
                label=title or existing.label,
                excerpt=content,
            )
        return {
            "citation_id": citation_id,
            "title": title or existing.label,
            "url": url,
            "content": content,
            "source_kind": "web",
            "evidence_status": "read",
        }

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
        if self._retriever is None:
            raise RetrievalPipelineUnavailable("release-bound hybrid retriever is not configured")
        result = self._retriever.search(
            query=query,
            knowledge_release_id=self.release.knowledge_release_id,
            release_content_hash=self.release.content_hash,
            document_kind=None,
            limit=max(1, min(limit, 50)),
        )
        values: list[dict[str, object]] = []
        seen_knowledge_ids: set[str] = set()
        for hit in result.hits:
            chunk = hit.chunk
            if chunk.knowledge_id is None or chunk.knowledge_id in seen_knowledge_ids:
                continue
            seen_knowledge_ids.add(chunk.knowledge_id)
            try:
                detail = self._catalog.get_entry(
                    knowledge_id=chunk.knowledge_id,
                    release_id=self.release.knowledge_release_id,
                )
            except LookupError as error:
                raise RetrievalPipelineUnavailable(
                    "retrieval evidence cannot be restored from the pinned release"
                ) from error
            if detail.summary.content_version != chunk.content_version:
                raise RetrievalPipelineUnavailable(
                    "retrieval evidence content version does not match the pinned release"
                )
            sources_by_id = {source.source_id: source for source in detail.sources}
            if any(source_id not in sources_by_id for source_id in chunk.source_ids):
                raise RetrievalPipelineUnavailable(
                    "retrieval evidence source cannot be restored from the pinned release"
                )
            source_citation_ids = []
            for source_id in chunk.source_ids:
                source = sources_by_id[source_id]
                source_citation_id = f"source:{source.source_id}"
                source_citation_ids.append(source_citation_id)
                self._allowed_source_ids.add(source.source_id)
                self.evidence[source_citation_id] = KnowledgeEvidence(
                    citation_id=source_citation_id,
                    label=source.title,
                    kind="source",
                    excerpt=source.use_boundary,
                    source_id=source.source_id,
                )
            citation_id = f"retrieval:{chunk.chunk_id}"
            self.evidence[citation_id] = KnowledgeEvidence(
                citation_id=citation_id,
                label=chunk.title,
                kind="theory" if chunk.document_kind == "theory_profile" else "entry",
                excerpt=chunk.text,
                knowledge_id=chunk.knowledge_id,
            )
            values.append(
                {
                    "citation_id": citation_id,
                    "knowledge_id": chunk.knowledge_id,
                    "theory_id": chunk.theory_id,
                    "chunk_id": chunk.chunk_id,
                    "title": chunk.title,
                    "excerpt": chunk.text,
                    "retrieval_index_id": result.retrieval_index_id,
                    "retrieval_mode": result.mode,
                    "retrieval_sources": list(hit.retrieval_sources),
                    "rerank_score": hit.rerank_score,
                    "embedding_model": result.embedding_model,
                    "reranker_model": result.reranker_model,
                    "source_citation_ids": source_citation_ids,
                    "evidence_status": "verified",
                }
            )
        return values

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
        self.evidence[citation_id] = KnowledgeEvidence(
            citation_id=citation_id,
            label=detail.summary.title,
            kind="entry",
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
            "evidence_status": "verified",
        }

    def read_sources(self, source_ids: list[str]) -> list[dict[str, object]]:
        requested = [
            source_id for source_id in source_ids if source_id in self._allowed_source_ids
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
            limit=max(1, min(limit, 50)),
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
            citation_id = f"knowledge:{item.knowledge_id}"
            self.evidence[citation_id] = KnowledgeEvidence(
                citation_id=citation_id,
                label=item.title,
                kind="entry",
                excerpt=_excerpt(detail.content),
                knowledge_id=item.knowledge_id,
            )
            previews.append(
                {
                    "knowledge_id": item.knowledge_id,
                    "title": item.title,
                    "excerpt": _excerpt(detail.content),
                    "evidence_status": "verified",
                }
            )
        return previews


def _excerpt(content: str, *, length: int = 480) -> str:
    plain = re.sub(r"(^|\s)[#>*_`]+", r"\1", content)
    plain = re.sub(r"\[[^\]]*\]\([^)]*\)", "", plain)
    normalized = " ".join(plain.split())
    return normalized if len(normalized) <= length else f"{normalized[:length].rstrip()}…"
