from dataclasses import dataclass
from uuid import UUID

from qunxue_api.modules.knowledge_catalog import (
    KnowledgeCatalog,
    KnowledgeReleaseLevel,
    KnowledgeUsePurpose,
)
from qunxue_api.modules.research_framework import (
    AuditResolution,
    ConfirmedFrameworkSnapshot,
    FrameworkReviewRunSnapshot,
    FrameworkVersionSnapshot,
    MethodIntentSnapshot,
    ResearchFrameworkDraft,
    ResearchFrameworkDraftInput,
    ResearchFrameworkWorkflow,
)
from qunxue_api.modules.research_intake import ConfirmedPhenomenonSnapshot
from qunxue_api.modules.theory_matching import (
    ConfirmedTheoryPlanSnapshot,
    DeferredTheoryPlanSnapshot,
    MatchCompletionBasis,
    MatchRunSnapshot,
    TheoryDecisionCommand,
    TheoryDecisionSetSnapshot,
    TheoryMatching,
    TheoryRelationCommand,
    TheoryUseAssignment,
)


@dataclass(frozen=True, slots=True)
class ResearchJourneyDependencies:
    knowledge_catalog: KnowledgeCatalog
    theory_matching: TheoryMatching
    research_framework: ResearchFrameworkWorkflow


class ResearchJourneyConfigurationError(ValueError):
    """Composition supplied a release that is not eligible for the requested use."""


class ResearchJourney:
    """主链协调器只编排公开接口，不读取任何模块内部状态。"""

    def __init__(self, dependencies: ResearchJourneyDependencies) -> None:
        self._knowledge_catalog = dependencies.knowledge_catalog
        self._theory_matching = dependencies.theory_matching
        self._research_framework = dependencies.research_framework

    def start_theory_matching(
        self,
        *,
        phenomenon: ConfirmedPhenomenonSnapshot,
    ) -> MatchRunSnapshot:
        release = self._knowledge_catalog.current_release(
            purpose=KnowledgeUsePurpose.MATCH
        )
        if release.level is KnowledgeReleaseLevel.WORKING:
            raise ResearchJourneyConfigurationError(
                "working knowledge releases cannot drive formal theory matching"
            )
        return self._theory_matching.start(
            phenomenon=phenomenon,
            release=release,
        )

    def record_theory_decisions(
        self,
        *,
        match_run_id: UUID,
        expected_version: int,
        completion_basis: MatchCompletionBasis,
        decisions: tuple[TheoryDecisionCommand, ...],
        use_assignments: tuple[TheoryUseAssignment, ...],
        relations: tuple[TheoryRelationCommand, ...],
    ) -> TheoryDecisionSetSnapshot:
        return self._theory_matching.record_decisions(
            match_run_id=match_run_id,
            expected_version=expected_version,
            completion_basis=completion_basis,
            decisions=decisions,
            use_assignments=use_assignments,
            relations=relations,
        )

    def confirm_theory_plan(
        self,
        *,
        decision_set_id: UUID,
        expected_version: int,
    ) -> ConfirmedTheoryPlanSnapshot:
        return self._theory_matching.confirm_plan(
            decision_set_id=decision_set_id,
            expected_version=expected_version,
        )

    def defer_theory_plan(
        self,
        *,
        match_run_id: UUID,
        expected_version: int,
        reason: str,
    ) -> DeferredTheoryPlanSnapshot:
        return self._theory_matching.defer_plan(
            match_run_id=match_run_id,
            expected_version=expected_version,
            reason=reason,
        )

    def create_framework_draft(
        self,
        *,
        theory_plan: ConfirmedTheoryPlanSnapshot,
        original_research_question: str,
        confirmed_research_question: str,
        question_adjustment_reason: str | None,
        research_object: str,
        analysis_unit: str | None,
        context: str | None,
        method_intent: MethodIntentSnapshot,
    ) -> FrameworkVersionSnapshot:
        input_snapshot = ResearchFrameworkDraftInput(
            theory_plan=theory_plan,
            original_research_question=original_research_question,
            confirmed_research_question=confirmed_research_question,
            question_adjustment_reason=question_adjustment_reason,
            research_object=research_object,
            analysis_unit=analysis_unit,
            context=context,
            method_intent=method_intent,
        )
        return self._research_framework.create_draft(input=input_snapshot)

    def start_framework_review(
        self,
        *,
        framework_id: UUID,
        expected_version: int,
    ) -> FrameworkReviewRunSnapshot:
        return self._research_framework.start_review(
            framework_id=framework_id,
            expected_version=expected_version,
        )

    def revise_framework(
        self,
        *,
        framework_id: UUID,
        expected_version: int,
        audit_id: UUID,
        revised_draft: ResearchFrameworkDraft,
        resolutions: tuple[AuditResolution, ...],
        revision_reason: str,
    ) -> FrameworkVersionSnapshot:
        return self._research_framework.revise(
            framework_id=framework_id,
            expected_version=expected_version,
            audit_id=audit_id,
            revised_draft=revised_draft,
            resolutions=resolutions,
            revision_reason=revision_reason,
        )

    def confirm_framework(
        self,
        *,
        framework_id: UUID,
        expected_version: int,
        audit_id: UUID,
        resolutions: tuple[AuditResolution, ...],
    ) -> ConfirmedFrameworkSnapshot:
        return self._research_framework.confirm(
            framework_id=framework_id,
            expected_version=expected_version,
            audit_id=audit_id,
            resolutions=resolutions,
        )
