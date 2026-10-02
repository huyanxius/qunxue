"""Deterministic lexical retrieval and explainable, date-qualified topic metrics."""

from datetime import date, timedelta

from .analysis import aggregate_topics
from .calendar import publication_calendar
from .domain import content_hash, frontier_today
from .overview import overview_basis
from .overview_stats import corpus_statistics, visible_corpus_records
from .period_report import period_report
from .periods import PublicationInterval, available_as_of, browse_visible
from .ports import FrontierStore
from .read_projection import record_summary
from .series import topic_series


def _brief_references_visible(value: object, allowed: set[str]) -> bool:
    if isinstance(value, list):
        return all(_brief_references_visible(item, allowed) for item in value)
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "evidence_record_ids":
                if not isinstance(item, list) or any(
                    not isinstance(ref, str) or ref not in allowed for ref in item
                ):
                    return False
            elif (
                key == "record_id"
                and (not isinstance(item, str) or item not in allowed)
                or not _brief_references_visible(item, allowed)
            ):
                return False
    return True


class FrontierService:
    def __init__(self, store: FrontierStore, vector_retriever=None):
        self.store = store
        self.vector_retriever = vector_retriever

    def record(self, record_id: str, *, as_of: date | None = None) -> dict:
        record = self.store.get_record(record_id)
        if (
            not record
            or not browse_visible(record)
            or not available_as_of(record, as_of or frontier_today())
        ):
            raise LookupError("Frontier record not found")
        return record

    def calendar(self, *, year: int, as_of: date | None = None) -> dict:
        cutoff = as_of or frontier_today()
        return publication_calendar(
            [
                r
                for r in self.store.list_records()
                if browse_visible(r) and available_as_of(r, cutoff)
            ],
            year=year,
            as_of=cutoff,
        )

    def period_report(
        self,
        *,
        previous_start: date,
        previous_end: date,
        current_start: date,
        current_end: date,
        topic_key: str,
        as_of: date | None = None,
    ) -> dict:
        previous = PublicationInterval(previous_start, previous_end)
        current = PublicationInterval(current_start, current_end)
        if previous.end >= current.start:
            raise ValueError("comparison periods must not overlap")
        return period_report(
            self.store.list_records(),
            self.store.list_issue_coverage(),
            previous=previous,
            current=current,
            topic_key=topic_key,
            as_of=as_of or frontier_today(),
        )

    def overview(self, *, as_of: date | None = None) -> dict:
        as_of = as_of or frontier_today()
        records = [
            r
            for r in visible_corpus_records(self.store.list_records())
            if browse_visible(r) and available_as_of(r, as_of)
        ]
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
        source_name: str | None = None,
        topic_id: str | None = None,
        since_days: int | None = None,
        material_type: str | None = None,
        limit: int = 24,
        offset: int = 0,
        summaries: bool = False,
        focus: bool = False,
        record_ids: list[str] | None = None,
        as_of: date | None = None,
    ) -> dict:
        as_of = as_of or frontier_today()
        sql_search = getattr(self.store, "search_records", None)
        dense_ready = q and self.vector_retriever and self.vector_retriever.status == "ready"
        if sql_search and not dense_ready:
            return sql_search(
                q=q,
                stream=stream,
                source_id=source_id,
                source_name=source_name,
                topic_id=topic_id,
                since_days=since_days,
                material_type=material_type,
                limit=limit,
                offset=offset,
                as_of=as_of,
                summaries=summaries,
                focus=focus,
                record_ids=record_ids,
            )
        records = [
            r for r in self.store.list_records() if browse_visible(r) and available_as_of(r, as_of)
        ]
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
            if source_name and record["source_name"] != source_name:
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
        if record_ids is not None:
            deduped = [r for r in deduped if r["id"] in record_ids]
        if summaries:
            deduped.sort(key=lambda r: r["id"])
            deduped.sort(
                key=lambda r: r.get("published_at") or r.get("source_published_at") or "",
                reverse=True,
            )
        if focus:
            deduped = [
                r
                for r in deduped
                if r.get("research_question", "")
                and any((text or "").strip() for text in r.get("findings") or [])
                and r["verification_status"] in {"lead_only", "verified_frontier"}
            ]
        total = len(deduped)
        return {
            "items": [
                record_summary(r) if summaries else r for r in deduped[offset : offset + limit]
            ],
            "total": total,
            "offset": offset,
            "limit": limit,
            "next_offset": offset + limit if offset + limit < total else None,
            "as_of": as_of.isoformat(),
            "search_mode": "lexical_dense_rrf" if dense else "lexical",
            "sort_basis": "publication_date_or_source_page_date_desc_then_id_asc"
            if summaries
            else "source_page_date_desc_then_id_desc",
            "date_filter_basis": "exact_publication_date_only",
        }

    def topics(
        self, *, as_of: date | None = None, detail: bool = True, topic_id: str | None = None
    ) -> list[dict]:
        as_of = as_of or frontier_today()
        visible = [
            r for r in self.store.list_records() if browse_visible(r) and available_as_of(r, as_of)
        ]
        # Legacy rolling day counts describe samples. Only the period report can
        # establish a covered fixed cohort from actual ledgers.
        coverage_start = None
        topics = aggregate_topics(visible, as_of)
        record_by_id = {r["id"]: r for r in visible}
        briefs = {f"{b['topic_key']}-{b['stream']}": b for b in self.store.list_briefs()}
        sources = self.store.list_sources()
        issue_coverage = self.store.list_issue_coverage()
        if topic_id:
            topics = [topic for topic in topics if topic["id"] == topic_id]
        source_order = (
            sorted(
                visible, key=lambda r: (r.get("source_published_at") or "", r["id"]), reverse=True
            )
            if not detail
            else []
        )
        for topic in topics:
            topic.update(topic_series(topic, visible, sources, issue_coverage, as_of))
            if coverage_start is None:
                topic["reasons"].append(
                    "本批为人工或定额采样，未证明连续完整覆盖；数量仅描述收录样本"
                )
            brief = briefs.get(topic["id"])
            if brief:
                ids = brief.get("evidence_record_ids", [])
                valid = (
                    isinstance(ids, list)
                    and bool(ids)
                    and all(isinstance(i, str) and i in topic["record_ids"] for i in ids)
                    and _brief_references_visible(brief, set(ids))
                )
                digest = (
                    content_hash(sorted((i, record_by_id[i].get("content_hash")) for i in set(ids)))
                    if valid
                    else None
                )
                if not valid or digest != brief.get("basis_content_hash"):
                    brief = None
            topic["editorial_brief"] = brief
            topic["research_brief"] = brief.get("research_brief") if brief else None
            if brief:
                topic["summary"] = brief["summary"]
                topic["summary_method"] = brief["generated_by"]
            if not detail:
                member_ids = set(topic["record_ids"])
                representative = next((r for r in source_order if r["id"] in member_ids), None)
                if not brief and representative:
                    topic["summary"] = (
                        representative.get("research_question")
                        or representative.get("summary")
                        or ""
                    )
                topic.update(record_ids=[], evidence=[])
                topic["summary"] = topic["summary"][:280]
                # Preserve the existing row headline/sparkline, without transporting
                # its corpus-sized evidence membership or detail analysis.
                for key in ("monthly_series", "issue_series"):
                    for point in topic.get(key, []):
                        for field in list(point):
                            if field.endswith("record_ids"):
                                point[field] = []
                if brief:
                    topic["editorial_brief"] = {
                        **brief,
                        "evidence_record_ids": [],
                        "research_brief": None,
                    }
                    research = brief.get("research_brief")
                    if research:
                        topic["research_brief"] = {
                            **research,
                            "evidence_record_ids": [],
                            "priority_reads": [],
                            "consensus": [],
                            "differences": [],
                            "methods": [],
                            "research_implication": None,
                            "development": {**research["development"], "evidence_record_ids": []}
                            if research.get("development")
                            else None,
                        }
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
