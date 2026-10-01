"""Read-only reading priorities, using the frontier public visibility gate."""

from datetime import date

from qunxue_api.modules.frontier_knowledge import (
    FrontierService,
    FrontierStore,
    assess_record_value,
)


class FrontierReadingPriority:
    def __init__(self, store: FrontierStore, frontier: FrontierService):
        self.store = store
        self.frontier = frontier

    def for_record(self, record_id: str, *, as_of: date | None = None) -> dict:
        record = self.frontier.record(record_id, as_of=as_of)
        return assess_record_value(record, self.store.get_snapshot(record["snapshot_id"]))

    def search(
        self,
        *,
        q: str = "",
        readiness: str | None = None,
        assessment_status: str | None = None,
        min_academic_value: float | None = None,
        as_of: date | None = None,
        offset: int = 0,
        limit: int = 24,
    ) -> dict:
        items, source_offset = [], 0
        while True:
            page = self.frontier.search(q=q, as_of=as_of, offset=source_offset, limit=200)
            for record in page["items"]:
                try:
                    item = self.for_record(record["id"], as_of=as_of)
                except LookupError:
                    continue
                if readiness and item["reading_priority"] != readiness:
                    continue
                if assessment_status and item["assessment"]["status"] != assessment_status:
                    continue
                score = item["assessment"]["academic_value"]
                if min_academic_value is not None and (score is None or score < min_academic_value):
                    continue
                items.append(item)
            if page["next_offset"] is None:
                break
            source_offset = page["next_offset"]
        ranks = {"passage_supported": 0, "abstract_supported": 1, "metadata_only": 2}
        items.sort(
            key=lambda item: (
                ranks[item["reading_priority"]],
                -len(item["supported_fields"]),
                item["record_id"],
            )
        )
        total = len(items)
        return {
            "items": items[offset : offset + limit],
            "total": total,
            "offset": offset,
            "limit": limit,
            "next_offset": offset + limit if offset + limit < total else None,
            "as_of": page["as_of"],
            "sort_basis": "evidence_readiness_then_supported_field_count_then_record_id",
        }
