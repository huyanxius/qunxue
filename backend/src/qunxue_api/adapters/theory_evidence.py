import json
from dataclasses import asdict
from enum import Enum
from hashlib import sha256
from typing import Protocol
from uuid import UUID

from qunxue_api.adapters.retrieval.errors import RetrievalPipelineUnavailable
from qunxue_api.adapters.retrieval.hybrid import HybridRetrievalResult
from qunxue_api.modules.knowledge_catalog import (
    KnowledgeCatalog,
    KnowledgeReleaseLevel,
    KnowledgeReleaseRef,
    SourceRecordSnapshot,
    SourceVerificationStatus,
)
from qunxue_api.modules.research_intake import (
    ConfirmedPhenomenonSnapshot,
    PhenomenonEvidenceVerificationStatus,
)
from qunxue_api.modules.theory_matching import (
    EvidenceBundleSnapshot,
    EvidenceItemSnapshot,
    RetrievalProvenanceSnapshot,
)


class TheoryProfileRetriever(Protocol):
    def search(
        self,
        *,
        query: str,
        knowledge_release_id: str,
        release_content_hash: str,
        document_kind: str,
        limit: int,
    ) -> HybridRetrievalResult: ...


class CatalogTheoryEvidenceSource:
    """Stable recall over one audited final release pinned to a match run."""

    def __init__(
        self,
        catalog: KnowledgeCatalog,
        *,
        retriever: TheoryProfileRetriever | None = None,
    ) -> None:
        self._catalog = catalog
        self._retriever = retriever

    def retrieve(
        self,
        *,
        phenomenon: ConfirmedPhenomenonSnapshot,
        release: KnowledgeReleaseRef,
    ) -> EvidenceBundleSnapshot:
        if release.level is not KnowledgeReleaseLevel.FINAL:
            raise ValueError("theory recall requires a final MATCH knowledge release")

        profiles = self._catalog.list_match_profiles(
            release_id=release.knowledge_release_id
        )
        query = _phenomenon_retrieval_query(phenomenon)
        selected_profiles, retrieval = self._select_profiles(
            profiles=profiles,
            query=query,
            release=release,
        )
        evidence_items = []
        for profile in selected_profiles:
            loaded_sources = self._catalog.get_sources(
                source_ids=profile.source_ids,
                release_id=release.knowledge_release_id,
            )
            source_by_id = {source.source_id: source for source in loaded_sources}
            if not profile.source_ids or any(
                source_id not in source_by_id
                or source_by_id[source_id].verification_status
                is not SourceVerificationStatus.VERIFIED
                or not source_by_id[source_id].locator
                or not source_by_id[source_id].locator.strip()
                for source_id in profile.source_ids
            ):
                raise ValueError(
                    f"theory {profile.theory_id} requires a verified source with a locator"
                )
            ordered_sources = tuple(source_by_id[source_id] for source_id in profile.source_ids)
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
        used_evidence_ids = {item.evidence_ref_id for item in evidence_items}
        for item in phenomenon.evidence_refs:
            if item.evidence_ref_id in used_evidence_ids:
                raise ValueError(
                    f"phenomenon evidence id conflicts with theory evidence: {item.evidence_ref_id}"
                )
            used_evidence_ids.add(item.evidence_ref_id)
            verification_status = (
                SourceVerificationStatus.VERIFIED
                if item.verification_status
                is PhenomenonEvidenceVerificationStatus.VERIFIED
                else SourceVerificationStatus.PENDING
            )
            evidence_items.append(
                EvidenceItemSnapshot(
                    evidence_ref_id=item.evidence_ref_id,
                    claim=item.source_description or "已确认现象材料",
                    excerpt=item.excerpt,
                    locator=item.locator,
                    source=SourceRecordSnapshot(
                        source_id=item.source_ref_id,
                        source_type="confirmed_phenomenon_evidence",
                        title=item.source_description or item.source_ref_id,
                        authors_or_institution=(),
                        year=None,
                        publication=None,
                        locator=item.locator,
                        url=None,
                        verification_status=verification_status,
                        use_boundary=item.use_boundary,
                    ),
                    verification_status=verification_status,
                    use_boundary=item.use_boundary,
                )
            )

        payload = json.dumps(
            {
                "knowledge_release_id": release.knowledge_release_id,
                "release_content_hash": release.content_hash,
                "phenomenon_content_hash": phenomenon.content_hash,
                "retrieval": _json_value(retrieval),
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
            retrieval=retrieval,
        )

    def _select_profiles(
        self,
        *,
        profiles: tuple,
        query: str,
        release: KnowledgeReleaseRef,
    ) -> tuple[list, RetrievalProvenanceSnapshot]:
        by_id = {profile.theory_id: profile for profile in profiles}
        if self._retriever is None:
            raise RetrievalPipelineUnavailable("release-bound hybrid retriever is required")
        result = self._retriever.search(
            query=query,
            knowledge_release_id=release.knowledge_release_id,
            release_content_hash=release.content_hash,
            document_kind="theory_profile",
            limit=5,
        )
        chunk_ids = tuple(hit.chunk.chunk_id for hit in result.hits)
        theory_ids = tuple(
            hit.chunk.theory_id for hit in result.hits if hit.chunk.theory_id is not None
        )
        unknown_ids = tuple(theory_id for theory_id in theory_ids if theory_id not in by_id)
        if unknown_ids:
            raise ValueError("retrieval index returned a theory outside the pinned release")
        selected = [by_id[theory_id] for theory_id in theory_ids]
        return selected, RetrievalProvenanceSnapshot(
            retrieval_index_id=result.retrieval_index_id,
            mode=result.mode,
            embedding_model=result.embedding_model,
            reranker_model=result.reranker_model,
            degraded_reason=result.degraded_reason,
            retrieved_chunk_ids=chunk_ids,
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


def _phenomenon_retrieval_query(phenomenon: ConfirmedPhenomenonSnapshot) -> str:
    values = (
        phenomenon.phenomenon,
        phenomenon.research_intent,
        phenomenon.context,
        *(item.excerpt for item in phenomenon.evidence_refs if item.excerpt),
    )
    return "\n".join(value.strip() for value in values if value and value.strip())
