import json
from dataclasses import asdict
from enum import Enum
from hashlib import sha256
from uuid import UUID

from qunxue_api.modules.knowledge_catalog import KnowledgeCatalog, KnowledgeReleaseRef
from qunxue_api.modules.research_intake import ConfirmedPhenomenonSnapshot
from qunxue_api.modules.theory_matching import (
    EvidenceBundleSnapshot,
    EvidenceItemSnapshot,
)

_PAGE_SIZE = 100


class CatalogTheoryEvidenceSource:
    """Temporary stable recall over the versioned KnowledgeCatalog port."""

    def __init__(self, catalog: KnowledgeCatalog) -> None:
        self._catalog = catalog

    def retrieve(
        self,
        *,
        phenomenon: ConfirmedPhenomenonSnapshot,
        release: KnowledgeReleaseRef,
    ) -> EvidenceBundleSnapshot:
        cursor: str | None = None
        selected_profiles = []
        evidence_items = []
        seen_theory_ids: set[str] = set()
        while True:
            page = self._catalog.browse(
                release_id=release.knowledge_release_id,
                query=None,
                category=None,
                category_id=None,
                dimension_id=None,
                cursor=cursor,
                limit=_PAGE_SIZE,
            )
            for entry in page.entries:
                if not entry.eligibility.match_eligible:
                    continue
                detail = self._catalog.get_entry(
                    knowledge_id=entry.knowledge_id,
                    release_id=release.knowledge_release_id,
                )
                profile = detail.theory_profile
                if (
                    detail.release != release
                    or profile is None
                    or not profile.match_eligible
                    or entry.knowledge_id not in profile.related_knowledge_ids
                    or profile.theory_id in seen_theory_ids
                ):
                    continue
                loaded_sources = self._catalog.get_sources(
                    source_ids=profile.source_ids,
                    release_id=release.knowledge_release_id,
                )
                source_by_id = {source.source_id: source for source in loaded_sources}
                if not profile.source_ids or any(
                    source_id not in source_by_id for source_id in profile.source_ids
                ):
                    continue
                ordered_sources = tuple(
                    source_by_id[source_id] for source_id in profile.source_ids
                )
                claims = profile.core_propositions or (profile.title,)
                for index, claim in enumerate(claims):
                    source = ordered_sources[index % len(ordered_sources)]
                    evidence_items.append(
                        EvidenceItemSnapshot(
                            evidence_ref_id=(
                                f"evidence:{profile.theory_id}:v{profile.content_version}:"
                                f"claim-{index + 1}:{source.source_id}"
                            ),
                            claim=claim,
                            excerpt=None,
                            locator=source.locator,
                            source=source,
                            verification_status=source.verification_status,
                            use_boundary=source.use_boundary,
                        )
                    )
                selected_profiles.append(profile)
                seen_theory_ids.add(profile.theory_id)
                if len(selected_profiles) == 5:
                    break
            if len(selected_profiles) == 5:
                break
            if page.next_cursor is None:
                break
            cursor = page.next_cursor

        payload = json.dumps(
            {
                "knowledge_release_id": release.knowledge_release_id,
                "release_content_hash": release.content_hash,
                "phenomenon_content_hash": phenomenon.content_hash,
                "theory_profiles": _json_value(selected_profiles),
                "evidence_items": _json_value(evidence_items),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        content_hash = f"sha256:{sha256(payload.encode()).hexdigest()}"
        return EvidenceBundleSnapshot(
            evidence_bundle_id=f"evidence-bundle:{content_hash.removeprefix('sha256:')[:24]}",
            version=1,
            content_hash=content_hash,
            release=release,
            theory_profiles=tuple(selected_profiles),
            evidence_items=tuple(evidence_items),
        )


def _json_value(value: object) -> object:
    if hasattr(value, "__dataclass_fields__"):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    return value
