from qunxue_api.api.contracts.matching import (
    ConfirmedTheoryPlanResponse,
    TheoryDecisionRecordResponse,
    TheoryPlanAction,
    TheoryRelationResponse,
    TheoryUseAssignmentResponse,
)
from qunxue_api.api.contracts.phenomena import (
    PhenomenonEvidenceReferenceResponse,
    PhenomenonSnapshotAction,
    PhenomenonSnapshotResponse,
)
from qunxue_api.modules.theory_matching import ConfirmedTheoryPlanSnapshot


def confirmed_theory_plan_response(
    plan: ConfirmedTheoryPlanSnapshot,
) -> ConfirmedTheoryPlanResponse:
    phenomenon = plan.phenomenon
    return ConfirmedTheoryPlanResponse(
        theory_plan_id=plan.theory_plan_id,
        task_id=plan.task_id,
        match_run_id=plan.match_run_id,
        decision_set_id=plan.decision_set_id,
        version=plan.version,
        allowed_actions=[TheoryPlanAction.CREATE_FRAMEWORK],
        phenomenon_query_id=phenomenon.phenomenon_query_id,
        phenomenon_version=phenomenon.version,
        knowledge_release_id=plan.knowledge_release.knowledge_release_id,
        adopted_candidate_ids=[
            assignment.candidate_id for assignment in plan.use_assignments
        ],
        confirmed_phenomenon=PhenomenonSnapshotResponse(
            phenomenon_query_id=phenomenon.phenomenon_query_id,
            task_id=phenomenon.task_id,
            version=phenomenon.version,
            status="confirmed",
            allowed_actions=[PhenomenonSnapshotAction.START_MATCHING],
            phenomenon=phenomenon.phenomenon,
            research_intent=phenomenon.research_intent,
            context=phenomenon.context,
            content_hash=phenomenon.content_hash,
            source_ref_ids=[item.source_ref_id for item in phenomenon.evidence_refs],
            evidence_refs=[
                PhenomenonEvidenceReferenceResponse(
                    evidence_ref_id=item.evidence_ref_id,
                    excerpt=item.excerpt,
                    source_ref_id=item.source_ref_id,
                    source_description=item.source_description,
                    locator=item.locator,
                    verification_status=item.verification_status,
                    use_boundary=item.use_boundary,
                )
                for item in phenomenon.evidence_refs
            ],
            confirmed_at=plan.confirmed_at,
        ),
        decisions=[
            TheoryDecisionRecordResponse(
                decision_id=item.decision_id,
                candidate_id=item.candidate_id,
                candidate_version=item.candidate_version,
                action=item.action,
                reason=item.reason,
                related_source_ids=list(item.related_source_ids),
                related_candidate_ids=list(item.related_candidate_ids),
                revised_applicability=item.revised_applicability,
                recorded_at=item.recorded_at,
            )
            for item in plan.decisions
        ],
        use_assignments=[
            TheoryUseAssignmentResponse(
                candidate_id=item.candidate_id,
                role_code=item.role_code,
                responsibility=item.responsibility,
            )
            for item in plan.use_assignments
        ],
        relations=[
            TheoryRelationResponse(
                relation_id=item.relation_id,
                candidate_ids=list(item.candidate_ids),
                relation_kind=item.relation_kind,
                explanation=item.explanation,
                premise_compatibility=item.premise_compatibility,
                supporting_evidence=list(item.supporting_evidence),
                excluding_evidence=list(item.excluding_evidence),
                distinguishing_evidence=list(item.distinguishing_evidence),
            )
            for item in plan.relations
        ],
        confirmed_at=plan.confirmed_at,
    )
