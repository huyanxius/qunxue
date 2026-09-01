from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from qunxue_api.modules.knowledge_catalog import KnowledgeReleaseRef
from qunxue_api.modules.research_intake import ConfirmedPhenomenonSnapshot
from qunxue_api.modules.theory_matching.public import (
    CandidateContentStatus,
    CandidateJudgementRunStatus,
    CandidateOrigin,
    ConfirmedTheoryPlanSnapshot,
    EvidenceBundleSnapshot,
    MatchCompletionBasis,
    MatchRunModelSnapshot,
    MatchRunRepository,
    MatchRunSnapshot,
    MatchRunStatus,
    TheoryCandidateContentSnapshot,
    TheoryCandidateFailureSnapshot,
    TheoryCandidateJudge,
    TheoryCandidateRetryRecord,
    TheoryCandidateSnapshot,
    TheoryDecisionCommand,
    TheoryDecisionDraftSnapshot,
    TheoryDecisionRecord,
    TheoryDecisionSetSnapshot,
    TheoryEvidenceSource,
    TheoryJudgementBatchInput,
    TheoryJudgementBatchItem,
    TheoryJudgementInput,
    TheoryRelationCommand,
    TheoryRelationSnapshot,
    TheoryUseAssignment,
)
from qunxue_api.modules.theory_matching.rules import validate_theory_plan_confirmation


class TheoryMatchingService:
    def __init__(
        self,
        *,
        evidence_source: TheoryEvidenceSource,
        judge: TheoryCandidateJudge,
        repository: MatchRunRepository,
        provider: str,
        model_version: str,
        capability: str,
        contract_version: str,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._evidence_source = evidence_source
        self._judge = judge
        self._repository = repository
        self._provider = provider
        self._model_version = model_version
        self._capability = capability
        self._contract_version = contract_version
        self._id_factory = id_factory

    def start(
        self,
        *,
        user_id: UUID | None = None,
        phenomenon: ConfirmedPhenomenonSnapshot,
        release: KnowledgeReleaseRef,
    ) -> MatchRunSnapshot:
        evidence_bundle = self._evidence_source.retrieve(
            user_id=user_id,
            phenomenon=phenomenon,
            release=release,
        )
        match_run_id = self._id_factory()
        if len(evidence_bundle.theory_profiles) >= 3:
            return self._start_judgement(
                match_run_id=match_run_id,
                phenomenon=phenomenon,
                release=release,
                evidence_bundle=evidence_bundle,
            )

        snapshot = MatchRunSnapshot(
            match_run_id=match_run_id,
            task_id=phenomenon.task_id,
            version=1,
            status=MatchRunStatus.NO_RELIABLE_CANDIDATE,
            phenomenon=phenomenon,
            knowledge_release=release,
            evidence_bundle=evidence_bundle,
            candidates=(),
            completion_basis=MatchCompletionBasis.COMPLETE,
            stable_candidate_order=(),
            model=None,
        )
        return self._repository.add(snapshot)

    def _start_judgement(
        self,
        *,
        match_run_id: UUID,
        phenomenon: ConfirmedPhenomenonSnapshot,
        release: KnowledgeReleaseRef,
        evidence_bundle: EvidenceBundleSnapshot,
    ) -> MatchRunSnapshot:
        contents = tuple(
            TheoryCandidateContentSnapshot(
                theory_id=profile.theory_id,
                title=profile.title,
                origin=CandidateOrigin.PRE_REVIEWED_KNOWLEDGE,
                problem_focus=(
                    "；".join(profile.applicable_phenomena)
                    if profile.applicable_phenomena
                    else profile.title
                ),
                core_claims=profile.core_propositions,
                analysis_levels=profile.analysis_levels,
                source_ids=profile.source_ids,
                reviewed_profile=profile,
                formal_adoption_eligible=profile.match_eligible,
                adoption_blockers=(),
                knowledge_id=profile.related_knowledge_ids[0],
                content_status=CandidateContentStatus.PRE_REVIEW_COMPLETED,
            )
            for profile in evidence_bundle.theory_profiles
        )
        candidate_ids = tuple(self._id_factory() for _content in contents)
        items = []
        for candidate_id, content in zip(candidate_ids, contents, strict=True):
            candidate_evidence = tuple(
                item
                for item in evidence_bundle.evidence_items
                if _evidence_applies_to_candidate(item, content.source_ids)
            )
            items.append(
                TheoryJudgementBatchItem(
                    candidate_id=candidate_id,
                    candidate_version=1,
                    judgement_input=TheoryJudgementInput(
                        knowledge_release=evidence_bundle.release,
                        phenomenon=phenomenon,
                        candidate=content,
                        comparison_candidates=tuple(
                            other for other in contents if other is not content
                        ),
                        evidence_items=candidate_evidence,
                    ),
                )
            )
        judgement = self._judge.judge_and_rerank(
            input=TheoryJudgementBatchInput(
                items=tuple(items),
                target_candidate_ids=candidate_ids,
            )
        )
        content_by_id = dict(zip(candidate_ids, contents, strict=True))
        result_by_id = {item.candidate_id: item for item in judgement.results}
        stable_order = tuple(
            candidate_id
            for candidate_id in judgement.ranked_candidate_order
            if candidate_id in result_by_id
            and result_by_id[candidate_id].status is CandidateJudgementRunStatus.SUCCEEDED
            and result_by_id[candidate_id].judgement is not None
        )
        candidates = tuple(
            TheoryCandidateSnapshot(
                candidate_id=candidate_id,
                candidate_version=result_by_id[candidate_id].candidate_version,
                content=content_by_id[candidate_id],
                judgement=result_by_id[candidate_id].judgement,
                trace_id=result_by_id[candidate_id].trace_id,
                request_id=result_by_id[candidate_id].request_id,
                contract_version=result_by_id[candidate_id].contract_version,
                judgement_run_status=result_by_id[candidate_id].status,
            )
            for candidate_id in stable_order
            if result_by_id[candidate_id].judgement is not None
        )
        successful_candidate_ids = {candidate.candidate_id for candidate in candidates}
        failed_candidate_ids = tuple(
            candidate_id
            for candidate_id in candidate_ids
            if candidate_id not in successful_candidate_ids
        )
        retryable_ids = set(judgement.retryable_candidate_ids)
        candidate_failures = tuple(
            TheoryCandidateFailureSnapshot(
                candidate_id=candidate_id,
                candidate_version=(
                    result_by_id[candidate_id].candidate_version
                    if candidate_id in result_by_id
                    else 1
                ),
                content=content_by_id[candidate_id],
                judgement_run_status=(
                    result_by_id[candidate_id].status
                    if candidate_id in result_by_id
                    else CandidateJudgementRunStatus.FAILED
                ),
                failure_code=(
                    result_by_id[candidate_id].failure_code
                    if candidate_id in result_by_id
                    and result_by_id[candidate_id].failure_code is not None
                    else "judgement_missing"
                ),
                retryable=candidate_id in retryable_ids,
                trace_id=(
                    result_by_id[candidate_id].trace_id
                    if candidate_id in result_by_id
                    else self._id_factory()
                ),
                request_id=(
                    result_by_id[candidate_id].request_id
                    if candidate_id in result_by_id
                    else self._id_factory()
                ),
                contract_version=(
                    result_by_id[candidate_id].contract_version
                    if candidate_id in result_by_id
                    else self._contract_version
                ),
            )
            for candidate_id in failed_candidate_ids
        )
        if len(candidates) == len(contents):
            run_status = MatchRunStatus.AWAITING_DECISION
        elif candidates:
            run_status = MatchRunStatus.PARTIAL_FAILURE
        elif candidate_failures and all(
            item.failure_code == "no_reliable_candidate" for item in candidate_failures
        ):
            run_status = MatchRunStatus.NO_RELIABLE_CANDIDATE
        else:
            run_status = MatchRunStatus.FAILED
        first_result = judgement.results[0] if judgement.results else None
        snapshot = MatchRunSnapshot(
            match_run_id=match_run_id,
            task_id=phenomenon.task_id,
            version=1,
            status=run_status,
            phenomenon=phenomenon,
            knowledge_release=release,
            evidence_bundle=evidence_bundle,
            candidates=candidates,
            completion_basis=judgement.completion_basis,
            failed_candidate_ids=failed_candidate_ids,
            candidate_failures=candidate_failures,
            stable_candidate_order=stable_order,
            model=MatchRunModelSnapshot(
                provider=self._provider,
                model_version=self._model_version,
                capability=self._capability,
                degraded=judgement.completion_basis is not MatchCompletionBasis.COMPLETE,
                knowledge_release_id=release.knowledge_release_id,
                trace_id=(
                    first_result.trace_id if first_result is not None else self._id_factory()
                ),
                request_id=(
                    first_result.request_id if first_result is not None else self._id_factory()
                ),
                contract_version=self._contract_version,
            ),
        )
        return self._repository.add(snapshot)

    def retry_candidate(
        self,
        *,
        match_run_id: UUID,
        candidate_id: UUID,
        expected_version: int,
        expected_candidate_version: int,
        idempotency_key: str | None = None,
        request_hash: str | None = None,
    ) -> MatchRunSnapshot:
        match_run = self.get(match_run_id)
        if (idempotency_key is None) != (request_hash is None):
            raise ValueError("retry idempotency key and request hash must be provided together")
        if idempotency_key is not None:
            replay = next(
                (
                    item
                    for item in match_run.candidate_retry_records
                    if item.idempotency_key == idempotency_key
                ),
                None,
            )
            if replay is not None:
                if replay.request_hash != request_hash:
                    raise ValueError("idempotency key was already used with another payload")
                return match_run
        if match_run.version != expected_version:
            raise ValueError("stale match run version")
        if match_run.partial_completion_acknowledged:
            raise ValueError("acknowledged partial runs cannot retry a candidate")
        failure_by_id = {item.candidate_id: item for item in match_run.candidate_failures}
        failure = failure_by_id.get(candidate_id)
        if failure is None:
            raise LookupError(candidate_id)
        if failure.candidate_version != expected_candidate_version:
            raise ValueError("stale failed candidate version")
        if not failure.retryable:
            raise ValueError("failed candidate is not retryable")

        all_contents = tuple(
            [item.content for item in match_run.candidates]
            + [item.content for item in match_run.candidate_failures]
        )
        evidence = tuple(
            item
            for item in match_run.evidence_bundle.evidence_items
            if _evidence_applies_to_candidate(item, failure.content.source_ids)
        )
        retry_version = failure.candidate_version + 1
        result = self._judge.judge_and_rerank(
            input=TheoryJudgementBatchInput(
                items=(
                    TheoryJudgementBatchItem(
                        candidate_id=candidate_id,
                        candidate_version=retry_version,
                        judgement_input=TheoryJudgementInput(
                            knowledge_release=match_run.knowledge_release,
                            phenomenon=match_run.phenomenon,
                            candidate=failure.content,
                            comparison_candidates=tuple(
                                item for item in all_contents if item is not failure.content
                            ),
                            evidence_items=evidence,
                        ),
                    ),
                ),
                target_candidate_ids=(candidate_id,),
            )
        )
        retry_result = next(
            (item for item in result.results if item.candidate_id == candidate_id),
            None,
        )
        remaining_failures = tuple(
            item for item in match_run.candidate_failures if item.candidate_id != candidate_id
        )
        candidates = match_run.candidates
        if (
            retry_result is not None
            and retry_result.status is CandidateJudgementRunStatus.SUCCEEDED
            and retry_result.judgement is not None
        ):
            candidates = (
                *candidates,
                TheoryCandidateSnapshot(
                    candidate_id=candidate_id,
                    candidate_version=retry_result.candidate_version,
                    content=failure.content,
                    judgement=retry_result.judgement,
                    trace_id=retry_result.trace_id,
                    request_id=retry_result.request_id,
                    contract_version=retry_result.contract_version,
                    judgement_run_status=retry_result.status,
                ),
            )
            theory_order = {
                profile.theory_id: index
                for index, profile in enumerate(match_run.evidence_bundle.theory_profiles)
            }
            candidates = tuple(
                sorted(
                    candidates,
                    key=lambda item: theory_order.get(
                        item.content.theory_id or "", len(theory_order)
                    ),
                )
            )
        else:
            remaining_failures = (
                *remaining_failures,
                TheoryCandidateFailureSnapshot(
                    candidate_id=candidate_id,
                    candidate_version=retry_version,
                    content=failure.content,
                    judgement_run_status=(
                        retry_result.status
                        if retry_result is not None
                        else CandidateJudgementRunStatus.FAILED
                    ),
                    failure_code=(
                        retry_result.failure_code
                        if retry_result is not None and retry_result.failure_code is not None
                        else "judgement_missing"
                    ),
                    retryable=(
                        candidate_id in set(result.retryable_candidate_ids)
                        if retry_result is not None
                        else False
                    ),
                    trace_id=(
                        retry_result.trace_id if retry_result is not None else self._id_factory()
                    ),
                    request_id=(
                        retry_result.request_id if retry_result is not None else self._id_factory()
                    ),
                    contract_version=(
                        retry_result.contract_version
                        if retry_result is not None
                        else self._contract_version
                    ),
                    attempt=failure.attempt + 1,
                ),
            )

        if not remaining_failures:
            status = MatchRunStatus.AWAITING_DECISION
            completion_basis = MatchCompletionBasis.COMPLETE
        elif candidates:
            status = MatchRunStatus.PARTIAL_FAILURE
            completion_basis = MatchCompletionBasis.PARTIAL
        elif all(item.failure_code == "no_reliable_candidate" for item in remaining_failures):
            status = MatchRunStatus.NO_RELIABLE_CANDIDATE
            completion_basis = MatchCompletionBasis.PARTIAL
        else:
            status = MatchRunStatus.FAILED
            completion_basis = MatchCompletionBasis.PARTIAL
        retry_records = match_run.candidate_retry_records
        if idempotency_key is not None and request_hash is not None:
            retry_records = (
                *retry_records,
                TheoryCandidateRetryRecord(
                    candidate_id=candidate_id,
                    expected_candidate_version=expected_candidate_version,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    resulting_match_run_version=match_run.version + 1,
                ),
            )
        saved = self._repository.save(
            replace(
                match_run,
                version=match_run.version + 1,
                status=status,
                candidates=candidates,
                completion_basis=completion_basis,
                failed_candidate_ids=tuple(item.candidate_id for item in remaining_failures),
                candidate_failures=remaining_failures,
                candidate_retry_records=retry_records,
                stable_candidate_order=tuple(item.candidate_id for item in candidates),
                model=(
                    replace(match_run.model, degraded=bool(remaining_failures))
                    if match_run.model is not None
                    else None
                ),
            )
        )
        if idempotency_key is not None and request_hash is not None:
            persisted = next(
                (
                    item
                    for item in saved.candidate_retry_records
                    if item.idempotency_key == idempotency_key
                ),
                None,
            )
            if persisted is None:
                raise ValueError("stale match run version")
            if persisted.request_hash != request_hash:
                raise ValueError("idempotency key was already used with another payload")
        return saved

    def acknowledge_partial_completion(
        self,
        *,
        match_run_id: UUID,
        expected_version: int,
        acknowledged_candidate_ids: tuple[UUID, ...],
        failed_candidate_ids: tuple[UUID, ...],
        reason: str,
        idempotency_key: str | None = None,
        request_hash: str | None = None,
    ) -> MatchRunSnapshot:
        match_run = self.get(match_run_id)
        if match_run.partial_completion_acknowledged:
            if (
                match_run.partial_completion_idempotency_key == idempotency_key
                and match_run.partial_completion_request_hash == request_hash
            ):
                return match_run
            raise ValueError("partial completion was already acknowledged")
        if match_run.version != expected_version:
            raise ValueError("stale match run version")
        if match_run.status is not MatchRunStatus.PARTIAL_FAILURE:
            raise ValueError("only a partial match run can be acknowledged")
        if not match_run.candidates:
            raise ValueError(
                "partial completion cannot be acknowledged without a successful candidate"
            )
        if set(acknowledged_candidate_ids) != {
            candidate.candidate_id for candidate in match_run.candidates
        }:
            raise ValueError("acknowledged candidate IDs do not match completed candidates")
        if set(failed_candidate_ids) != set(match_run.failed_candidate_ids):
            raise ValueError("failed candidate IDs do not match the partial match run")
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise ValueError("partial completion acknowledgement reason is required")
        now = datetime.now(UTC)
        saved = self._repository.save(
            replace(
                match_run,
                version=match_run.version + 1,
                status=MatchRunStatus.AWAITING_DECISION,
                completion_basis=MatchCompletionBasis.PARTIAL_WITH_USER_ACK,
                partial_completion_acknowledged=True,
                partial_completion_acknowledgement_reason=normalized_reason,
                partial_completion_acknowledged_at=now,
                partial_completion_idempotency_key=idempotency_key,
                partial_completion_request_hash=request_hash,
            )
        )
        if (
            saved.partial_completion_idempotency_key != idempotency_key
            or saved.partial_completion_request_hash != request_hash
        ):
            raise ValueError("partial completion was already acknowledged")
        return saved

    def get_decision_draft(self, match_run_id: UUID) -> TheoryDecisionDraftSnapshot | None:
        self.get(match_run_id)
        return self._repository.get_decision_draft(match_run_id)

    def save_decision_draft(
        self,
        *,
        match_run_id: UUID,
        expected_match_run_version: int,
        expected_draft_version: int,
        completion_basis: MatchCompletionBasis,
        decisions: tuple[TheoryDecisionCommand, ...],
        use_assignments: tuple[TheoryUseAssignment, ...],
        relations: tuple[TheoryRelationCommand, ...],
        acknowledged_candidate_ids: tuple[UUID, ...],
        failed_candidate_ids: tuple[UUID, ...],
        partial_completion_acknowledgement_reason: str | None,
        idempotency_key: str,
        request_hash: str,
    ) -> TheoryDecisionDraftSnapshot:
        replay = self._repository.get_decision_draft_replay(
            match_run_id=match_run_id,
            idempotency_key=idempotency_key,
        )
        if replay is not None:
            replay_hash, replay_snapshot = replay
            if replay_hash != request_hash:
                raise ValueError(
                    "Idempotency-Key was already used for another theory decision draft"
                )
            return replay_snapshot

        match_run = self.get(match_run_id)
        if self._repository.get_confirmed_plan_for_task(match_run.task_id) is not None:
            raise ValueError("research task already has a confirmed theory plan")
        if match_run.version != expected_match_run_version:
            raise ValueError("stale match run version")
        if completion_basis is not match_run.completion_basis:
            raise ValueError("match completion basis is stale")
        self._validate_draft_content(
            match_run=match_run,
            decisions=decisions,
            use_assignments=use_assignments,
            relations=relations,
        )
        self._validate_draft_partial_acknowledgement(
            match_run=match_run,
            acknowledged_candidate_ids=acknowledged_candidate_ids,
            failed_candidate_ids=failed_candidate_ids,
            reason=partial_completion_acknowledgement_reason,
        )
        current_draft = self._repository.get_decision_draft(match_run_id)
        now = datetime.now(UTC)
        return self._repository.save_decision_draft(
            TheoryDecisionDraftSnapshot(
                draft_id=(
                    current_draft.draft_id if current_draft is not None else self._id_factory()
                ),
                match_run_id=match_run_id,
                version=expected_draft_version + 1,
                expected_match_run_version=expected_match_run_version,
                completion_basis=completion_basis,
                decisions=decisions,
                use_assignments=use_assignments,
                relations=relations,
                acknowledged_candidate_ids=acknowledged_candidate_ids,
                failed_candidate_ids=failed_candidate_ids,
                partial_completion_acknowledgement_reason=(
                    partial_completion_acknowledgement_reason.strip()
                    if partial_completion_acknowledgement_reason is not None
                    else None
                ),
                updated_at=now,
            ),
            expected_version=expected_draft_version,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            request_record_id=self._id_factory(),
        )

    def finalize_decision_draft(
        self,
        *,
        match_run_id: UUID,
        expected_match_run_version: int,
        expected_draft_version: int,
        idempotency_key: str,
        request_hash: str,
    ) -> TheoryDecisionSetSnapshot:
        match_run = self.get(match_run_id)
        if match_run.version != expected_match_run_version:
            raise ValueError("stale match run version")
        draft = self._repository.get_decision_draft(match_run_id)
        if draft is None:
            raise ValueError("save the theory decision draft before finalizing it")
        if draft.version != expected_draft_version:
            raise ValueError("stale theory decision draft version")
        existing = self._repository.get_decision_set_for_match_run(
            match_run_id,
            draft_version=draft.version,
        )
        if existing is not None:
            if (
                existing.idempotency_key == idempotency_key
                and existing.request_hash == request_hash
            ):
                return existing
            raise ValueError("this theory decision draft was already finalized")
        return self._record_decision_set(
            match_run=match_run,
            draft_version=draft.version,
            decisions=draft.decisions,
            use_assignments=draft.use_assignments,
            relations=draft.relations,
            completion_basis=draft.completion_basis,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )

    def get(self, match_run_id: UUID) -> MatchRunSnapshot:
        snapshot = self._repository.get(match_run_id)
        if snapshot is None:
            raise LookupError(match_run_id)
        return snapshot

    def discard(self, match_run_id: UUID) -> None:
        """Remove a run that could not be attached to its task projection."""
        self._repository.delete(match_run_id)

    def record_decisions(
        self,
        *,
        match_run_id: UUID,
        expected_version: int,
        decisions: tuple[TheoryDecisionCommand, ...],
        use_assignments: tuple[TheoryUseAssignment, ...],
        relations: tuple[TheoryRelationCommand, ...],
        completion_basis: MatchCompletionBasis | None = None,
        idempotency_key: str | None = None,
        request_hash: str | None = None,
    ) -> TheoryDecisionSetSnapshot:
        match_run = self.get(match_run_id)
        existing = self._repository.get_decision_set_for_match_run(match_run_id)
        if existing is not None:
            if (
                request_hash is not None
                and existing.idempotency_key == idempotency_key
                and existing.request_hash == request_hash
            ):
                return existing
            raise ValueError("match run already has a final decision set")
        return self._record_decision_set(
            match_run=match_run,
            draft_version=0,
            decisions=decisions,
            use_assignments=use_assignments,
            relations=relations,
            completion_basis=completion_basis,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            expected_match_run_version=expected_version,
        )

    def _record_decision_set(
        self,
        *,
        match_run: MatchRunSnapshot,
        draft_version: int,
        decisions: tuple[TheoryDecisionCommand, ...],
        use_assignments: tuple[TheoryUseAssignment, ...],
        relations: tuple[TheoryRelationCommand, ...],
        completion_basis: MatchCompletionBasis | None,
        idempotency_key: str | None,
        request_hash: str | None,
        expected_match_run_version: int | None = None,
    ) -> TheoryDecisionSetSnapshot:
        if (
            expected_match_run_version is not None
            and match_run.version != expected_match_run_version
        ):
            raise ValueError("stale match run version")
        if completion_basis is not None and completion_basis is not match_run.completion_basis:
            raise ValueError("match completion basis is stale")
        if (
            match_run.completion_basis is MatchCompletionBasis.PARTIAL
            and not match_run.partial_completion_acknowledged
        ):
            raise ValueError("acknowledge partial completion before recording decisions")
        candidate_by_id = {candidate.candidate_id: candidate for candidate in match_run.candidates}
        if len(candidate_by_id) != len(match_run.candidates):
            raise ValueError("match run contains duplicate candidate IDs")
        if not decisions:
            raise ValueError("at least one theory decision is required")
        records: list[TheoryDecisionRecord] = []
        seen: set[UUID] = set()
        now = datetime.now(UTC)
        for command in decisions:
            candidate = candidate_by_id.get(command.candidate_id)
            if candidate is None:
                raise ValueError("decision candidate is not part of the match run")
            if command.candidate_id in seen:
                raise ValueError("each candidate may have only one final decision")
            if command.candidate_version != candidate.candidate_version:
                raise ValueError("stale candidate version")
            if command.action is None:
                raise ValueError("every candidate needs a final decision action")
            if not command.reason.strip():
                raise ValueError("decision reason is required")
            if not set(command.related_source_ids) <= set(candidate.content.source_ids):
                raise ValueError("decision source IDs must belong to the selected candidate")
            seen.add(command.candidate_id)
            records.append(
                TheoryDecisionRecord(
                    decision_id=self._id_factory(),
                    candidate_id=command.candidate_id,
                    candidate_version=command.candidate_version,
                    action=command.action,
                    reason=command.reason.strip(),
                    related_source_ids=command.related_source_ids,
                    revised_applicability=command.revised_applicability,
                    related_candidate_ids=command.related_candidate_ids,
                    recorded_at=now,
                )
            )
        relation_snapshots = tuple(
            TheoryRelationSnapshot(
                relation_id=self._id_factory(),
                candidate_ids=relation.candidate_ids,
                relation_kind=relation.relation_kind.strip(),
                explanation=relation.explanation.strip(),
                premise_compatibility=relation.premise_compatibility.strip(),
                supporting_evidence=relation.supporting_evidence,
                excluding_evidence=relation.excluding_evidence,
                distinguishing_evidence=relation.distinguishing_evidence,
            )
            for relation in relations
        )
        snapshot = TheoryDecisionSetSnapshot(
            decision_set_id=self._id_factory(),
            match_run_id=match_run.match_run_id,
            version=1,
            decisions=tuple(records),
            use_assignments=use_assignments,
            relations=relation_snapshots,
            recorded_at=now,
            draft_version=draft_version,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        return self._repository.add_decision_set(snapshot)

    @staticmethod
    def _validate_draft_content(
        *,
        match_run: MatchRunSnapshot,
        decisions: tuple[TheoryDecisionCommand, ...],
        use_assignments: tuple[TheoryUseAssignment, ...],
        relations: tuple[TheoryRelationCommand, ...],
    ) -> None:
        candidate_by_id = {candidate.candidate_id: candidate for candidate in match_run.candidates}
        if len(candidate_by_id) != len(match_run.candidates):
            raise ValueError("match run contains duplicate candidate IDs")
        decision_ids: set[UUID] = set()
        for command in decisions:
            candidate = candidate_by_id.get(command.candidate_id)
            if candidate is None:
                raise ValueError("decision candidate is not part of the match run")
            if command.candidate_id in decision_ids:
                raise ValueError("each candidate may have only one draft decision")
            if command.candidate_version != candidate.candidate_version:
                raise ValueError("stale candidate version")
            if not set(command.related_source_ids) <= set(candidate.content.source_ids):
                raise ValueError("decision source IDs must belong to the selected candidate")
            if not set(command.related_candidate_ids) <= set(candidate_by_id):
                raise ValueError("related candidate IDs must belong to the match run")
            decision_ids.add(command.candidate_id)
        assignment_ids: set[UUID] = set()
        for assignment in use_assignments:
            if assignment.candidate_id not in candidate_by_id:
                raise ValueError("theory use assignment candidate is not part of the match run")
            if assignment.candidate_id in assignment_ids:
                raise ValueError("each candidate may have only one theory use assignment")
            assignment_ids.add(assignment.candidate_id)
        for relation in relations:
            if len(set(relation.candidate_ids)) < 2:
                raise ValueError("a theory relation requires at least two candidates")
            if not set(relation.candidate_ids) <= set(candidate_by_id):
                raise ValueError("relation candidate IDs must belong to the match run")

    @staticmethod
    def _validate_draft_partial_acknowledgement(
        *,
        match_run: MatchRunSnapshot,
        acknowledged_candidate_ids: tuple[UUID, ...],
        failed_candidate_ids: tuple[UUID, ...],
        reason: str | None,
    ) -> None:
        if match_run.completion_basis is MatchCompletionBasis.COMPLETE:
            if acknowledged_candidate_ids or failed_candidate_ids or reason:
                raise ValueError("complete match runs do not accept partial acknowledgement data")
            return
        if set(acknowledged_candidate_ids) != {
            candidate.candidate_id for candidate in match_run.candidates
        }:
            raise ValueError("draft acknowledged candidate IDs are stale")
        if set(failed_candidate_ids) != set(match_run.failed_candidate_ids):
            raise ValueError("draft failed candidate IDs are stale")
        normalized_reason = reason.strip() if reason is not None else ""
        if match_run.completion_basis is MatchCompletionBasis.PARTIAL:
            # The reason is itself user-authored draft state. It can be empty while the
            # user is typing, but its candidate/failure scope must already be exact.
            return
        if not normalized_reason:
            raise ValueError("partial completion acknowledgement reason is required")
        if normalized_reason != match_run.partial_completion_acknowledgement_reason:
            raise ValueError("partial completion acknowledgement reason is stale")

    def confirm_plan(
        self,
        *,
        decision_set_id: UUID,
        expected_version: int,
        idempotency_key: str | None = None,
        request_hash: str | None = None,
    ) -> ConfirmedTheoryPlanSnapshot:
        decision_set = self._repository.get_decision_set(decision_set_id)
        if decision_set is None:
            raise LookupError(decision_set_id)
        if decision_set.version != expected_version:
            raise ValueError("stale decision set version")
        if decision_set.draft_version > 0:
            current_draft = self._repository.get_decision_draft(decision_set.match_run_id)
            if current_draft is None or current_draft.version != decision_set.draft_version:
                raise ValueError("theory decision set was superseded by a newer draft")
        existing = self._repository.get_confirmed_plan_for_decision_set(decision_set_id)
        if existing is not None:
            if existing.request_hash == request_hash:
                return existing
            raise ValueError("theory plan was already confirmed with another request")
        match_run = self.get(decision_set.match_run_id)
        existing_for_task = self._repository.get_confirmed_plan_for_task(match_run.task_id)
        if existing_for_task is not None:
            if (
                existing_for_task.decision_set_id == decision_set_id
                and existing_for_task.request_hash == request_hash
            ):
                return existing_for_task
            raise ValueError("research task already has a confirmed theory plan")
        adopted = validate_theory_plan_confirmation(decision_set, match_run.candidates)
        persisted = self._repository.add_confirmed_plan(
            ConfirmedTheoryPlanSnapshot(
                theory_plan_id=self._id_factory(),
                task_id=match_run.task_id,
                match_run_id=match_run.match_run_id,
                decision_set_id=decision_set.decision_set_id,
                version=decision_set.version,
                phenomenon=match_run.phenomenon,
                knowledge_release=match_run.knowledge_release,
                evidence_bundle=match_run.evidence_bundle,
                candidates=tuple(
                    candidate
                    for candidate in match_run.candidates
                    if candidate.candidate_id in adopted
                ),
                decisions=decision_set.decisions,
                use_assignments=decision_set.use_assignments,
                relations=decision_set.relations,
                confirmed_at=datetime.now(UTC),
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
        )
        if persisted.decision_set_id != decision_set_id:
            raise ValueError("research task already has a confirmed theory plan")
        return persisted

    def get_decision_set(self, decision_set_id: UUID) -> TheoryDecisionSetSnapshot:
        snapshot = self._repository.get_decision_set(decision_set_id)
        if snapshot is None:
            raise LookupError(decision_set_id)
        return snapshot

    def get_decision_set_for_match_run(
        self, match_run_id: UUID
    ) -> TheoryDecisionSetSnapshot | None:
        return self._repository.get_decision_set_for_match_run(match_run_id)

    def list_decision_sets(self, match_run_id: UUID) -> tuple[TheoryDecisionSetSnapshot, ...]:
        return self._repository.list_decision_sets(match_run_id)

    def get_confirmed_plan(self, theory_plan_id: UUID) -> ConfirmedTheoryPlanSnapshot:
        snapshot = self._repository.get_confirmed_plan(theory_plan_id)
        if snapshot is None:
            raise LookupError(theory_plan_id)
        return snapshot


def _evidence_applies_to_candidate(item, candidate_source_ids: tuple[str, ...]) -> bool:
    """Project evidence by provenance, not by similarity or candidate score."""

    if item.source is None:
        return True
    return (
        item.source.source_type in {"confirmed_phenomenon_evidence", "personal_research_material"}
        or item.source.source_id in candidate_source_ids
    )
