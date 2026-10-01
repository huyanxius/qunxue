"""Deterministic lexical retrieval and explainable, date-qualified topic metrics."""

from datetime import date, timedelta

from .analysis import aggregate_topics
from .domain import frontier_today
from .overview import overview_basis
from .overview_stats import corpus_statistics, visible_corpus_records
from .ports import FrontierStore
from .series import topic_series


class FrontierService:
    def __init__(self, store: FrontierStore, vector_retriever=None):
        self.store = store
        self.vector_retriever = vector_retriever

    def overview(self, *, as_of: date | None = None) -> dict:
        as_of = as_of or frontier_today()
        records = visible_corpus_records(self.store.list_records())
        research = [r for r in records if r["material_type"] != "official_practice"]
        stored = self.store.get_corpus_overview()
        ready = bool(stored and stored["basis_content_hash"] == overview_basis(research))
        return {
            "as_of": as_of.isoformat(),
            "status": "ready" if ready else "stale" if stored else "not_configured",
            "overview": stored if ready else None,
            "statistics": corpus_statistics(records, aggregate_topics(records, as_of)),
        }

    def search(
        self,
        *,
        q: str = "",
        stream: str | None = None,
        source_id: str | None = None,
        topic_id: str | None = None,
        since_days: int | None = None,
        material_type: str | None = None,
        limit: int = 24,
        offset: int = 0,
        as_of: date | None = None,
    ) -> dict:
        as_of = as_of or frontier_today()
        records = [r for r in self.store.list_records() if r["eligibility"]["browse"]]
        if topic_id:
            topic = next((t for t in aggregate_topics(records, as_of) if t["id"] == topic_id), None)
            member_ids = set(topic["record_ids"] if topic else [])
            records = [r for r in records if r["id"] in member_ids]
        terms = q.casefold().split()
        dense = (
            self.vector_retriever.search(q, 200)
            if q and self.vector_retriever and self.vector_retriever.status == "ready"
            else []
        )
        dense_rank = {hit["record_id"]: i + 1 for i, hit in enumerate(dense)}
        lexical_ids = []
        eligible = []
        for record in records:
            if not record["eligibility"]["browse"]:
                continue
            record_stream = (
                "practice" if record["material_type"] == "official_practice" else "research"
            )
            if stream and stream != record_stream:
                continue
            if source_id and record["source_id"] != source_id:
                continue
            if material_type and record["material_type"] != material_type:
                continue
            if since_days is not None:
                value = record.get("published_at")
                if not value or record.get("published_at_precision") != "day":
                    continue
                try:
                    age = (as_of - date.fromisoformat(value)).days
                except ValueError:
                    continue
                if not 0 <= age < since_days:
                    continue
            haystack = " ".join(
                [
                    record["title"],
                    record.get("summary") or "",
                    record.get("research_question") or "",
                    record["source_name"],
                    *(record.get("authors") or []),
                    *record.get("topics", []),
                ]
            ).casefold()
            lexical_match = all(term in haystack for term in terms)
            if lexical_match:
                lexical_ids.append(record["id"])
            if lexical_match or record["id"] in dense_rank:
                eligible.append(record)
        # Source-page update ordering is explicit; it is never used for research trend dating.
        eligible.sort(key=lambda r: (r.get("source_published_at") or "", r["id"]), reverse=True)
        if dense:
            lexical_rank = {key: i + 1 for i, key in enumerate(lexical_ids)}

            def fused(record):
                key = record["id"]
                return (1 / (60 + lexical_rank[key]) if key in lexical_rank else 0) + (
                    1 / (60 + dense_rank[key]) if key in dense_rank else 0
                )

            eligible.sort(key=lambda r: (-fused(r), r["id"]))
        seen = set()
        deduped = []
        for record in eligible:
            if record["canonical_study_id"] not in seen:
                seen.add(record["canonical_study_id"])
                deduped.append(record)
        total = len(deduped)
        return {
            "items": deduped[offset : offset + limit],
            "total": total,
            "offset": offset,
            "limit": limit,
            "next_offset": offset + limit if offset + limit < total else None,
            "as_of": as_of.isoformat(),
            "search_mode": "lexical_dense_rrf" if dense else "lexical",
            "sort_basis": "source_page_date_desc_then_id_desc",
            "date_filter_basis": "exact_publication_date_only",
        }

    def topics(self, *, as_of: date | None = None) -> list[dict]:
        visible = [r for r in self.store.list_records() if r["eligibility"]["browse"]]
        as_of = as_of or frontier_today()
        coverage_start = self.coverage_start(as_of)
        topics = aggregate_topics(visible, as_of, coverage_start=coverage_start)
        briefs = {f"{b['topic_key']}-{b['stream']}": b for b in self.store.list_briefs()}
        sources = self.store.list_sources()
        issue_coverage = self.store.list_issue_coverage()
        for topic in topics:
            topic.update(topic_series(topic, visible, sources, issue_coverage, as_of))
            if coverage_start is None:
                topic["reasons"].append(
                    "本批为人工或定额采样，未证明连续完整覆盖；数量仅描述收录样本"
                )
            brief = briefs.get(topic["id"])
            topic["editorial_brief"] = brief
            topic["research_brief"] = brief.get("research_brief") if brief else None
            if brief:
                topic["summary"] = brief["summary"]
                topic["summary_method"] = brief["generated_by"]
        return topics

    def coverage_start(self, as_of: date) -> date | None:
        source_ids = {
            r["source_id"] for r in self.store.list_records() if r["eligibility"]["browse"]
        }
        sources = [s for s in self.store.list_sources() if s["source_id"] in source_ids]
        if len(sources) != len(source_ids) or not sources:
            return None
        starts = []
        for source in sources:
            if not source.get("coverage_complete"):
                return None
            try:
                start = date.fromisoformat(source["coverage_start"])
                end = date.fromisoformat(source["coverage_end"])
            except (KeyError, ValueError, TypeError):
                return None
            if end < as_of or start > as_of:
                return None
            starts.append(start)
        return max(starts)

    def baseline_status(self, as_of: date) -> str:
        start = self.coverage_start(as_of)
        return (
            "available"
            if start and start <= as_of - timedelta(days=179)
            else "insufficient_evidence"
        )

    def search_frontier(
        self,
        query: str,
        since_days: int | None = None,
        material_types: list[str] | None = None,
        limit: int = 10,
    ) -> dict:
        """Agent-ready split: leads never enter conclusion evidence."""
        records = self.search(q=query, since_days=since_days, limit=200)["items"]
        if material_types:
            records = [r for r in records if r["material_type"] in material_types]
        evidence, leads = [], []
        for r in records:
            hit = {
                "record_id": r["id"],
                "title": r["title"],
                "knowledge_layer": "frontier",
                "published_at": r.get("published_at"),
                "source_id": r["source_id"],
                "material_type": r["material_type"],
                "verification_status": r["verification_status"],
                "url": r["url"],
                "snapshot_id": r["snapshot_id"],
            }
            if r["eligibility"]["rag"]:
                hit["evidence"] = [e for e in r["evidence"] if e.get("snippet")]
                hit["limitation"] = r.get("editorial_caveat", "实践描述不证明因果效果")
                evidence.append(hit)
            else:
                hit["usage"] = "literature_discovery_only_not_conclusion_evidence"
                leads.append(hit)
        return {
            "evidence": evidence[:limit],
            "leads": leads[:limit],
            "mode": "lexical",
            "embedding_status": self.vector_retriever.status
            if self.vector_retriever
            else "not_configured",
        }
