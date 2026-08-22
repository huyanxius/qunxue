from uuid import UUID

from qunxue_api.modules.theory_matching.public import (
    TheoryCandidateSnapshot,
    TheoryDecisionAction,
    TheoryDecisionSetSnapshot,
    TheoryJudgementVerdict,
    TheoryPlanGateViolation,
)


def validate_theory_plan_confirmation(
    decision_set: TheoryDecisionSetSnapshot,
    candidates: tuple[TheoryCandidateSnapshot, ...],
) -> tuple[UUID, ...]:
    """Return adopted candidates only after the Proposal's human-decision gate passes."""

    violations: list[str] = []
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    if len(candidate_by_id) != len(candidates):
        violations.append("candidate IDs must be unique within one match run")

    action_by_candidate: dict[UUID, TheoryDecisionAction] = {}
    for decision in decision_set.decisions:
        if decision.candidate_id in action_by_candidate:
            violations.append(
                f"candidate {decision.candidate_id} has more than one final decision"
            )
        action_by_candidate[decision.candidate_id] = decision.action

    unknown_candidates = set(action_by_candidate) - set(candidate_by_id)
    if unknown_candidates:
        violations.append("decisions must belong to candidates in the match run")

    missing_decisions = set(candidate_by_id) - set(action_by_candidate)
    if missing_decisions:
        violations.append("every candidate must have a final user decision")

    non_final_actions = {
        TheoryDecisionAction.DEFER,
        TheoryDecisionAction.REQUEST_MORE_EVIDENCE,
        TheoryDecisionAction.REVISE_APPLICABILITY,
    }
    if any(action in non_final_actions for action in action_by_candidate.values()):
        violations.append(
            "deferred decisions, evidence requests, and applicability revisions must "
            "finish before confirmation"
        )

    adopted = tuple(
        candidate_id
        for candidate_id, action in action_by_candidate.items()
        if action in {TheoryDecisionAction.ADOPT, TheoryDecisionAction.COMBINE}
    )
    adopted_set = set(adopted)
    for decision in decision_set.decisions:
        if decision.action is not TheoryDecisionAction.COMBINE:
            continue
        if not decision.related_candidate_ids:
            violations.append("each combined theory must identify related candidates")
            continue
        if not set(decision.related_candidate_ids) <= adopted_set:
            violations.append("combined theories may only reference selected candidates")
    if not adopted:
        violations.append("at least one candidate must be adopted")
    for candidate_id in adopted:
        candidate = candidate_by_id.get(candidate_id)
        if candidate is None:
            continue
        content = candidate.content
        if (
            not content.formal_adoption_eligible
            or content.adoption_blockers
            or (
                content.reviewed_profile is not None
                and not content.reviewed_profile.match_eligible
            )
        ):
            violations.append(
                "every adopted theory must pass formal-adoption eligibility"
            )
        if candidate.judgement.verdict not in {
            TheoryJudgementVerdict.APPLICABLE,
            TheoryJudgementVerdict.CONDITIONAL,
        }:
            violations.append(
                "every adopted theory needs an applicable or conditional judgement"
            )

    assignment_by_candidate = {}
    for assignment in decision_set.use_assignments:
        if assignment.candidate_id in assignment_by_candidate:
            violations.append("each theory may have only one use assignment")
        assignment_by_candidate[assignment.candidate_id] = assignment
    if set(assignment_by_candidate) - set(candidate_by_id):
        violations.append("theory use assignments must belong to matched candidates")
    missing_assignments = set(adopted) - set(assignment_by_candidate)
    if missing_assignments:
        violations.append("every adopted theory must have a role and responsibility")
    if any(
        not assignment_by_candidate[candidate_id].role_code.strip()
        or not assignment_by_candidate[candidate_id].responsibility.strip()
        for candidate_id in adopted
        if candidate_id in assignment_by_candidate
    ):
        violations.append(
            "every adopted theory needs a non-empty role and responsibility"
        )

    if len(adopted) > 1:
        graph = {candidate_id: set() for candidate_id in adopted}
        for relation in decision_set.relations:
            members = adopted_set.intersection(relation.candidate_ids)
            if len(members) < 2:
                continue
            for candidate_id in members:
                graph[candidate_id].update(members - {candidate_id})
            if not (
                relation.relation_kind.strip()
                and relation.explanation.strip()
                and relation.premise_compatibility.strip()
            ):
                violations.append(
                    "each multi-theory relation needs a kind, explanation, and "
                    "premise-compatibility statement"
                )
            if not (
                relation.supporting_evidence
                and relation.excluding_evidence
                and relation.distinguishing_evidence
            ):
                violations.append(
                    "each multi-theory relation needs supporting, excluding, and "
                    "distinguishing evidence requirements"
                )

        visited: set[UUID] = set()
        pending = [adopted[0]]
        while pending:
            candidate_id = pending.pop()
            if candidate_id in visited:
                continue
            visited.add(candidate_id)
            pending.extend(graph[candidate_id] - visited)
        if visited != adopted_set:
            violations.append(
                "all adopted theories must be connected by explained relations"
            )

    if violations:
        raise TheoryPlanGateViolation(tuple(dict.fromkeys(violations)))
    return adopted
