from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.theory_matching_model import (
    MatchRunRow,
    TheoryMatchingRequestRow,
)
from qunxue_api.modules.knowledge_catalog import (
    KnowledgeReleaseLevel,
    KnowledgeReleaseRef,
    KnowledgeReviewStatus,
    SourceRecordSnapshot,
    SourceVerificationStatus,
    TheoryProfileSnapshot,
)
from qunxue_api.modules.research_intake import (
    ConfirmedPhenomenonSnapshot,
    PhenomenonEvidenceRefSnapshot,
    PhenomenonEvidenceVerificationStatus,
)
from qunxue_api.modules.theory_matching import (
    CandidateContentStatus,
    CandidateJudgementRunStatus,
    CandidateOrigin,
    EvidenceBundleSnapshot,
    EvidenceItemSnapshot,
    MatchCompletionBasis,
    MatchRunModelSnapshot,
    MatchRunSnapshot,
    MatchRunStatus,
    TheoryCandidateContentSnapshot,
    TheoryCandidateSnapshot,
    TheoryJudgementDraft,
    TheoryJudgementVerdict,
)


class SqliteMatchRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, snapshot: MatchRunSnapshot) -> MatchRunSnapshot:
        model = snapshot.model
        self._session.add(
            MatchRunRow(
                match_run_id=str(snapshot.match_run_id),
                task_id=str(snapshot.task_id),
                version=snapshot.version,
                status=snapshot.status.value,
                snapshot=_snapshot_payload(snapshot),
                model_provider=model.provider if model is not None else None,
                model_version=model.model_version if model is not None else None,
                model_capability=model.capability if model is not None else None,
                model_degraded=model.degraded if model is not None else None,
                model_knowledge_release_id=(
                    model.knowledge_release_id if model is not None else None
                ),
                trace_id=str(model.trace_id) if model is not None else None,
                request_id=str(model.request_id) if model is not None else None,
                contract_version=model.contract_version if model is not None else None,
                created_at=datetime.now(UTC),
            )
        )
        self._session.flush()
        return snapshot

    def get(self, match_run_id: UUID) -> MatchRunSnapshot | None:
        row = self._session.get(MatchRunRow, str(match_run_id))
        return _snapshot_from_row(row) if row is not None else None


class SqliteMatchingRequestRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_idempotency_key(
        self,
        *,
        user_id: UUID,
        idempotency_key: str,
    ) -> tuple[str, UUID] | None:
        row = self._session.scalar(
            select(TheoryMatchingRequestRow).where(
                TheoryMatchingRequestRow.user_id == str(user_id),
                TheoryMatchingRequestRow.idempotency_key == idempotency_key,
            )
        )
        return (row.request_hash, UUID(row.match_run_id)) if row is not None else None

    def add(
        self,
        *,
        request_record_id: UUID,
        user_id: UUID,
        idempotency_key: str,
        request_hash: str,
        match_run_id: UUID,
        created_at: datetime,
    ) -> None:
        self._session.add(
            TheoryMatchingRequestRow(
                request_record_id=str(request_record_id),
                user_id=str(user_id),
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                match_run_id=str(match_run_id),
                created_at=created_at,
            )
        )
        self._session.flush()

    def owns(self, *, user_id: UUID, match_run_id: UUID) -> bool:
        row = self._session.scalar(
            select(TheoryMatchingRequestRow.request_record_id).where(
                TheoryMatchingRequestRow.user_id == str(user_id),
                TheoryMatchingRequestRow.match_run_id == str(match_run_id),
            )
        )
        return row is not None


def _snapshot_payload(snapshot: MatchRunSnapshot) -> dict[str, object]:
    return {
        "phenomenon": {
            "task_id": str(snapshot.phenomenon.task_id),
            "phenomenon_query_id": str(snapshot.phenomenon.phenomenon_query_id),
            "version": snapshot.phenomenon.version,
            "phenomenon": snapshot.phenomenon.phenomenon,
            "research_intent": snapshot.phenomenon.research_intent,
            "context": snapshot.phenomenon.context,
            "content_hash": snapshot.phenomenon.content_hash,
            "evidence_refs": [
                {
                    "evidence_ref_id": item.evidence_ref_id,
                    "excerpt": item.excerpt,
                    "source_ref_id": item.source_ref_id,
                    "source_description": item.source_description,
                    "locator": item.locator,
                    "verification_status": item.verification_status.value,
                    "use_boundary": item.use_boundary,
                }
                for item in snapshot.phenomenon.evidence_refs
            ],
        },
        "knowledge_release": {
            "knowledge_release_id": snapshot.knowledge_release.knowledge_release_id,
            "level": snapshot.knowledge_release.level.value,
            "content_hash": snapshot.knowledge_release.content_hash,
        },
        "evidence_bundle": {
            "evidence_bundle_id": snapshot.evidence_bundle.evidence_bundle_id,
            "version": snapshot.evidence_bundle.version,
            "content_hash": snapshot.evidence_bundle.content_hash,
            "theory_profiles": [
                _profile_payload(profile)
                for profile in snapshot.evidence_bundle.theory_profiles
            ],
            "evidence_items": [
                _evidence_payload(item) for item in snapshot.evidence_bundle.evidence_items
            ],
        },
        "candidates": [_candidate_payload(candidate) for candidate in snapshot.candidates],
        "completion_basis": snapshot.completion_basis.value,
        "partial_completion_acknowledged": snapshot.partial_completion_acknowledged,
        "stable_candidate_order": [str(value) for value in snapshot.stable_candidate_order],
        "next_cursor": snapshot.next_cursor,
    }


def _snapshot_from_row(row: MatchRunRow) -> MatchRunSnapshot:
    payload = row.snapshot
    phenomenon_payload = payload["phenomenon"]
    assert isinstance(phenomenon_payload, dict)
    release_payload = payload["knowledge_release"]
    assert isinstance(release_payload, dict)
    bundle_payload = payload["evidence_bundle"]
    assert isinstance(bundle_payload, dict)
    phenomenon = ConfirmedPhenomenonSnapshot(
        task_id=UUID(str(phenomenon_payload["task_id"])),
        phenomenon_query_id=UUID(str(phenomenon_payload["phenomenon_query_id"])),
        version=int(phenomenon_payload["version"]),
        phenomenon=str(phenomenon_payload["phenomenon"]),
        research_intent=_optional_text(phenomenon_payload.get("research_intent")),
        context=_optional_text(phenomenon_payload.get("context")),
        content_hash=str(phenomenon_payload["content_hash"]),
        evidence_refs=tuple(
            PhenomenonEvidenceRefSnapshot(
                evidence_ref_id=str(item["evidence_ref_id"]),
                excerpt=str(item["excerpt"]),
                source_ref_id=str(item["source_ref_id"]),
                source_description=_optional_text(item.get("source_description")),
                locator=_optional_text(item.get("locator")),
                verification_status=PhenomenonEvidenceVerificationStatus(
                    str(item["verification_status"])
                ),
                use_boundary=str(item["use_boundary"]),
            )
            for item in phenomenon_payload["evidence_refs"]
        ),
    )
    release = KnowledgeReleaseRef(
        knowledge_release_id=str(release_payload["knowledge_release_id"]),
        level=KnowledgeReleaseLevel(str(release_payload["level"])),
        content_hash=str(release_payload["content_hash"]),
    )
    profiles = tuple(
        _profile_from_payload(item) for item in bundle_payload["theory_profiles"]
    )
    evidence_items = tuple(
        _evidence_from_payload(item) for item in bundle_payload["evidence_items"]
    )
    bundle = EvidenceBundleSnapshot(
        evidence_bundle_id=str(bundle_payload["evidence_bundle_id"]),
        version=int(bundle_payload["version"]),
        content_hash=str(bundle_payload["content_hash"]),
        release=release,
        theory_profiles=profiles,
        evidence_items=evidence_items,
    )
    profiles_by_id = {profile.theory_id: profile for profile in profiles}
    candidates = tuple(
        _candidate_from_payload(item, profiles_by_id) for item in payload["candidates"]
    )
    return MatchRunSnapshot(
        match_run_id=UUID(row.match_run_id),
        task_id=UUID(row.task_id),
        version=row.version,
        status=MatchRunStatus(row.status),
        phenomenon=phenomenon,
        knowledge_release=release,
        evidence_bundle=bundle,
        candidates=candidates,
        completion_basis=MatchCompletionBasis(str(payload["completion_basis"])),
        partial_completion_acknowledged=bool(payload["partial_completion_acknowledged"]),
        stable_candidate_order=tuple(
            UUID(str(value)) for value in payload["stable_candidate_order"]
        ),
        next_cursor=_optional_text(payload.get("next_cursor")),
        model=_model_from_row(row),
    )


def _model_from_row(row: MatchRunRow) -> MatchRunModelSnapshot | None:
    fields = (
        row.model_provider,
        row.model_version,
        row.model_capability,
        row.model_degraded,
        row.model_knowledge_release_id,
        row.trace_id,
        row.request_id,
        row.contract_version,
    )
    if all(value is None for value in fields):
        return None
    if any(value is None for value in fields):
        raise RuntimeError("persisted match run has partial model metadata")
    return MatchRunModelSnapshot(
        provider=str(row.model_provider),
        model_version=str(row.model_version),
        capability=str(row.model_capability),
        degraded=bool(row.model_degraded),
        knowledge_release_id=str(row.model_knowledge_release_id),
        trace_id=UUID(str(row.trace_id)),
        request_id=UUID(str(row.request_id)),
        contract_version=str(row.contract_version),
    )


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _profile_payload(profile: TheoryProfileSnapshot) -> dict[str, object]:
    return {
        "theory_id": profile.theory_id,
        "related_knowledge_ids": list(profile.related_knowledge_ids),
        "title": profile.title,
        "core_propositions": list(profile.core_propositions),
        "applicable_phenomena": list(profile.applicable_phenomena),
        "analysis_levels": list(profile.analysis_levels),
        "prerequisites": list(profile.prerequisites),
        "exclusion_signals": list(profile.exclusion_signals),
        "observable_evidence": list(profile.observable_evidence),
        "competing_or_complementary_theory_ids": list(
            profile.competing_or_complementary_theory_ids
        ),
        "source_ids": list(profile.source_ids),
        "content_version": profile.content_version,
        "review_status": profile.review_status.value,
        "match_eligible": profile.match_eligible,
    }


def _profile_from_payload(payload: dict[str, object]) -> TheoryProfileSnapshot:
    return TheoryProfileSnapshot(
        theory_id=str(payload["theory_id"]),
        related_knowledge_ids=_text_tuple(payload["related_knowledge_ids"]),
        title=str(payload["title"]),
        core_propositions=_text_tuple(payload["core_propositions"]),
        applicable_phenomena=_text_tuple(payload["applicable_phenomena"]),
        analysis_levels=_text_tuple(payload["analysis_levels"]),
        prerequisites=_text_tuple(payload["prerequisites"]),
        exclusion_signals=_text_tuple(payload["exclusion_signals"]),
        observable_evidence=_text_tuple(payload["observable_evidence"]),
        competing_or_complementary_theory_ids=_text_tuple(
            payload["competing_or_complementary_theory_ids"]
        ),
        source_ids=_text_tuple(payload["source_ids"]),
        content_version=int(payload["content_version"]),
        review_status=KnowledgeReviewStatus(str(payload["review_status"])),
        match_eligible=bool(payload["match_eligible"]),
    )


def _source_payload(source: SourceRecordSnapshot) -> dict[str, object]:
    return {
        "source_id": source.source_id,
        "source_type": source.source_type,
        "title": source.title,
        "authors_or_institution": list(source.authors_or_institution),
        "year": source.year,
        "publication": source.publication,
        "locator": source.locator,
        "url": source.url,
        "verification_status": source.verification_status.value,
        "use_boundary": source.use_boundary,
    }


def _source_from_payload(payload: dict[str, object]) -> SourceRecordSnapshot:
    raw_year = payload.get("year")
    return SourceRecordSnapshot(
        source_id=str(payload["source_id"]),
        source_type=str(payload["source_type"]),
        title=str(payload["title"]),
        authors_or_institution=_text_tuple(payload["authors_or_institution"]),
        year=int(raw_year) if raw_year is not None else None,
        publication=_optional_text(payload.get("publication")),
        locator=_optional_text(payload.get("locator")),
        url=_optional_text(payload.get("url")),
        verification_status=SourceVerificationStatus(
            str(payload["verification_status"])
        ),
        use_boundary=str(payload["use_boundary"]),
    )


def _evidence_payload(item: EvidenceItemSnapshot) -> dict[str, object]:
    return {
        "evidence_ref_id": item.evidence_ref_id,
        "claim": item.claim,
        "excerpt": item.excerpt,
        "locator": item.locator,
        "source": _source_payload(item.source) if item.source is not None else None,
        "verification_status": item.verification_status.value,
        "use_boundary": item.use_boundary,
    }


def _evidence_from_payload(payload: dict[str, object]) -> EvidenceItemSnapshot:
    raw_source = payload.get("source")
    return EvidenceItemSnapshot(
        evidence_ref_id=str(payload["evidence_ref_id"]),
        claim=str(payload["claim"]),
        excerpt=_optional_text(payload.get("excerpt")),
        locator=_optional_text(payload.get("locator")),
        source=(
            _source_from_payload(raw_source) if isinstance(raw_source, dict) else None
        ),
        verification_status=SourceVerificationStatus(
            str(payload["verification_status"])
        ),
        use_boundary=str(payload["use_boundary"]),
    )


def _candidate_payload(candidate: TheoryCandidateSnapshot) -> dict[str, object]:
    content = candidate.content
    judgement = candidate.judgement
    return {
        "candidate_id": str(candidate.candidate_id),
        "candidate_version": candidate.candidate_version,
        "content": {
            "theory_id": content.theory_id,
            "title": content.title,
            "origin": content.origin.value,
            "problem_focus": content.problem_focus,
            "core_claims": list(content.core_claims),
            "analysis_levels": list(content.analysis_levels),
            "source_ids": list(content.source_ids),
            "reviewed_profile_theory_id": (
                content.reviewed_profile.theory_id
                if content.reviewed_profile is not None
                else None
            ),
            "formal_adoption_eligible": content.formal_adoption_eligible,
            "adoption_blockers": list(content.adoption_blockers),
            "knowledge_id": content.knowledge_id,
            "seed_theory_id": content.seed_theory_id,
            "content_status": content.content_status.value,
        },
        "judgement": {
            "verdict": judgement.verdict.value,
            "match_rationale": judgement.match_rationale,
            "applicable_conditions": list(judgement.applicable_conditions),
            "limitations": list(judgement.limitations),
            "material_requirements": list(judgement.material_requirements),
            "evidence_gaps": list(judgement.evidence_gaps),
            "alternative_explanations": list(judgement.alternative_explanations),
            "evidence_ref_ids": list(judgement.evidence_ref_ids),
        },
        "trace_id": str(candidate.trace_id),
        "request_id": str(candidate.request_id),
        "contract_version": candidate.contract_version,
        "judgement_run_status": candidate.judgement_run_status.value,
    }


def _candidate_from_payload(
    payload: dict[str, object],
    profiles_by_id: dict[str, TheoryProfileSnapshot],
) -> TheoryCandidateSnapshot:
    content_payload = payload["content"]
    judgement_payload = payload["judgement"]
    assert isinstance(content_payload, dict)
    assert isinstance(judgement_payload, dict)
    raw_profile_id = content_payload.get("reviewed_profile_theory_id")
    reviewed_profile = (
        profiles_by_id.get(str(raw_profile_id)) if raw_profile_id is not None else None
    )
    content = TheoryCandidateContentSnapshot(
        theory_id=_optional_text(content_payload.get("theory_id")),
        title=str(content_payload["title"]),
        origin=CandidateOrigin(str(content_payload["origin"])),
        problem_focus=str(content_payload["problem_focus"]),
        core_claims=_text_tuple(content_payload["core_claims"]),
        analysis_levels=_text_tuple(content_payload["analysis_levels"]),
        source_ids=_text_tuple(content_payload["source_ids"]),
        reviewed_profile=reviewed_profile,
        formal_adoption_eligible=bool(content_payload["formal_adoption_eligible"]),
        adoption_blockers=_text_tuple(content_payload["adoption_blockers"]),
        knowledge_id=_optional_text(content_payload.get("knowledge_id")),
        seed_theory_id=_optional_text(content_payload.get("seed_theory_id")),
        content_status=CandidateContentStatus(str(content_payload["content_status"])),
    )
    judgement = TheoryJudgementDraft(
        verdict=TheoryJudgementVerdict(str(judgement_payload["verdict"])),
        match_rationale=str(judgement_payload["match_rationale"]),
        applicable_conditions=_text_tuple(judgement_payload["applicable_conditions"]),
        limitations=_text_tuple(judgement_payload["limitations"]),
        material_requirements=_text_tuple(judgement_payload["material_requirements"]),
        evidence_gaps=_text_tuple(judgement_payload["evidence_gaps"]),
        alternative_explanations=_text_tuple(
            judgement_payload["alternative_explanations"]
        ),
        evidence_ref_ids=_text_tuple(judgement_payload["evidence_ref_ids"]),
    )
    return TheoryCandidateSnapshot(
        candidate_id=UUID(str(payload["candidate_id"])),
        candidate_version=int(payload["candidate_version"]),
        content=content,
        judgement=judgement,
        trace_id=UUID(str(payload["trace_id"])),
        request_id=UUID(str(payload["request_id"])),
        contract_version=str(payload["contract_version"]),
        judgement_run_status=CandidateJudgementRunStatus(
            str(payload["judgement_run_status"])
        ),
    )


def _text_tuple(value: object) -> tuple[str, ...]:
    assert isinstance(value, list)
    return tuple(str(item) for item in value)
