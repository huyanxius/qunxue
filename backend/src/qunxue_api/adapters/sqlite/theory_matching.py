from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.theory_matching_model import (
    ConfirmedTheoryPlanRow,
    MatchRunRow,
    TheoryDecisionDraftRequestRow,
    TheoryDecisionDraftRow,
    TheoryDecisionSetRow,
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
    ConfirmedTheoryPlanSnapshot,
    EvidenceBundleSnapshot,
    EvidenceItemSnapshot,
    MatchCompletionBasis,
    MatchRunModelSnapshot,
    MatchRunSnapshot,
    MatchRunStatus,
    RetrievalProvenanceSnapshot,
    TheoryCandidateContentSnapshot,
    TheoryCandidateFailureSnapshot,
    TheoryCandidateRetryRecord,
    TheoryCandidateSnapshot,
    TheoryDecisionAction,
    TheoryDecisionCommand,
    TheoryDecisionDraftSnapshot,
    TheoryDecisionRecord,
    TheoryDecisionSetSnapshot,
    TheoryJudgementDraft,
    TheoryJudgementVerdict,
    TheoryRelationCommand,
    TheoryRelationSnapshot,
    TheoryUseAssignment,
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

    def delete(self, match_run_id: UUID) -> None:
        self._session.execute(
            delete(MatchRunRow).where(MatchRunRow.match_run_id == str(match_run_id))
        )

    def save(self, snapshot: MatchRunSnapshot) -> MatchRunSnapshot:
        model = snapshot.model
        result = self._session.execute(
            update(MatchRunRow)
            .where(
                MatchRunRow.match_run_id == str(snapshot.match_run_id),
                MatchRunRow.version == snapshot.version - 1,
            )
            .values(
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
            )
        )
        if result.rowcount == 1:
            return snapshot
        row = self._session.scalar(
            select(MatchRunRow)
            .where(MatchRunRow.match_run_id == str(snapshot.match_run_id))
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise LookupError(snapshot.match_run_id)
        return _snapshot_from_row(row)

    def get_decision_draft(
        self, match_run_id: UUID
    ) -> TheoryDecisionDraftSnapshot | None:
        row = self._session.scalar(
            select(TheoryDecisionDraftRow).where(
                TheoryDecisionDraftRow.match_run_id == str(match_run_id)
            )
        )
        return _decision_draft_from_row(row)

    def get_decision_draft_replay(
        self,
        *,
        match_run_id: UUID,
        idempotency_key: str,
    ) -> tuple[str, TheoryDecisionDraftSnapshot] | None:
        row = self._session.scalar(
            select(TheoryDecisionDraftRequestRow).where(
                TheoryDecisionDraftRequestRow.match_run_id == str(match_run_id),
                TheoryDecisionDraftRequestRow.idempotency_key == idempotency_key,
            )
        )
        if row is None:
            return None
        return (
            row.request_hash,
            _decision_draft_from_payload(row.response_snapshot),
        )

    def save_decision_draft(
        self,
        snapshot: TheoryDecisionDraftSnapshot,
        *,
        expected_version: int,
        idempotency_key: str,
        request_hash: str,
        request_record_id: UUID,
    ) -> TheoryDecisionDraftSnapshot:
        payload = _decision_draft_payload(snapshot)
        if expected_version == 0:
            result = self._session.execute(
                insert(TheoryDecisionDraftRow)
                .values(
                    draft_id=str(snapshot.draft_id),
                    match_run_id=str(snapshot.match_run_id),
                    version=snapshot.version,
                    snapshot=payload,
                    updated_at=snapshot.updated_at,
                )
                .on_conflict_do_nothing(index_elements=["match_run_id"])
            )
        else:
            result = self._session.execute(
                update(TheoryDecisionDraftRow)
                .where(
                    TheoryDecisionDraftRow.match_run_id == str(snapshot.match_run_id),
                    TheoryDecisionDraftRow.version == expected_version,
                )
                .values(
                    version=snapshot.version,
                    snapshot=payload,
                    updated_at=snapshot.updated_at,
                )
            )
        if result.rowcount != 1:
            raise ValueError("stale theory decision draft version")
        self._session.add(
            TheoryDecisionDraftRequestRow(
                request_record_id=str(request_record_id),
                match_run_id=str(snapshot.match_run_id),
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                resulting_version=snapshot.version,
                response_snapshot=payload,
                created_at=snapshot.updated_at,
            )
        )
        self._session.flush()
        return snapshot

    def add_decision_set(self, snapshot: TheoryDecisionSetSnapshot) -> TheoryDecisionSetSnapshot:
        self._session.execute(
            insert(TheoryDecisionSetRow)
            .values(
                decision_set_id=str(snapshot.decision_set_id),
                match_run_id=str(snapshot.match_run_id),
                version=snapshot.version,
                draft_version=snapshot.draft_version,
                snapshot=_decision_set_payload(snapshot),
                idempotency_key=snapshot.idempotency_key,
                request_hash=snapshot.request_hash,
                created_at=snapshot.recorded_at,
            )
            .on_conflict_do_nothing(index_elements=["match_run_id", "draft_version"])
        )
        row = self._session.scalar(
            select(TheoryDecisionSetRow).where(
                TheoryDecisionSetRow.match_run_id == str(snapshot.match_run_id)
                , TheoryDecisionSetRow.draft_version == snapshot.draft_version
            )
        )
        persisted = _decision_set_from_row(row)
        if persisted is None:
            raise RuntimeError("theory decision set was not persisted")
        if (
            persisted.idempotency_key != snapshot.idempotency_key
            or persisted.request_hash != snapshot.request_hash
        ):
            raise ValueError("theory decisions were already recorded for this match run")
        return persisted

    def get_decision_set(self, decision_set_id: UUID) -> TheoryDecisionSetSnapshot | None:
        row = self._session.get(TheoryDecisionSetRow, str(decision_set_id))
        return _decision_set_from_row(row) if row is not None else None

    def get_decision_set_for_match_run(
        self, match_run_id: UUID, draft_version: int | None = None
    ) -> TheoryDecisionSetSnapshot | None:
        statement = select(TheoryDecisionSetRow).where(
            TheoryDecisionSetRow.match_run_id == str(match_run_id)
        )
        if draft_version is not None:
            statement = statement.where(
                TheoryDecisionSetRow.draft_version == draft_version
            )
        row = self._session.scalar(
            statement.order_by(TheoryDecisionSetRow.draft_version.desc())
        )
        return _decision_set_from_row(row)

    def list_decision_sets(
        self, match_run_id: UUID
    ) -> tuple[TheoryDecisionSetSnapshot, ...]:
        rows = self._session.scalars(
            select(TheoryDecisionSetRow)
            .where(TheoryDecisionSetRow.match_run_id == str(match_run_id))
            .order_by(TheoryDecisionSetRow.created_at.desc())
        )
        return tuple(
            item for row in rows if (item := _decision_set_from_row(row)) is not None
        )

    def add_confirmed_plan(
        self, snapshot: ConfirmedTheoryPlanSnapshot
    ) -> ConfirmedTheoryPlanSnapshot:
        self._session.execute(
            insert(ConfirmedTheoryPlanRow).values(
                theory_plan_id=str(snapshot.theory_plan_id),
                task_id=str(snapshot.task_id),
                match_run_id=str(snapshot.match_run_id),
                decision_set_id=str(snapshot.decision_set_id),
                version=snapshot.version,
                adopted_candidate_ids=[
                    str(candidate.candidate_id) for candidate in snapshot.candidates
                ],
                confirmed_at=snapshot.confirmed_at,
                idempotency_key=snapshot.idempotency_key,
                request_hash=snapshot.request_hash,
            )
            .on_conflict_do_nothing(index_elements=["task_id"])
        )
        row = self._session.scalar(
            select(ConfirmedTheoryPlanRow).where(
                ConfirmedTheoryPlanRow.task_id == str(snapshot.task_id)
            )
        )
        persisted = self._confirmed_plan_from_row(row)
        if persisted is None:
            raise RuntimeError("confirmed theory plan was not persisted")
        if persisted.request_hash != snapshot.request_hash:
            raise ValueError("theory plan was already confirmed with another request")
        return persisted

    def get_confirmed_plan(self, theory_plan_id: UUID) -> ConfirmedTheoryPlanSnapshot | None:
        return self._confirmed_plan_from_row(
            self._session.get(ConfirmedTheoryPlanRow, str(theory_plan_id))
        )

    def get_confirmed_plan_for_decision_set(
        self, decision_set_id: UUID
    ) -> ConfirmedTheoryPlanSnapshot | None:
        row = self._session.scalar(
            select(ConfirmedTheoryPlanRow).where(
                ConfirmedTheoryPlanRow.decision_set_id == str(decision_set_id)
            )
        )
        return self._confirmed_plan_from_row(row)

    def get_confirmed_plan_for_task(
        self, task_id: UUID
    ) -> ConfirmedTheoryPlanSnapshot | None:
        row = self._session.scalar(
            select(ConfirmedTheoryPlanRow).where(
                ConfirmedTheoryPlanRow.task_id == str(task_id)
            )
        )
        return self._confirmed_plan_from_row(row)

    def _confirmed_plan_from_row(
        self, row: ConfirmedTheoryPlanRow | None
    ) -> ConfirmedTheoryPlanSnapshot | None:
        if row is None:
            return None
        match_run = self.get(UUID(row.match_run_id))
        decision_set = self.get_decision_set(UUID(row.decision_set_id))
        if match_run is None or decision_set is None:
            raise RuntimeError("confirmed theory plan references missing snapshots")
        adopted_ids = {UUID(value) for value in row.adopted_candidate_ids}
        return ConfirmedTheoryPlanSnapshot(
            theory_plan_id=UUID(row.theory_plan_id),
            task_id=UUID(row.task_id),
            match_run_id=UUID(row.match_run_id),
            decision_set_id=UUID(row.decision_set_id),
            version=row.version,
            phenomenon=match_run.phenomenon,
            knowledge_release=match_run.knowledge_release,
            evidence_bundle=match_run.evidence_bundle,
            candidates=tuple(
                candidate
                for candidate in match_run.candidates
                if candidate.candidate_id in adopted_ids
            ),
            decisions=decision_set.decisions,
            use_assignments=decision_set.use_assignments,
            relations=decision_set.relations,
            confirmed_at=_as_utc(row.confirmed_at),
            idempotency_key=row.idempotency_key,
            request_hash=row.request_hash,
        )


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
        try:
            with self._session.begin_nested():
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
        except IntegrityError:
            # A concurrent request may have claimed the same key. Keep the
            # outer transaction usable so the caller can replay that row.
            return

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
                _profile_payload(profile) for profile in snapshot.evidence_bundle.theory_profiles
            ],
            "evidence_items": [
                _evidence_payload(item) for item in snapshot.evidence_bundle.evidence_items
            ],
            "retrieval": {
                "retrieval_index_id": snapshot.evidence_bundle.retrieval.retrieval_index_id,
                "mode": snapshot.evidence_bundle.retrieval.mode,
                "embedding_model": snapshot.evidence_bundle.retrieval.embedding_model,
                "reranker_model": snapshot.evidence_bundle.retrieval.reranker_model,
                "degraded_reason": snapshot.evidence_bundle.retrieval.degraded_reason,
                "retrieved_chunk_ids": list(
                    snapshot.evidence_bundle.retrieval.retrieved_chunk_ids
                ),
            },
        },
        "candidates": [_candidate_payload(candidate) for candidate in snapshot.candidates],
        "candidate_failures": [
            _candidate_failure_payload(failure)
            for failure in snapshot.candidate_failures
        ],
        "candidate_retry_records": [
            {
                "candidate_id": str(item.candidate_id),
                "expected_candidate_version": item.expected_candidate_version,
                "idempotency_key": item.idempotency_key,
                "request_hash": item.request_hash,
                "resulting_match_run_version": item.resulting_match_run_version,
            }
            for item in snapshot.candidate_retry_records
        ],
        "completion_basis": snapshot.completion_basis.value,
        "partial_completion_acknowledged": snapshot.partial_completion_acknowledged,
        "failed_candidate_ids": [str(value) for value in snapshot.failed_candidate_ids],
        "partial_completion_acknowledgement_reason": (
            snapshot.partial_completion_acknowledgement_reason
        ),
        "partial_completion_acknowledged_at": (
            snapshot.partial_completion_acknowledged_at.isoformat()
            if snapshot.partial_completion_acknowledged_at is not None
            else None
        ),
        "partial_completion_idempotency_key": snapshot.partial_completion_idempotency_key,
        "partial_completion_request_hash": snapshot.partial_completion_request_hash,
        "stable_candidate_order": [str(value) for value in snapshot.stable_candidate_order],
        "next_cursor": snapshot.next_cursor,
    }


def _decision_set_payload(snapshot: TheoryDecisionSetSnapshot) -> dict[str, object]:
    return {
        "decision_set_id": str(snapshot.decision_set_id),
        "match_run_id": str(snapshot.match_run_id),
        "version": snapshot.version,
        "draft_version": snapshot.draft_version,
        "recorded_at": snapshot.recorded_at.isoformat(),
        "decisions": [
            {
                "decision_id": str(item.decision_id),
                "candidate_id": str(item.candidate_id),
                "candidate_version": item.candidate_version,
                "action": item.action.value,
                "reason": item.reason,
                "related_source_ids": list(item.related_source_ids),
                "revised_applicability": item.revised_applicability,
                "related_candidate_ids": [str(value) for value in item.related_candidate_ids],
                "recorded_at": item.recorded_at.isoformat(),
            }
            for item in snapshot.decisions
        ],
        "use_assignments": [
            {
                "candidate_id": str(item.candidate_id),
                "role_code": item.role_code,
                "responsibility": item.responsibility,
            }
            for item in snapshot.use_assignments
        ],
        "relations": [
            {
                "relation_id": str(item.relation_id),
                "candidate_ids": [str(value) for value in item.candidate_ids],
                "relation_kind": item.relation_kind,
                "explanation": item.explanation,
                "premise_compatibility": item.premise_compatibility,
                "supporting_evidence": list(item.supporting_evidence),
                "excluding_evidence": list(item.excluding_evidence),
                "distinguishing_evidence": list(item.distinguishing_evidence),
            }
            for item in snapshot.relations
        ],
    }


def _decision_set_from_row(row: TheoryDecisionSetRow | None) -> TheoryDecisionSetSnapshot | None:
    if row is None:
        return None
    payload = row.snapshot
    return TheoryDecisionSetSnapshot(
        decision_set_id=UUID(row.decision_set_id),
        match_run_id=UUID(row.match_run_id),
        version=row.version,
        decisions=tuple(
            TheoryDecisionRecord(
                decision_id=UUID(str(item["decision_id"])),
                candidate_id=UUID(str(item["candidate_id"])),
                candidate_version=int(item["candidate_version"]),
                action=TheoryDecisionAction(str(item["action"])),
                reason=str(item["reason"]),
                related_source_ids=tuple(
                    str(value) for value in item.get("related_source_ids", [])
                ),
                revised_applicability=(
                    None
                    if item.get("revised_applicability") is None
                    else str(item["revised_applicability"])
                ),
                related_candidate_ids=tuple(
                    UUID(str(value)) for value in item.get("related_candidate_ids", [])
                ),
                recorded_at=datetime.fromisoformat(str(item["recorded_at"])),
            )
            for item in payload.get("decisions", [])
        ),
        use_assignments=tuple(
            TheoryUseAssignment(
                candidate_id=UUID(str(item["candidate_id"])),
                role_code=str(item["role_code"]),
                responsibility=str(item["responsibility"]),
            )
            for item in payload.get("use_assignments", [])
        ),
        relations=tuple(
            TheoryRelationSnapshot(
                relation_id=UUID(str(item["relation_id"])),
                candidate_ids=tuple(UUID(str(value)) for value in item.get("candidate_ids", [])),
                relation_kind=str(item["relation_kind"]),
                explanation=str(item["explanation"]),
                premise_compatibility=str(item["premise_compatibility"]),
                supporting_evidence=tuple(
                    str(value) for value in item.get("supporting_evidence", [])
                ),
                excluding_evidence=tuple(
                    str(value) for value in item.get("excluding_evidence", [])
                ),
                distinguishing_evidence=tuple(
                    str(value) for value in item.get("distinguishing_evidence", [])
                ),
            )
            for item in payload.get("relations", [])
        ),
        recorded_at=datetime.fromisoformat(str(payload["recorded_at"])),
        draft_version=row.draft_version,
        idempotency_key=row.idempotency_key,
        request_hash=row.request_hash,
    )


def _decision_draft_payload(
    snapshot: TheoryDecisionDraftSnapshot,
) -> dict[str, object]:
    return {
        "draft_id": str(snapshot.draft_id),
        "match_run_id": str(snapshot.match_run_id),
        "version": snapshot.version,
        "expected_match_run_version": snapshot.expected_match_run_version,
        "completion_basis": snapshot.completion_basis.value,
        "decisions": [
            {
                "candidate_id": str(item.candidate_id),
                "candidate_version": item.candidate_version,
                "action": item.action.value if item.action is not None else None,
                "reason": item.reason,
                "related_source_ids": list(item.related_source_ids),
                "revised_applicability": item.revised_applicability,
                "related_candidate_ids": [
                    str(value) for value in item.related_candidate_ids
                ],
            }
            for item in snapshot.decisions
        ],
        "use_assignments": [
            {
                "candidate_id": str(item.candidate_id),
                "role_code": item.role_code,
                "responsibility": item.responsibility,
            }
            for item in snapshot.use_assignments
        ],
        "relations": [
            {
                "candidate_ids": [str(value) for value in item.candidate_ids],
                "relation_kind": item.relation_kind,
                "explanation": item.explanation,
                "premise_compatibility": item.premise_compatibility,
                "supporting_evidence": list(item.supporting_evidence),
                "excluding_evidence": list(item.excluding_evidence),
                "distinguishing_evidence": list(item.distinguishing_evidence),
            }
            for item in snapshot.relations
        ],
        "acknowledged_candidate_ids": [
            str(value) for value in snapshot.acknowledged_candidate_ids
        ],
        "failed_candidate_ids": [str(value) for value in snapshot.failed_candidate_ids],
        "partial_completion_acknowledgement_reason": (
            snapshot.partial_completion_acknowledgement_reason
        ),
        "updated_at": snapshot.updated_at.isoformat(),
    }


def _decision_draft_from_row(
    row: TheoryDecisionDraftRow | None,
) -> TheoryDecisionDraftSnapshot | None:
    if row is None:
        return None
    return _decision_draft_from_payload(row.snapshot)


def _decision_draft_from_payload(
    payload: dict[str, object],
) -> TheoryDecisionDraftSnapshot:
    return TheoryDecisionDraftSnapshot(
        draft_id=UUID(str(payload["draft_id"])),
        match_run_id=UUID(str(payload["match_run_id"])),
        version=int(payload["version"]),
        expected_match_run_version=int(payload["expected_match_run_version"]),
        completion_basis=MatchCompletionBasis(str(payload["completion_basis"])),
        decisions=tuple(
            TheoryDecisionCommand(
                candidate_id=UUID(str(item["candidate_id"])),
                candidate_version=int(item["candidate_version"]),
                action=(
                    TheoryDecisionAction(str(item["action"]))
                    if item.get("action") is not None
                    else None
                ),
                reason=str(item["reason"]),
                related_source_ids=tuple(
                    str(value) for value in item.get("related_source_ids", [])
                ),
                revised_applicability=_optional_text(
                    item.get("revised_applicability")
                ),
                related_candidate_ids=tuple(
                    UUID(str(value))
                    for value in item.get("related_candidate_ids", [])
                ),
            )
            for item in payload.get("decisions", [])
        ),
        use_assignments=tuple(
            TheoryUseAssignment(
                candidate_id=UUID(str(item["candidate_id"])),
                role_code=str(item["role_code"]),
                responsibility=str(item["responsibility"]),
            )
            for item in payload.get("use_assignments", [])
        ),
        relations=tuple(
            TheoryRelationCommand(
                candidate_ids=tuple(
                    UUID(str(value)) for value in item.get("candidate_ids", [])
                ),
                relation_kind=str(item["relation_kind"]),
                explanation=str(item["explanation"]),
                premise_compatibility=str(item["premise_compatibility"]),
                supporting_evidence=tuple(
                    str(value) for value in item.get("supporting_evidence", [])
                ),
                excluding_evidence=tuple(
                    str(value) for value in item.get("excluding_evidence", [])
                ),
                distinguishing_evidence=tuple(
                    str(value) for value in item.get("distinguishing_evidence", [])
                ),
            )
            for item in payload.get("relations", [])
        ),
        acknowledged_candidate_ids=tuple(
            UUID(str(value))
            for value in payload.get("acknowledged_candidate_ids", [])
        ),
        failed_candidate_ids=tuple(
            UUID(str(value)) for value in payload.get("failed_candidate_ids", [])
        ),
        partial_completion_acknowledgement_reason=_optional_text(
            payload.get("partial_completion_acknowledgement_reason")
        ),
        updated_at=datetime.fromisoformat(str(payload["updated_at"])),
    )


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
    profiles = tuple(_profile_from_payload(item) for item in bundle_payload["theory_profiles"])
    evidence_items = tuple(
        _evidence_from_payload(item) for item in bundle_payload["evidence_items"]
    )
    retrieval_payload = bundle_payload.get("retrieval", {})
    assert isinstance(retrieval_payload, dict)
    bundle = EvidenceBundleSnapshot(
        evidence_bundle_id=str(bundle_payload["evidence_bundle_id"]),
        version=int(bundle_payload["version"]),
        content_hash=str(bundle_payload["content_hash"]),
        release=release,
        theory_profiles=profiles,
        evidence_items=evidence_items,
        retrieval=RetrievalProvenanceSnapshot(
            retrieval_index_id=_optional_text(
                retrieval_payload.get("retrieval_index_id")
            ),
            mode=str(retrieval_payload.get("mode", "legacy_untracked")),
            embedding_model=_optional_text(retrieval_payload.get("embedding_model")),
            reranker_model=_optional_text(retrieval_payload.get("reranker_model")),
            degraded_reason=_optional_text(retrieval_payload.get("degraded_reason")),
            retrieved_chunk_ids=tuple(
                str(value) for value in retrieval_payload.get("retrieved_chunk_ids", [])
            ),
        ),
    )
    profiles_by_id = {profile.theory_id: profile for profile in profiles}
    candidates = tuple(
        _candidate_from_payload(item, profiles_by_id) for item in payload["candidates"]
    )
    candidate_failures = tuple(
        _candidate_failure_from_payload(item, profiles_by_id)
        for item in payload.get("candidate_failures", [])
    )
    candidate_retry_records = tuple(
        TheoryCandidateRetryRecord(
            candidate_id=UUID(str(item["candidate_id"])),
            expected_candidate_version=int(item["expected_candidate_version"]),
            idempotency_key=str(item["idempotency_key"]),
            request_hash=str(item["request_hash"]),
            resulting_match_run_version=int(item["resulting_match_run_version"]),
        )
        for item in payload.get("candidate_retry_records", [])
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
        failed_candidate_ids=tuple(
            UUID(str(value)) for value in payload.get("failed_candidate_ids", [])
        ),
        candidate_failures=candidate_failures,
        candidate_retry_records=candidate_retry_records,
        partial_completion_acknowledgement_reason=_optional_text(
            payload.get("partial_completion_acknowledgement_reason")
        ),
        partial_completion_acknowledged_at=(
            datetime.fromisoformat(str(payload["partial_completion_acknowledged_at"]))
            if payload.get("partial_completion_acknowledged_at") is not None
            else None
        ),
        partial_completion_idempotency_key=_optional_text(
            payload.get("partial_completion_idempotency_key")
        ),
        partial_completion_request_hash=_optional_text(
            payload.get("partial_completion_request_hash")
        ),
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


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


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
        verification_status=SourceVerificationStatus(str(payload["verification_status"])),
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
        source=(_source_from_payload(raw_source) if isinstance(raw_source, dict) else None),
        verification_status=SourceVerificationStatus(str(payload["verification_status"])),
        use_boundary=str(payload["use_boundary"]),
    )


def _candidate_payload(candidate: TheoryCandidateSnapshot) -> dict[str, object]:
    judgement = candidate.judgement
    return {
        "candidate_id": str(candidate.candidate_id),
        "candidate_version": candidate.candidate_version,
        "content": _candidate_content_payload(candidate.content),
        "judgement": {
            "verdict": judgement.verdict.value,
            "match_rationale": judgement.match_rationale,
            "applicable_conditions": list(judgement.applicable_conditions),
            "limitations": list(judgement.limitations),
            "material_requirements": list(judgement.material_requirements),
            "evidence_gaps": list(judgement.evidence_gaps),
            "alternative_explanations": list(judgement.alternative_explanations),
            "evidence_ref_ids": list(judgement.evidence_ref_ids),
            "supporting_evidence_ref_ids": list(
                judgement.supporting_evidence_ref_ids
            ),
            "conflicting_evidence_ref_ids": list(
                judgement.conflicting_evidence_ref_ids
            ),
        },
        "trace_id": str(candidate.trace_id),
        "request_id": str(candidate.request_id),
        "contract_version": candidate.contract_version,
        "judgement_run_status": candidate.judgement_run_status.value,
    }


def _candidate_failure_payload(
    failure: TheoryCandidateFailureSnapshot,
) -> dict[str, object]:
    return {
        "candidate_id": str(failure.candidate_id),
        "candidate_version": failure.candidate_version,
        "content": _candidate_content_payload(failure.content),
        "judgement_run_status": failure.judgement_run_status.value,
        "failure_code": failure.failure_code,
        "retryable": failure.retryable,
        "trace_id": str(failure.trace_id),
        "request_id": str(failure.request_id),
        "contract_version": failure.contract_version,
        "attempt": failure.attempt,
    }


def _candidate_content_payload(
    content: TheoryCandidateContentSnapshot,
) -> dict[str, object]:
    return {
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
    }


def _candidate_from_payload(
    payload: dict[str, object],
    profiles_by_id: dict[str, TheoryProfileSnapshot],
) -> TheoryCandidateSnapshot:
    content_payload = payload["content"]
    judgement_payload = payload["judgement"]
    assert isinstance(content_payload, dict)
    assert isinstance(judgement_payload, dict)
    content = _candidate_content_from_payload(content_payload, profiles_by_id)
    judgement = TheoryJudgementDraft(
        verdict=TheoryJudgementVerdict(str(judgement_payload["verdict"])),
        match_rationale=str(judgement_payload["match_rationale"]),
        applicable_conditions=_text_tuple(judgement_payload["applicable_conditions"]),
        limitations=_text_tuple(judgement_payload["limitations"]),
        material_requirements=_text_tuple(judgement_payload["material_requirements"]),
        evidence_gaps=_text_tuple(judgement_payload["evidence_gaps"]),
        alternative_explanations=_text_tuple(judgement_payload["alternative_explanations"]),
        evidence_ref_ids=_text_tuple(judgement_payload["evidence_ref_ids"]),
        supporting_evidence_ref_ids=_text_tuple(
            judgement_payload.get(
                "supporting_evidence_ref_ids",
                judgement_payload["evidence_ref_ids"],
            )
        ),
        conflicting_evidence_ref_ids=_text_tuple(
            judgement_payload.get("conflicting_evidence_ref_ids", [])
        ),
    )
    return TheoryCandidateSnapshot(
        candidate_id=UUID(str(payload["candidate_id"])),
        candidate_version=int(payload["candidate_version"]),
        content=content,
        judgement=judgement,
        trace_id=UUID(str(payload["trace_id"])),
        request_id=UUID(str(payload["request_id"])),
        contract_version=str(payload["contract_version"]),
        judgement_run_status=CandidateJudgementRunStatus(str(payload["judgement_run_status"])),
    )


def _candidate_failure_from_payload(
    payload: dict[str, object],
    profiles_by_id: dict[str, TheoryProfileSnapshot],
) -> TheoryCandidateFailureSnapshot:
    content_payload = payload["content"]
    assert isinstance(content_payload, dict)
    return TheoryCandidateFailureSnapshot(
        candidate_id=UUID(str(payload["candidate_id"])),
        candidate_version=int(payload["candidate_version"]),
        content=_candidate_content_from_payload(content_payload, profiles_by_id),
        judgement_run_status=CandidateJudgementRunStatus(
            str(payload["judgement_run_status"])
        ),
        failure_code=str(payload["failure_code"]),
        retryable=bool(payload["retryable"]),
        trace_id=UUID(str(payload["trace_id"])),
        request_id=UUID(str(payload["request_id"])),
        contract_version=str(payload["contract_version"]),
        attempt=int(payload.get("attempt", 1)),
    )


def _candidate_content_from_payload(
    content_payload: dict[str, object],
    profiles_by_id: dict[str, TheoryProfileSnapshot],
) -> TheoryCandidateContentSnapshot:
    raw_profile_id = content_payload.get("reviewed_profile_theory_id")
    reviewed_profile = (
        profiles_by_id.get(str(raw_profile_id))
        if raw_profile_id is not None
        else None
    )
    return TheoryCandidateContentSnapshot(
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


def _text_tuple(value: object) -> tuple[str, ...]:
    assert isinstance(value, list)
    return tuple(str(item) for item in value)
