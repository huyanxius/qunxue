from collections.abc import Callable
from uuid import UUID, uuid4

from qunxue_api.modules.knowledge_catalog import KnowledgeReleaseRef
from qunxue_api.modules.research_intake import ConfirmedPhenomenonSnapshot
from qunxue_api.modules.theory_matching.public import (
    CandidateContentStatus,
    CandidateJudgementRunStatus,
    CandidateOrigin,
    EvidenceBundleSnapshot,
    MatchCompletionBasis,
    MatchRunModelSnapshot,
    MatchRunRepository,
    MatchRunSnapshot,
    MatchRunStatus,
    TheoryCandidateContentSnapshot,
    TheoryCandidateJudge,
    TheoryCandidateSnapshot,
    TheoryEvidenceSource,
    TheoryJudgementBatchInput,
    TheoryJudgementBatchItem,
    TheoryJudgementInput,
)


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
        if evidence_bundle.theory_profiles:
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
            and result_by_id[candidate_id].status
            is CandidateJudgementRunStatus.SUCCEEDED
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

    def get(self, match_run_id: UUID) -> MatchRunSnapshot:
        snapshot = self._repository.get(match_run_id)
        if snapshot is None:
            raise LookupError(match_run_id)
        return snapshot
