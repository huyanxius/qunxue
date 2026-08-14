import { apiClient } from '../../api/client'
import { ApiRequestError } from '../../api/error'
import {
  confirmTheoryPlan,
  createMatchRun,
  createTheoryDecisions,
  deferTheoryPlan,
  getMatchRun,
  getResearchTaskNavigation,
  listTheoryDecisions,
  type MatchRunResponse,
  type TheoryCandidateResponse,
  type TheoryDecisionSetResponse,
} from '../../api/generated'
import type {
  ConfirmedTheoryPlan,
  SaveTheoryDecisionsInput,
  SavedDecisionSet,
  TheoryCandidate,
  TheoryWorkspace,
} from './types'

function idempotencyKey() {
  return globalThis.crypto.randomUUID()
}

function candidateOrigin(value: TheoryCandidateResponse['origin']) {
  return {
    reviewed_knowledge: '已审校知识',
    model_exploration: '模型探索',
    external_unreviewed: '外部未审校',
    user_supplied: '用户提供',
  }[value]
}

function toCandidate(response: TheoryCandidateResponse): TheoryCandidate {
  const verified = response.supporting_evidence.filter(
    (item) => item.verification_status === 'verified',
  ).length
  return {
    candidateId: response.candidate_id,
    version: response.version,
    knowledgeId: response.knowledge_id,
    title: response.title,
    originLabel: candidateOrigin(response.origin),
    verificationLabel: verified === response.supporting_evidence.length
      ? '来源已核验'
      : `${verified}/${response.supporting_evidence.length} 条来源已核验`,
    formalAdoptionEligible: response.formal_adoption_eligible,
    adoptionBlockers: response.adoption_blockers,
    problemFocus: response.problem_focus,
    coreClaims: response.core_claims,
    analysisLevels: response.analysis_levels,
    prerequisites: response.prerequisites,
    applicabilityJudgement: response.applicability_judgement,
    applicabilityRationale: response.applicability_rationale,
    supportingEvidence: response.supporting_evidence.map((item) => ({
      evidenceRefId: item.evidence_ref_id,
      sourceId: item.source_id,
      title: item.source?.title ?? item.claim,
      verificationStatus: item.verification_status,
      useBoundary: item.use_boundary,
    })),
    missingEvidence: response.missing_evidence,
    limitations: response.limitations,
    misuseBoundaries: response.misuse_boundaries,
  }
}

function toDecisionSet(response: TheoryDecisionSetResponse): SavedDecisionSet {
  return {
    decisionSetId: response.decision_set_id,
    version: response.version,
    decisions: response.decisions.map((item) => ({
      candidateId: item.candidate_id,
      action: item.action,
      reason: item.reason,
      revisedApplicability: item.revised_applicability,
    })),
    useAssignments: response.use_assignments.map((item) => ({
      candidateId: item.candidate_id,
      roleCode: item.role_code,
      responsibility: item.responsibility,
    })),
    relations: response.relations.map((item) => ({
      candidateIds: item.candidate_ids,
      relationKind: item.relation_kind,
      explanation: item.explanation,
      premiseCompatibility: item.premise_compatibility,
      supportingEvidence: item.supporting_evidence,
      excludingEvidence: item.excluding_evidence,
      distinguishingEvidence: item.distinguishing_evidence,
    })),
  }
}

function toConfirmedPlan(response: NonNullable<Awaited<ReturnType<typeof readDecisions>>['confirmed']>): ConfirmedTheoryPlan {
  return {
    theoryPlanId: response.theory_plan_id,
    adoptedCandidateIds: response.adopted_candidate_ids,
    confirmedAt: response.confirmed_at,
  }
}

async function readDecisions(matchRunId: string, signal?: AbortSignal) {
  const result = await listTheoryDecisions({
    client: apiClient,
    path: { match_run_id: matchRunId },
    signal,
  })
  if (!result.data) throw new ApiRequestError('用户决定恢复失败。', result.response?.status)
  return {
    latest: result.data.decision_sets[0] ?? null,
    confirmed: result.data.confirmed_plan ?? null,
    deferred: result.data.deferred_plan ?? null,
  }
}

async function resolveMatchRun(taskId: string, signal?: AbortSignal): Promise<MatchRunResponse> {
  const navigation = await getResearchTaskNavigation({
    client: apiClient,
    path: { task_id: taskId },
    signal,
  })
  signal?.throwIfAborted()
  if (!navigation.data) throw new ApiRequestError('研究进度恢复失败。', navigation.response?.status)
  if (navigation.data.current_match_run_id) {
    const restored = await getMatchRun({
      client: apiClient,
      path: { match_run_id: navigation.data.current_match_run_id },
      signal,
    })
    signal?.throwIfAborted()
    if (!restored.data) throw new ApiRequestError('候选匹配恢复失败。', restored.response?.status)
    return restored.data
  }
  const phenomenon = navigation.data.phenomenon_summary
  if (!phenomenon) throw new ApiRequestError('请先确认研究现象。')
  const created = await createMatchRun({
    client: apiClient,
    path: { task_id: taskId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: {
      expected_task_version: navigation.data.version,
      phenomenon_query_id: phenomenon.phenomenon_query_id,
      phenomenon_version: phenomenon.version,
      knowledge_release_id: null,
    },
    signal,
  })
  signal?.throwIfAborted()
  if (!created.data) throw new ApiRequestError('理论匹配启动失败。', created.response?.status)
  return created.data
}

export async function restoreTheoryWorkspaceViaApi(
  taskId: string,
  signal?: AbortSignal,
): Promise<TheoryWorkspace> {
  const matchRun = await resolveMatchRun(taskId, signal)
  signal?.throwIfAborted()
  const decisions = await readDecisions(matchRun.match_run_id, signal)
  return {
    taskId,
    matchRunId: matchRun.match_run_id,
    matchRunVersion: matchRun.version,
    knowledgeReleaseId: matchRun.knowledge_release_id,
    status: matchRun.status,
    completionBasis: matchRun.completion_basis,
    candidates: matchRun.candidate_page.candidates.map(toCandidate),
    latestDecisionSet: decisions.latest ? toDecisionSet(decisions.latest) : null,
    confirmedPlan: decisions.confirmed ? toConfirmedPlan(decisions.confirmed) : null,
    deferredPlan: decisions.deferred ? {
      reason: decisions.deferred.reason,
      deferredAt: decisions.deferred.deferred_at,
    } : null,
  }
}

export async function saveTheoryDecisionsViaApi(
  input: SaveTheoryDecisionsInput,
): Promise<SavedDecisionSet> {
  const result = await createTheoryDecisions({
    client: apiClient,
    path: { match_run_id: input.matchRunId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: {
      expected_match_run_version: input.matchRunVersion,
      completion_basis: input.completionBasis,
      decisions: input.decisions.map((item) => ({
        candidate_id: item.candidateId,
        candidate_version: item.candidateVersion,
        action: item.action,
        reason: item.reason,
        related_source_ids: [...item.relatedSourceIds],
        related_candidate_ids: [...item.relatedCandidateIds],
        revised_applicability: item.revisedApplicability,
      })),
      use_assignments: input.useAssignments.map((item) => ({
        candidate_id: item.candidateId,
        role_code: item.roleCode,
        responsibility: item.responsibility,
      })),
      relations: input.relations.map((item) => ({
        candidate_ids: [...item.candidateIds],
        relation_kind: item.relationKind,
        explanation: item.explanation,
        premise_compatibility: item.premiseCompatibility,
        supporting_evidence: [...item.supportingEvidence],
        excluding_evidence: [...item.excludingEvidence],
        distinguishing_evidence: [...item.distinguishingEvidence],
      })),
    },
  })
  if (!result.data) throw new ApiRequestError('用户决定保存失败。', result.response?.status)
  return toDecisionSet(result.data)
}

export async function deferTheoryPlanViaApi(input: {
  matchRunId: string
  matchRunVersion: number
  reason: string
}) {
  const result = await deferTheoryPlan({
    client: apiClient,
    path: { match_run_id: input.matchRunId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: {
      expected_match_run_version: input.matchRunVersion,
      reason: input.reason,
    },
  })
  if (!result.data) throw new ApiRequestError('理论方案暂缓失败。', result.response?.status)
  return { reason: result.data.reason, deferredAt: result.data.deferred_at }
}

export async function confirmTheoryPlanViaApi(input: {
  decisionSetId: string
  version: number
}): Promise<ConfirmedTheoryPlan> {
  const result = await confirmTheoryPlan({
    client: apiClient,
    path: { decision_set_id: input.decisionSetId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: { expected_decision_set_version: input.version },
  })
  if (!result.data) throw new ApiRequestError('理论方案确认失败。', result.response?.status)
  return toConfirmedPlan(result.data)
}
