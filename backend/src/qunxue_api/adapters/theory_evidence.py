import json
from collections.abc import Callable
from dataclasses import asdict
from enum import Enum
from hashlib import sha256
from typing import Protocol
from uuid import UUID

from qunxue_api.adapters.research_agent.retrieval import lexical_relevance_score
from qunxue_api.adapters.retrieval import (
    HybridRetrievalHit,
    HybridRetrievalResult,
    RetrievalChunk,
    build_knowledge_entry_chunks,
    build_theory_profile_chunks,
)
from qunxue_api.adapters.retrieval.errors import RetrievalPipelineUnavailable
from qunxue_api.modules.knowledge_catalog import (
    KnowledgeCatalog,
    KnowledgeReleaseLevel,
    KnowledgeReleaseRef,
    SourceRecordSnapshot,
    SourceVerificationStatus,
)
from qunxue_api.modules.research_analysis import ConfirmedComparisonProjection
from qunxue_api.modules.research_cycle import CycleEvidence
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


class CatalogTheoryLexicalRetriever:
    """Release-bound lexical fallback for API-key-only installations.

    Hybrid retrieval remains opt-in when its embedding and reranker credentials
    are configured.  A clean installation still needs a deterministic way to
    recall the audited catalog, so this adapter ranks the same release corpus
    without introducing another credential or silently switching to mock data.
    """

    def __init__(self, catalog: KnowledgeCatalog) -> None:
        self._catalog = catalog

    def search(
        self,
        *,
        query: str,
        knowledge_release_id: str,
        release_content_hash: str,
        document_kind: str | None,
        limit: int,
    ) -> HybridRetrievalResult:
        chunks = self._chunks(
            knowledge_release_id=knowledge_release_id,
            document_kind=document_kind,
        )
        return self._lexical_result(
            query=query,
            chunks=chunks,
            limit=limit,
            retrieval_index_id=(
                f"catalog-lexical:{knowledge_release_id}:"
                f"{release_content_hash.removeprefix('sha256:')[:16]}"
            ),
        )

    def search_chunks(
        self,
        *,
        query: str,
        chunks: tuple[RetrievalChunk, ...],
        limit: int,
        retrieval_index_id: str = "external-chunks",
    ) -> HybridRetrievalResult:
        """Rank task-scoped material blocks without an embedding credential."""

        return self._lexical_result(
            query=query,
            chunks=chunks,
            limit=limit,
            retrieval_index_id=f"{retrieval_index_id}:catalog-lexical",
        )

    @staticmethod
    def _lexical_result(
        *,
        query: str,
        chunks: tuple[RetrievalChunk, ...],
        limit: int,
        retrieval_index_id: str,
    ) -> HybridRetrievalResult:
        ranked = sorted(
            [
                (
                    lexical_relevance_score(query, title=chunk.title, text=chunk.text),
                    chunk,
                )
                for chunk in chunks
            ],
            key=lambda item: (-item[0], item[1].chunk_id),
        )
        selected = [(score, chunk) for score, chunk in ranked if score > 0][: max(1, limit)]
        # A short or unfamiliar phenomenon should still expose the audited
        # candidate set to the real judge instead of fabricating a no-match.
        if not selected:
            selected = ranked[: max(1, limit)]
        return HybridRetrievalResult(
            retrieval_index_id=retrieval_index_id,
            mode="catalog_lexical",
            embedding_model="not_configured",
            reranker_model=None,
            degraded_reason=None,
            hits=tuple(
                HybridRetrievalHit(
                    chunk=chunk,
                    fused_score=score,
                    retrieval_sources=("lexical",),
                    rerank_score=None,
                )
                for score, chunk in selected
            ),
        )

    def _chunks(
        self,
        *,
        knowledge_release_id: str,
        document_kind: str | None,
    ) -> tuple[RetrievalChunk, ...]:
        if document_kind == "theory_profile":
            return build_theory_profile_chunks(
                self._catalog.list_match_profiles(release_id=knowledge_release_id)
            )
        if document_kind == "knowledge_entry":
            return build_knowledge_entry_chunks(
                self._catalog.list_rag_entries(release_id=knowledge_release_id)
            )
        if document_kind is None:
            return tuple(
                sorted(
                    (
                        *build_knowledge_entry_chunks(
                            self._catalog.list_rag_entries(release_id=knowledge_release_id)
                        ),
                        *build_theory_profile_chunks(
                            self._catalog.list_match_profiles(release_id=knowledge_release_id)
                        ),
                    ),
                    key=lambda item: item.chunk_id,
                )
            )
        return ()


class CatalogTheoryEvidenceSource:
    """Stable recall over one audited final release pinned to a match run."""

    def __init__(
        self,
        catalog: KnowledgeCatalog,
        *,
        retriever: TheoryProfileRetriever | None = None,
        get_confirmed_comparison_projection: (
            Callable[..., ConfirmedComparisonProjection] | None
        ) = None,
        get_confirmed_analysis_evidence: (Callable[..., tuple[CycleEvidence, ...]] | None) = None,
    ) -> None:
        self._catalog = catalog
        self._retriever = retriever
        self._get_confirmed_comparison_projection = get_confirmed_comparison_projection
        self._get_confirmed_analysis_evidence = get_confirmed_analysis_evidence

    def retrieve(
        self,
        *,
        user_id: UUID | None = None,
        phenomenon: ConfirmedPhenomenonSnapshot,
        release: KnowledgeReleaseRef,
    ) -> EvidenceBundleSnapshot:
        if release.level is not KnowledgeReleaseLevel.FINAL:
            raise ValueError("theory recall requires a final MATCH knowledge release")

        profiles = self._catalog.list_match_profiles(release_id=release.knowledge_release_id)
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
                if item.verification_status is PhenomenonEvidenceVerificationStatus.VERIFIED
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

        if self._get_confirmed_analysis_evidence is not None:
            if user_id is None:
                raise ValueError("personal analysis evidence requires an authenticated owner")
            analysis_evidence = self._get_confirmed_analysis_evidence(
                user_id=user_id,
                task_id=phenomenon.task_id,
            )
            self._append_analysis_evidence(
                evidence_items=evidence_items,
                used_evidence_ids=used_evidence_ids,
                analysis_evidence=analysis_evidence,
            )
        elif self._get_confirmed_comparison_projection is not None:
            if user_id is None:
                raise ValueError("personal comparison evidence requires an authenticated owner")
            projection = self._get_confirmed_comparison_projection(
                user_id=user_id,
                task_id=phenomenon.task_id,
            )
            for item in projection.evidence_items:
                if item.evidence_ref_id in used_evidence_ids:
                    raise ValueError(
                        f"comparison evidence id conflicts with existing evidence: "
                        f"{item.evidence_ref_id}"
                    )
                used_evidence_ids.add(item.evidence_ref_id)
                locator = item.locator.display()
                kind = item.finding_kind.value
                boundary = {
                    "support": "用户已确认的案例比较支持证据，仅支持该比较判断。",
                    "counterexample": "用户已确认的案例比较反例，仅用于限制或修订理论解释。",
                    "contradict": "用户已确认的案例比较矛盾材料，仅用于检验理论边界。",
                    "competing_explanation": "用户已确认的竞争解释证据，不代表最终理论结论。",
                }.get(kind, "用户已确认的案例比较证据，不代表最终理论结论。")
                source_id = (
                    f"research-material:{item.material_id}:{item.parse_id}:{item.segment_id}"
                )
                source = SourceRecordSnapshot(
                    source_id=source_id,
                    source_type="personal_research_material",
                    title=(
                        f"{item.case_label} · 个人研究材料" if item.case_label else "个人研究材料"
                    ),
                    authors_or_institution=(),
                    year=None,
                    publication=None,
                    locator=locator,
                    url=None,
                    verification_status=SourceVerificationStatus.VERIFIED,
                    use_boundary=boundary,
                )
                evidence_items.append(
                    EvidenceItemSnapshot(
                        evidence_ref_id=item.evidence_ref_id,
                        claim=item.statement,
                        excerpt=item.quote,
                        locator=locator,
                        source=source,
                        verification_status=SourceVerificationStatus.VERIFIED,
                        use_boundary=boundary,
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

    @staticmethod
    def _append_analysis_evidence(
        *,
        evidence_items: list[EvidenceItemSnapshot],
        used_evidence_ids: set[str],
        analysis_evidence: tuple[CycleEvidence, ...],
    ) -> None:
        boundaries = {
            "analytic_code": "用户已确认的分析代码，仅作为理论判断的正式分析依据。",
            "analytic_memo": "用户已确认的分析备忘，仅作为理论判断的正式分析依据。",
            "support": "用户已确认的支持证据，仅支持其来源判断。",
            "counterexample": "用户已确认的反例，仅用于限制或修订理论解释。",
            "contradiction": "用户已确认的矛盾材料，仅用于检验理论边界。",
            "competing_explanation": "用户已确认的竞争解释，不代表最终理论结论。",
        }
        for item in analysis_evidence:
            if item.evidence_ref_id in used_evidence_ids:
                raise ValueError(
                    f"analysis evidence id conflicts with existing evidence: {item.evidence_ref_id}"
                )
            used_evidence_ids.add(item.evidence_ref_id)
            kind = item.kind.value
            boundary = boundaries[kind]
            source_id = f"research-material:{item.material_id}:{item.parse_id}:{item.segment_id}"
            evidence_items.append(
                EvidenceItemSnapshot(
                    evidence_ref_id=item.evidence_ref_id,
                    claim=item.statement,
                    excerpt=item.quote,
                    locator=item.locator,
                    source=SourceRecordSnapshot(
                        source_id=source_id,
                        source_type="personal_research_material",
                        title=(
                            f"{item.case_label} · 个人研究材料"
                            if item.case_label
                            else "个人研究材料"
                        ),
                        authors_or_institution=(),
                        year=None,
                        publication=None,
                        locator=item.locator,
                        url=None,
                        verification_status=SourceVerificationStatus.VERIFIED,
                        use_boundary=boundary,
                    ),
                    verification_status=SourceVerificationStatus.VERIFIED,
                    use_boundary=boundary,
                )
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
