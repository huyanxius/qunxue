import {
  acknowledgePartialMatch,
  confirmTheoryPlan,
  createMatchRun,
  createTheoryDecisions,
  getConfirmedTheoryPlan,
  getMatchRun,
  getTheoryDecisionDraft,
  listTheoryDecisions,
  retryMatchCandidate,
  saveTheoryDecisionDraft,
  type ConfirmedTheoryPlanResponse,
  type ErrorResponse,
  type EvidenceReferenceResponse,
  type MatchRunResponse,
  type TheoryCandidateResponse,
  type TheoryDecisionDraftInput,
  type TheoryDecisionDraftResponse,
  type TheoryDecisionInput,
  type TheoryDecisionSetResponse,
  type TheoryRelationInput,
  type TheoryUseAssignmentInput,
} from '../../api/generated'
import { apiClient } from '../../api/client'
import {
  M4TheoryJudgmentFailure,
  type M4Candidate,
  type M4ConfirmedPlan,
  type M4DecisionDraft,
  type M4DraftDecision,
  type M4Evidence,
  type M4FailedCandidate,
  type M4MatchRun,
  type M4TaskContract,
  type M4TheoryJudgmentGateway,
  type M4Workspace,
} from './M4TheoryJudgment'

export interface M4TheoryJudgmentTransport {
  readonly acknowledgePartialMatch: typeof acknowledgePartialMatch
  readonly confirmTheoryPlan: typeof confirmTheoryPlan
  readonly createMatchRun: typeof createMatchRun
  readonly createTheoryDecisions: typeof createTheoryDecisions
  readonly getConfirmedTheoryPlan: typeof getConfirmedTheoryPlan
  readonly getMatchRun: typeof getMatchRun
  readonly getTheoryDecisionDraft: typeof getTheoryDecisionDraft
  readonly listTheoryDecisions: typeof listTheoryDecisions
  readonly retryMatchCandidate: typeof retryMatchCandidate
  readonly saveTheoryDecisionDraft: typeof saveTheoryDecisionDraft
}

const generatedTransport: M4TheoryJudgmentTransport = {
  acknowledgePartialMatch,
  confirmTheoryPlan,
  createMatchRun,
  createTheoryDecisions,
  getConfirmedTheoryPlan,
  getMatchRun,
  getTheoryDecisionDraft,
  listTheoryDecisions,
  retryMatchCandidate,
  saveTheoryDecisionDraft,
}

interface Result<T> {
  readonly data?: T
  readonly error?: unknown
  readonly response?: { readonly status: number }
}

function errorDetail(error: unknown) {
  if (!error || typeof error !== 'object' || !('error' in error)) return null
  const detail = (error as ErrorResponse).error
  return detail && typeof detail.code === 'string' && typeof detail.message === 'string' ? detail : null
}

function requestFailure(result: Result<unknown>, fallback: string) {
  const detail = errorDetail(result.error)
  const status = result.response?.status
  if (detail?.code === 'catalog_not_ready') return new M4TheoryJudgmentFailure('catalog_not_ready', detail.message)
  if (detail?.code === 'model_timeout' || detail?.code === 'insufficient_sources') return new M4TheoryJudgmentFailure('model_failed', detail.message)
  if (status === 404 || detail?.code === 'not_found') return new M4TheoryJudgmentFailure('not_found', detail?.message ?? fallback)
  if (status === 409 || detail?.code === 'validation_error') return new M4TheoryJudgmentFailure('conflict', detail?.message ?? fallback)
  return new M4TheoryJudgmentFailure('unknown', detail?.message ?? fallback)
}

function thrownFailure(reason: unknown) {
  if (reason instanceof M4TheoryJudgmentFailure) return reason
  if (reason instanceof TypeError) return new M4TheoryJudgmentFailure('network', '网络中断；如果正在编辑，请保持本页打开并在恢复连接后重试保存。')
  return new M4TheoryJudgmentFailure('unknown', reason instanceof Error ? reason.message : '理论判断请求未完成。')
}

function requireData<T>(result: Result<T>, fallback: string): T {
  if (result.data !== undefined) return result.data
  throw requestFailure(result, fallback)
}

function evidence(item: EvidenceReferenceResponse): M4Evidence {
  return {
    evidenceRefId: item.evidence_ref_id,
    claim: item.claim,
    excerpt: item.excerpt,
    locator: item.locator ?? item.source?.locator ?? null,
    sourceId: item.source_id ?? item.source?.source_id ?? null,
    sourceTitle: item.source?.title ?? null,
    sourceUrl: item.source?.url ?? null,
    verificationStatus: item.verification_status,
    useBoundary: item.use_boundary,
  }
}

const PRE_REVIEW_COMPLETED = 'pre_review_completed' as const

function reviewStatus(
  contentStatus: TheoryCandidateResponse['content_status'] | typeof PRE_REVIEW_COMPLETED,
): M4Candidate['reviewStatus'] {
  return contentStatus === PRE_REVIEW_COMPLETED ? PRE_REVIEW_COMPLETED : null
}

function candidate(item: TheoryCandidateResponse): M4Candidate {
  const verdict = item.applicability_judgement === 'conditional'
    ? 'partially_applicable'
    : item.applicability_judgement === 'insufficient'
      ? 'insufficient_evidence'
      : item.applicability_judgement
  return {
    candidateId: item.candidate_id,
    version: item.version,
    title: item.title,
    problemFocus: item.problem_focus,
    coreClaims: item.core_claims,
    analysisLevels: item.analysis_levels,
    prerequisites: item.prerequisites,
    applicabilityJudgement: verdict,
    applicabilityRationale: item.applicability_rationale,
    supportingEvidence: item.supporting_evidence.map(evidence),
    conflictingEvidence: item.conflicting_evidence.map(evidence),
    missingEvidence: item.missing_evidence,
    requestedMaterial: item.requested_material,
    limitations: item.limitations,
    misuseBoundaries: item.misuse_boundaries,
    competingTheories: item.competing_theories.map((theory) => ({ theoryId: theory.theory_id, title: theory.title, explanation: theory.relation_explanation })),
    complementaryTheories: item.complementary_theories.map((theory) => ({ theoryId: theory.theory_id, title: theory.title, explanation: theory.relation_explanation })),
    sourceIds: item.source_ids,
    reviewStatus: reviewStatus(item.content_status),
    formalAdoptionEligible: item.formal_adoption_eligible,
    adoptionBlockers: item.adoption_blockers,
    modelLabel: `${item.model.provider} · ${item.model.model_version}`,
    modelTraceId: item.model.trace.trace_id,
  }
}

type FailedCandidateWithProvenance = M4FailedCandidate & {
  readonly attempt: number
  readonly traceId: string
  readonly requestId: string
}

function matchRun(response: MatchRunResponse): M4MatchRun {
  return {
    matchRunId: response.match_run_id,
    taskId: response.task_id,
    version: response.version,
    status: response.status,
    knowledgeReleaseId: response.knowledge_release_id,
    completionBasis: response.completion_basis,
    partialCompletionAcknowledged: response.partial_completion_acknowledged,
    failedCandidates: response.failed_candidates.map((item): FailedCandidateWithProvenance => ({
      candidateId: item.candidate_id,
      version: item.version,
      title: item.title,
      failureCode: item.failure_code,
      retryable: item.retryable,
      attempt: item.attempt,
      traceId: item.trace_id,
      requestId: item.request_id,
    })),
    candidates: response.candidate_page.candidates.map(candidate),
  }
}

function draftDecision(
  item: TheoryDecisionDraftInput,
  assignments: readonly TheoryUseAssignmentInput[],
): M4DraftDecision {
  const assignment = assignments.find((value) => value.candidate_id === item.candidate_id)
  return {
    candidateId: item.candidate_id,
    candidateVersion: item.candidate_version,
    action: item.action ?? null,
    reason: item.reason ?? '',
    roleCode: assignment?.role_code ?? 'secondary',
    responsibility: assignment?.responsibility ?? '',
    relatedSourceIds: item.related_source_ids ?? [],
    revisedApplicability: item.revised_applicability ?? '',
  }
}

function decisionDraft(response: TheoryDecisionDraftResponse): M4DecisionDraft {
  const relation = response.relations[0]
  return {
    matchRunId: response.match_run_id,
    version: response.version,
    updatedAt: response.updated_at,
    partialAcknowledgementReason: response.partial_completion_acknowledgement_reason ?? '',
    decisions: response.decisions.map((item) => draftDecision(item, response.use_assignments)),
    relation: {
      explanation: relation?.explanation ?? '',
      premiseCompatibility: relation?.premise_compatibility ?? '',
      supportingEvidence: relation?.supporting_evidence.join('\n') ?? '',
      excludingEvidence: relation?.excluding_evidence.join('\n') ?? '',
      distinguishingEvidence: relation?.distinguishing_evidence.join('\n') ?? '',
    },
  }
}

function emptyDraft(run: M4MatchRun): M4DecisionDraft {
  return {
    matchRunId: run.matchRunId,
    version: 0,
    updatedAt: '',
    partialAcknowledgementReason: '',
    decisions: [],
    relation: { explanation: '', premiseCompatibility: '', supportingEvidence: '', excludingEvidence: '', distinguishingEvidence: '' },
  }
}

function decisionSet(response: TheoryDecisionSetResponse) {
  return {
    decisionSetId: response.decision_set_id,
    version: response.version,
    canConfirm: response.allowed_actions.includes('confirm_theory_plan'),
    knowledgeReleaseId: response.knowledge_release_id,
  }
}

function confirmed(response: ConfirmedTheoryPlanResponse): M4ConfirmedPlan {
  return {
    theoryPlanId: response.theory_plan_id,
    taskId: response.task_id,
    matchRunId: response.match_run_id,
    decisionSetId: response.decision_set_id,
    knowledgeReleaseId: response.knowledge_release_id,
    confirmedAt: response.confirmed_at,
  }
}

function lines(value: string) {
  return value.split('\n').map((item) => item.trim()).filter(Boolean)
}

function adoptedIds(draft: M4DecisionDraft) {
  return draft.decisions.filter((item) => item.action === 'adopt' || item.action === 'combine').map((item) => item.candidateId)
}

function decisionInputs(draft: M4DecisionDraft): TheoryDecisionInput[] {
  const adopted = adoptedIds(draft)
  return draft.decisions.flatMap((item) => item.action ? [{
    candidate_id: item.candidateId,
    candidate_version: item.candidateVersion,
    action: item.action,
    reason: item.reason,
    related_source_ids: [...item.relatedSourceIds],
    related_candidate_ids: item.action === 'combine' ? adopted.filter((id) => id !== item.candidateId) : [],
    revised_applicability: item.revisedApplicability.trim() || null,
  }] : [])
}

function draftInputs(draft: M4DecisionDraft): TheoryDecisionDraftInput[] {
  const adopted = adoptedIds(draft)
  return draft.decisions.map((item) => ({
    candidate_id: item.candidateId,
    candidate_version: item.candidateVersion,
    action: item.action,
    reason: item.reason,
    related_source_ids: [...item.relatedSourceIds],
    related_candidate_ids: item.action === 'combine' ? adopted.filter((id) => id !== item.candidateId) : [],
    revised_applicability: item.revisedApplicability.trim() || null,
  }))
}

function assignments(draft: M4DecisionDraft): TheoryUseAssignmentInput[] {
  return draft.decisions.filter((item) => item.action === 'adopt' || item.action === 'combine').map((item) => ({
    candidate_id: item.candidateId,
    role_code: item.roleCode,
    responsibility: item.responsibility,
  }))
}

function relations(draft: M4DecisionDraft): TheoryRelationInput[] {
  const ids = adoptedIds(draft)
  if (ids.length < 2) return []
  return [{
    candidate_ids: ids,
    relation_kind: 'complementary',
    explanation: draft.relation.explanation,
    premise_compatibility: draft.relation.premiseCompatibility,
    supporting_evidence: lines(draft.relation.supportingEvidence),
    excluding_evidence: lines(draft.relation.excludingEvidence),
    distinguishing_evidence: lines(draft.relation.distinguishingEvidence),
  }]
}

export function createM4TheoryJudgmentGateway(transport: M4TheoryJudgmentTransport = generatedTransport): M4TheoryJudgmentGateway {
  const cachedRuns = new Map<string, MatchRunResponse>()

  async function request<T>(operation: () => PromiseLike<Result<T>>, fallback: string) {
    try {
      return requireData(await operation(), fallback)
    } catch (reason) {
      throw thrownFailure(reason)
    }
  }

  async function fetchRawRun(matchRunId: string) {
    const response = await request(
      () => transport.getMatchRun({ client: apiClient, path: { match_run_id: matchRunId } }),
      '理论匹配记录恢复失败。',
    )
    cachedRuns.set(response.match_run_id, response)
    return response
  }

  async function rawRun(matchRunId: string) {
    return cachedRuns.get(matchRunId) ?? fetchRawRun(matchRunId)
  }

  async function assemble(response: MatchRunResponse, taskContract: M4TaskContract): Promise<M4Workspace> {
    try {
      cachedRuns.set(response.match_run_id, response)
      const [draftResult, decisionsResponse, planResponse] = await Promise.all([
      transport.getTheoryDecisionDraft({ client: apiClient, path: { match_run_id: response.match_run_id } }),
      request(
        () => transport.listTheoryDecisions({ client: apiClient, path: { match_run_id: response.match_run_id }, query: { limit: 20 } }),
        '理论决定恢复失败。',
      ),
      taskContract.theoryPlanId
        ? request(
          () => transport.getConfirmedTheoryPlan({ client: apiClient, path: { theory_plan_id: taskContract.theoryPlanId! } }),
          '已确认理论方案恢复失败。',
        )
        : Promise.resolve(null),
      ])
      let restoredDraft: M4DecisionDraft
      if (draftResult.data) restoredDraft = decisionDraft(draftResult.data)
      else if (draftResult.response?.status === 404) restoredDraft = emptyDraft(matchRun(response))
      else throw requestFailure(draftResult, '理论决定草稿恢复失败。')
      return {
        matchRun: matchRun(response),
        draft: restoredDraft,
        decisionSet: decisionsResponse.decision_sets[0] ? decisionSet(decisionsResponse.decision_sets[0]) : null,
        confirmedPlan: planResponse ? confirmed(planResponse) : null,
      }
    } catch (reason) {
      throw thrownFailure(reason)
    }
  }

  async function refreshWorkspace(matchRunId: string) {
    const response = await fetchRawRun(matchRunId)
    return assemble(response, {
      taskId: response.task_id,
      taskVersion: 1,
      matchRunId,
      theoryPlanId: null,
      phenomenonQueryId: response.phenomenon_query_id,
      phenomenonVersion: response.phenomenon_version,
      canStartMatching: false,
    })
  }

  return {
    async start({ task: taskContract, idempotencyKey }) {
      if (!taskContract.phenomenonQueryId || taskContract.phenomenonVersion === null) {
        throw new M4TheoryJudgmentFailure('conflict', '这项研究还没有已确认现象。')
      }
      try {
        const response = requireData(await transport.createMatchRun({
          client: apiClient,
          path: { task_id: taskContract.taskId },
          headers: { 'Idempotency-Key': idempotencyKey },
          body: {
            expected_task_version: taskContract.taskVersion,
            phenomenon_query_id: taskContract.phenomenonQueryId,
            phenomenon_version: taskContract.phenomenonVersion,
            knowledge_release_id: null,
          },
        }), '理论匹配启动失败。')
        return await assemble(response, { ...taskContract, matchRunId: response.match_run_id })
      } catch (reason) {
        throw thrownFailure(reason)
      }
    },

    async restore({ task: taskContract }) {
      if (!taskContract.matchRunId) throw new M4TheoryJudgmentFailure('not_found', '这项研究还没有理论匹配记录。')
      const response = await fetchRawRun(taskContract.matchRunId)
      return assemble(response, taskContract)
    },

    async saveDraft({ matchRunId, expectedVersion, draft, idempotencyKey }) {
      const response = await rawRun(matchRunId)
      const isPartial = response.completion_basis !== 'complete'
      const acknowledged = isPartial
        ? response.candidate_page.candidates.map((item) => item.candidate_id)
        : []
      const result = await transport.saveTheoryDecisionDraft({
        client: apiClient,
        path: { match_run_id: matchRunId },
        headers: { 'Idempotency-Key': idempotencyKey },
        body: {
          expected_match_run_version: response.version,
          expected_draft_version: expectedVersion,
          completion_basis: response.completion_basis,
          decisions: draftInputs(draft),
          use_assignments: assignments(draft),
          relations: relations(draft),
          acknowledged_candidate_ids: acknowledged,
          failed_candidate_ids: isPartial ? response.failed_candidate_ids : [],
          partial_completion_acknowledgement_reason: draft.partialAcknowledgementReason.trim() || null,
        },
      })
      if (result.data) return decisionDraft(result.data)
      if (result.response?.status === 409) {
        try {
          const latest = await refreshWorkspace(matchRunId)
          throw new M4TheoryJudgmentFailure('draft_conflict', errorDetail(result.error)?.message ?? '草稿版本冲突。', { workspace: latest })
        } catch (reason) {
          if (reason instanceof M4TheoryJudgmentFailure && reason.code === 'draft_conflict') throw reason
        }
        throw new M4TheoryJudgmentFailure('draft_conflict', errorDetail(result.error)?.message ?? '草稿版本冲突。')
      }
      throw requestFailure(result, '理论决定草稿保存失败。')
    },

    async retryCandidate({ matchRunId, matchRunVersion, candidateId, candidateVersion, idempotencyKey }) {
      try {
        const response = requireData(await transport.retryMatchCandidate({
          client: apiClient,
          path: { match_run_id: matchRunId, candidate_id: candidateId },
          headers: { 'Idempotency-Key': idempotencyKey },
          body: { expected_match_run_version: matchRunVersion, expected_candidate_version: candidateVersion },
        }), '候选理论重试失败。')
        return await assemble(response, { taskId: response.task_id, taskVersion: 1, matchRunId, theoryPlanId: null, phenomenonQueryId: response.phenomenon_query_id, phenomenonVersion: response.phenomenon_version, canStartMatching: false })
      } catch (reason) {
        throw thrownFailure(reason)
      }
    },

    async acknowledgePartial({ matchRunId, matchRunVersion, failedCandidateIds, acknowledgedCandidateIds, reason, idempotencyKey }) {
      try {
        const response = requireData(await transport.acknowledgePartialMatch({
          client: apiClient,
          path: { match_run_id: matchRunId },
          headers: { 'Idempotency-Key': idempotencyKey },
          body: { expected_version: matchRunVersion, failed_candidate_ids: [...failedCandidateIds], acknowledged_candidate_ids: [...acknowledgedCandidateIds], reason },
        }), '部分完成风险确认失败。')
        return await assemble(response, { taskId: response.task_id, taskVersion: 1, matchRunId, theoryPlanId: null, phenomenonQueryId: response.phenomenon_query_id, phenomenonVersion: response.phenomenon_version, canStartMatching: false })
      } catch (caught) {
        throw thrownFailure(caught)
      }
    },

    async createDecisionSet({ matchRun: run, draft, idempotencyKey }) {
      const response = await request(
        () => transport.createTheoryDecisions({
          client: apiClient,
          path: { match_run_id: run.matchRunId },
          headers: { 'Idempotency-Key': idempotencyKey },
          body: {
            expected_match_run_version: run.version,
            expected_draft_version: draft.version,
            completion_basis: run.completionBasis,
            decisions: decisionInputs(draft),
            use_assignments: assignments(draft),
            relations: relations(draft),
          },
        }),
        '完整理论决定保存失败。',
      )
      return decisionSet(response)
    },

    async confirmPlan({ decisionSetId, expectedVersion, idempotencyKey }) {
      const response = await request(
        () => transport.confirmTheoryPlan({
          client: apiClient,
          path: { decision_set_id: decisionSetId },
          headers: { 'Idempotency-Key': idempotencyKey },
          body: { expected_decision_set_version: expectedVersion },
        }),
        '理论方案确认失败。',
      )
      return confirmed(response)
    },
  }
}
