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
    TheoryCandidateJudge,
    TheoryCandidateSnapshot,
    TheoryDecisionCommand,
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
        phenomenon: ConfirmedPhenomenonSnapshot,
        release: KnowledgeReleaseRef,
    ) -> MatchRunSnapshot:
        evidence_bundle = self._evidence_source.retrieve(
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
                origin=CandidateOrigin.REVIEWED_KNOWLEDGE,
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
                content_status=CandidateContentStatus.REVIEWED,
            )
            for profile in evidence_bundle.theory_profiles
        )
        candidate_ids = tuple(self._id_factory() for _content in contents)
        items = []
        for candidate_id, content in zip(candidate_ids, contents, strict=True):
            candidate_evidence = tuple(
                item
                for item in evidence_bundle.evidence_items
                if item.source is not None and item.source.source_id in content.source_ids
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
        first_result = judgement.results[0] if judgement.results else None
        snapshot = MatchRunSnapshot(
            match_run_id=match_run_id,
            task_id=phenomenon.task_id,
            version=1,
            status=(
                MatchRunStatus.AWAITING_DECISION
                if len(candidates) == len(contents)
                else MatchRunStatus.PARTIAL_FAILURE
            ),
            phenomenon=phenomenon,
            knowledge_release=release,
            evidence_bundle=evidence_bundle,
            candidates=candidates,
            completion_basis=judgement.completion_basis,
            failed_candidate_ids=failed_candidate_ids,
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
        if match_run.version != expected_version:
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
            if not command.reason.strip():
                raise ValueError("decision reason is required")
            if not set(command.related_source_ids) <= set(candidate.content.source_ids):
                raise ValueError(
                    "decision source IDs must belong to the selected candidate"
                )
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
            match_run_id=match_run_id,
            version=1,
            decisions=tuple(records),
            use_assignments=use_assignments,
            relations=relation_snapshots,
            recorded_at=now,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        return self._repository.add_decision_set(snapshot)

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
        existing = self._repository.get_confirmed_plan_for_decision_set(decision_set_id)
        if existing is not None:
            if existing.request_hash == request_hash:
                return existing
            raise ValueError("theory plan was already confirmed with another request")
        match_run = self.get(decision_set.match_run_id)
        adopted = validate_theory_plan_confirmation(decision_set, match_run.candidates)
        return self._repository.add_confirmed_plan(
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

    def get_decision_set(self, decision_set_id: UUID) -> TheoryDecisionSetSnapshot:
        snapshot = self._repository.get_decision_set(decision_set_id)
        if snapshot is None:
            raise LookupError(decision_set_id)
        return snapshot

    def get_decision_set_for_match_run(
        self, match_run_id: UUID
    ) -> TheoryDecisionSetSnapshot | None:
        return self._repository.get_decision_set_for_match_run(match_run_id)

    def list_decision_sets(
        self, match_run_id: UUID
    ) -> tuple[TheoryDecisionSetSnapshot, ...]:
        return self._repository.list_decision_sets(match_run_id)

    def get_confirmed_plan(self, theory_plan_id: UUID) -> ConfirmedTheoryPlanSnapshot:
        snapshot = self._repository.get_confirmed_plan(theory_plan_id)
        if snapshot is None:
            raise LookupError(theory_plan_id)
        return snapshot
