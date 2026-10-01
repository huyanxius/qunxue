"""Read-only evidence-to-catalog suggestions through public module boundaries."""

from datetime import date

from qunxue_api.modules.frontier_knowledge import FrontierService, FrontierStore, reading_basis
from qunxue_api.modules.knowledge_catalog import KnowledgeCatalog, KnowledgeUsePurpose


class FrontierKnowledgeLinks:
    def __init__(
        self,
        store: FrontierStore,
        catalog: KnowledgeCatalog,
        frontier: FrontierService | None = None,
    ):
        self.store = store
        self.catalog = catalog
        self.frontier = frontier or FrontierService(store)

    def for_record(self, record_id: str, *, as_of: date | None = None) -> dict:
        record = self.frontier.record(record_id, as_of=as_of)
        release = self.catalog.existing_release(purpose=KnowledgeUsePurpose.BROWSE)
        result = {
            "record_id": record_id,
            "record_version": record["version"],
            "record_content_hash": record["content_hash"],
            "knowledge_release_id": release.knowledge_release_id if release else None,
            "knowledge_release_hash": release.content_hash if release else None,
            "knowledge_release_level": release.level.value if release else None,
            "matches": [],
            "status": "no_release",
            "match_basis": "topic_lexical_retrieval",
            "relationship": "reading_lead",
            "limitations": ["主题词检索只提供阅读线索，不证明理论适用、学术贡献或知识更新必要性。"],
        }
        if release is None:
            return result
        topics = sorted(
            {
                topic.strip()
                for topic in record.get("topics", [])
                if isinstance(topic, str) and topic.strip() and len(topic.strip()) <= 100
            }
        )[:6]
        if not topics:
            result["status"] = "no_topics"
            return result
        matches = {}
        for topic in topics:
            page = self.catalog.browse(
                release_id=release.knowledge_release_id,
                query=topic,
                category=None,
                category_id=None,
                dimension_id=None,
                cursor=None,
                limit=20,
            )
            # A release mismatch is an invalid handoff, never a cross-version link.
            if page.release != release:
                raise LookupError("knowledge release mismatch")
            for entry in page.entries:
                if not entry.eligibility.browse_eligible:
                    continue
                item = matches.setdefault(
                    entry.knowledge_id,
                    {
                        "knowledge_id": entry.knowledge_id,
                        "title": entry.title,
                        "content_version": entry.content_version,
                        "matched_topics": [],
                    },
                )
                item["matched_topics"].append(topic)
        result["matches"] = sorted(
            matches.values(), key=lambda item: (-len(item["matched_topics"]), item["knowledge_id"])
        )[:10]
        result["status"] = "ready" if result["matches"] else "no_matches"
        snapshot = self.store.get_snapshot(record["snapshot_id"])
        if result["matches"] and not reading_basis(record, snapshot):
            result["status"] = "low_evidence"
            result["limitations"].append(
                "当前文献没有可定位的正文或摘要证据，仅凭主题元数据提供线索。"
            )
        return result
