import { describe, expect, it, vi } from 'vitest'

import type { M4DecisionDraft, M4TaskContract } from './M4TheoryJudgment'
import { createM4TheoryJudgmentGateway, type M4TheoryJudgmentTransport } from './m4TheoryJudgmentApi'

const task: M4TaskContract = {
  taskId: 'task-1',
  taskVersion: 7,
  matchRunId: 'match-1',
  theoryPlanId: 'plan-1',
  phenomenonQueryId: 'phenomenon-1',
  phenomenonVersion: 2,
  canStartMatching: false,
}

const model = {
  capability: 'base' as const,
  degraded: false,
  knowledge_release_id: 'release-final-1',
  model_version: 'production-v2',
  provider: 'Qwen',
  trace: { contract_version: 'matching/v1', request_id: 'request-1', trace_id: 'trace-1' },
}

const source = {
  source_id: 'source-1',
  source_type: 'book',
  title: '社区关系与时间压力',
  authors_or_institution: ['张某'],
  year: 2025,
  publication: '社会学研究',
  locator: '第 3 章，p. 47',
  url: 'https://example.org/source-1',
  verification_status: 'verified' as const,
  use_boundary: '只支持关联，不证明因果。',
}

const evidence = {
  evidence_ref_id: 'evidence-1',
  claim: '时间紧缩会挤压互助。',
  excerpt: '下班后无法参与社区互助。',
  locator: '第 3 章，p. 47',
  source_id: 'source-1',
  source,
  verification_status: 'verified' as const,
  use_boundary: '只支持关联，不证明因果。',
}

const matchRun = {
  match_run_id: 'match-1',
  task_id: 'task-1',
  version: 6,
  status: 'partial_failure',
  allowed_actions: ['retry_candidate', 'acknowledge_partial_completion', 'refresh'],
  completion_basis: 'partial',
  partial_completion_acknowledged: false,
  total_candidate_count: 3,
  completed_candidate_count: 2,
  failed_candidate_count: 1,
  failed_candidate_ids: ['candidate-2'],
  failed_candidates: [{ candidate_id: 'candidate-2', version: 2, title: '社会资本理论', judgement_run_status: 'timed_out', failure_code: 'model_timeout', retryable: true, attempt: 2, trace_id: 'failed-trace-2', request_id: 'failed-request-2' }],
  phenomenon_query_id: 'phenomenon-1',
  phenomenon_version: 2,
  knowledge_release_id: 'release-final-1',
  model,
  candidate_page: {
    match_run_id: 'match-1',
    version: 6,
    allowed_actions: ['retry_candidate', 'acknowledge_partial_completion', 'refresh'],
    knowledge_release_id: 'release-final-1',
    stable_order: ['candidate-1', 'candidate-3', 'candidate-2'],
    next_cursor: null,
    candidates: [{
      candidate_id: 'candidate-1',
      version: 3,
      allowed_actions: ['create_decision'],
      judgement_run_status: 'succeeded',
      knowledge_release_id: 'release-final-1',
      knowledge_id: 'D1:C001',
      theory_id: 'theory-1',
      seed_theory_id: null,
      origin: 'reviewed_knowledge',
      content_status: 'pre_review_completed',
      title: '时间贫困理论',
      problem_focus: '时间资源分配如何改变关系维护。',
      core_claims: ['可支配时间受制度影响。'],
      analysis_levels: ['个体', '社区'],
      prerequisites: ['互助需要时间投入。'],
      applicability_judgement: 'conditional',
      applicability_rationale: '已观察到工时与互助同向变化。',
      supporting_evidence: [evidence],
      conflicting_evidence: [{ ...evidence, evidence_ref_id: 'evidence-2', claim: '长工时居民仍可能高频互助。' }],
      missing_evidence: ['个体时间日志。'],
      requested_material: ['两周时间日志。'],
      limitations: ['不能单独解释互惠规范。'],
      misuse_boundaries: ['不应归因为个人时间管理。'],
      competing_theories: [{ theory_id: 'theory-2', title: '社会资本理论', relation_explanation: '网络弱化是竞争解释。' }],
      complementary_theories: [{ theory_id: 'theory-3', title: '互惠规范理论', relation_explanation: '补充解释行动意愿。' }],
      source_ids: ['source-1'],
      formal_adoption_eligible: true,
      adoption_blockers: [],
      model,
    }],
  },
}

matchRun.candidate_page.candidates.push({
  ...matchRun.candidate_page.candidates[0],
  candidate_id: 'candidate-3',
  theory_id: 'theory-3',
  knowledge_id: 'D1:C003',
  title: '互惠规范理论',
  source_ids: ['source-1'],
})

const draftResponse = {
  draft_id: 'draft-1',
  match_run_id: 'match-1',
  version: 4,
  expected_match_run_version: 6,
  completion_basis: 'partial',
  decisions: [{ candidate_id: 'candidate-1', candidate_version: 3, action: 'combine', reason: '用于解释时间约束。', related_source_ids: ['source-1'], related_candidate_ids: ['candidate-3'], revised_applicability: null }, { candidate_id: 'candidate-3', candidate_version: 3, action: 'combine', reason: '用于解释行动意愿。', related_source_ids: ['source-1'], related_candidate_ids: ['candidate-1'], revised_applicability: null }],
  use_assignments: [{ candidate_id: 'candidate-1', role_code: 'primary', responsibility: '解释时间约束。' }, { candidate_id: 'candidate-3', role_code: 'secondary', responsibility: '解释互惠意愿。' }],
  relations: [{ candidate_ids: ['candidate-1', 'candidate-3'], relation_kind: 'complementary', explanation: '共同解释。', premise_compatibility: '前提兼容。', supporting_evidence: ['支持 A', '支持 B'], excluding_evidence: ['排除 A'], distinguishing_evidence: ['区分 A'] }],
  acknowledged_candidate_ids: ['candidate-1'],
  failed_candidate_ids: ['candidate-2'],
  partial_completion_acknowledgement_reason: '先使用已完成候选。',
  updated_at: '2026-08-22T08:01:00Z',
}

const decisionPage = {
  match_run_id: 'match-1',
  version: 6,
  allowed_actions: ['confirm_theory_plan'],
  knowledge_release_id: 'release-final-1',
  decision_sets: [{ decision_set_id: 'decision-set-1', match_run_id: 'match-1', version: 2, draft_version: 4, allowed_actions: ['confirm_theory_plan'], knowledge_release_id: 'release-final-1', completion_basis: 'partial_with_user_ack', decisions: [], use_assignments: [], relations: [] }],
  next_cursor: null,
}

const confirmedPlan = {
  theory_plan_id: 'plan-1',
  task_id: 'task-1',
  match_run_id: 'match-1',
  decision_set_id: 'decision-set-1',
  version: 1,
  allowed_actions: ['create_framework'],
  knowledge_release_id: 'release-final-1',
  phenomenon_query_id: 'phenomenon-1',
  phenomenon_version: 2,
  confirmed_phenomenon: { phenomenon_query_id: 'phenomenon-1', version: 2, phenomenon: '社区互助减少。', research_intent: '理解时间约束。', context: '某社区', evidence_refs: [], confirmed_at: '2026-08-22T07:00:00Z', content_hash: 'hash-1' },
  adopted_candidate_ids: ['candidate-1'],
  decisions: [],
  use_assignments: [],
  relations: [],
  confirmed_at: '2026-08-22T08:02:00Z',
}

function ok<T>(data: T) {
  return Promise.resolve({ data, error: undefined, request: new Request('http://localhost'), response: new Response() })
}

function failed(status: number, error: { readonly error: { readonly code: string; readonly message: string; readonly trace_id: string } }) {
  return Promise.resolve({ data: undefined, error, request: new Request('http://localhost'), response: new Response(JSON.stringify(error), { status }) })
}

function transport(overrides: Partial<M4TheoryJudgmentTransport> = {}): M4TheoryJudgmentTransport {
  return {
    createMatchRun: vi.fn().mockImplementation(() => ok(matchRun)),
    getMatchRun: vi.fn().mockImplementation(() => ok(matchRun)),
    getTheoryDecisionDraft: vi.fn().mockImplementation(() => ok(draftResponse)),
    saveTheoryDecisionDraft: vi.fn().mockImplementation(() => ok(draftResponse)),
    listTheoryDecisions: vi.fn().mockImplementation(() => ok(decisionPage)),
    retryMatchCandidate: vi.fn().mockImplementation(() => ok(matchRun)),
    acknowledgePartialMatch: vi.fn().mockImplementation(() => ok(matchRun)),
    createTheoryDecisions: vi.fn().mockImplementation(() => ok(decisionPage.decision_sets[0])),
    confirmTheoryPlan: vi.fn().mockImplementation(() => ok(confirmedPlan)),
    getConfirmedTheoryPlan: vi.fn().mockImplementation(() => ok(confirmedPlan)),
    ...overrides,
  } as unknown as M4TheoryJudgmentTransport
}

describe('m4TheoryJudgmentApi', () => {
  it('restores full candidate, failure, release, draft, decision, and confirmed-plan provenance', async () => {
    const api = transport()
    const gateway = createM4TheoryJudgmentGateway(api)

    const restored = await gateway.restore({ task })

    expect(restored.matchRun).toEqual(expect.objectContaining({ matchRunId: 'match-1', taskId: 'task-1', version: 6, status: 'partial_failure', knowledgeReleaseId: 'release-final-1' }))
    expect(restored.matchRun.candidates[0]).toEqual(expect.objectContaining({
      title: '时间贫困理论',
      applicabilityJudgement: 'partially_applicable',
      prerequisites: ['互助需要时间投入。'],
      conflictingEvidence: [expect.objectContaining({ claim: '长工时居民仍可能高频互助。', locator: '第 3 章，p. 47', sourceTitle: '社区关系与时间压力', sourceUrl: 'https://example.org/source-1' })],
      missingEvidence: ['个体时间日志。'],
      limitations: ['不能单独解释互惠规范。'],
      misuseBoundaries: ['不应归因为个人时间管理。'],
      competingTheories: [{ theoryId: 'theory-2', title: '社会资本理论', explanation: '网络弱化是竞争解释。' }],
      reviewStatus: 'pre_review_completed',
      modelLabel: 'Qwen · production-v2', modelTraceId: 'trace-1',
    }))
    expect(restored.matchRun.failedCandidates[0]).toEqual(expect.objectContaining({ candidateId: 'candidate-2', version: 2, failureCode: 'model_timeout', retryable: true }))
    expect(restored.draft).toEqual(expect.objectContaining({
      version: 4,
      partialAcknowledgementReason: '先使用已完成候选。',
      decisions: expect.arrayContaining([expect.objectContaining({ candidateId: 'candidate-1', action: 'combine', roleCode: 'primary', responsibility: '解释时间约束。' })]),
      relation: { explanation: '共同解释。', premiseCompatibility: '前提兼容。', supportingEvidence: '支持 A\n支持 B', excludingEvidence: '排除 A', distinguishingEvidence: '区分 A' },
    }))
    expect(restored.decisionSet).toEqual({ decisionSetId: 'decision-set-1', version: 2, canConfirm: true, knowledgeReleaseId: 'release-final-1' })
    expect(restored.confirmedPlan).toEqual({ theoryPlanId: 'plan-1', taskId: 'task-1', matchRunId: 'match-1', decisionSetId: 'decision-set-1', knowledgeReleaseId: 'release-final-1', confirmedAt: '2026-08-22T08:02:00Z' })
  })

  it('treats only a 404 draft as an empty server draft and preserves the pinned match release', async () => {
    const notFound = { error: { code: 'not_found' as const, message: 'Theory decision draft was not found.', trace_id: 'error-trace' } }
    const api = transport({
      getTheoryDecisionDraft: vi.fn().mockImplementation(() => failed(404, notFound)),
      getConfirmedTheoryPlan: vi.fn(),
    } as unknown as Partial<M4TheoryJudgmentTransport>)
    const gateway = createM4TheoryJudgmentGateway(api)

    const restored = await gateway.restore({ task: { ...task, theoryPlanId: null } })

    expect(restored.draft).toEqual(expect.objectContaining({ matchRunId: 'match-1', version: 0, decisions: [], partialAcknowledgementReason: '' }))
    expect(restored.matchRun.knowledgeReleaseId).toBe('release-final-1')
    expect(api.getConfirmedTheoryPlan).not.toHaveBeenCalled()
  })

  it('maps catalog and network failures into explicit recoverable M4 failures', async () => {
    const catalogError = { error: { code: 'catalog_not_ready' as const, message: 'Final MATCH release is unavailable.', trace_id: 'catalog-trace' } }
    const catalogApi = transport({ createMatchRun: vi.fn().mockImplementation(() => failed(409, catalogError)) } as unknown as Partial<M4TheoryJudgmentTransport>)
    const startTask = { ...task, matchRunId: null, theoryPlanId: null, canStartMatching: true }

    await expect(createM4TheoryJudgmentGateway(catalogApi).start({ task: startTask, idempotencyKey: 'start-key' })).rejects.toEqual(expect.objectContaining({ code: 'catalog_not_ready', message: 'Final MATCH release is unavailable.' }))

    const networkApi = transport({ getMatchRun: vi.fn().mockRejectedValue(new TypeError('Failed to fetch')) } as unknown as Partial<M4TheoryJudgmentTransport>)
    await expect(createM4TheoryJudgmentGateway(networkApi).restore({ task: { ...task, theoryPlanId: null } })).rejects.toEqual(expect.objectContaining({
      code: 'network',
      message: '网络中断；如果正在编辑，请保持本页打开并在恢复连接后重试保存。',
    }))

    const draftNetworkApi = transport({ getTheoryDecisionDraft: vi.fn().mockRejectedValue(new TypeError('Failed to fetch draft')) } as unknown as Partial<M4TheoryJudgmentTransport>)
    await expect(createM4TheoryJudgmentGateway(draftNetworkApi).restore({ task: { ...task, theoryPlanId: null } })).rejects.toEqual(expect.objectContaining({ code: 'network' }))
  })

  it('re-reads the match run on refresh instead of pinning a generating response in memory', async () => {
    const generating = { ...matchRun, status: 'generating' as const, version: 5 }
    const ready = { ...matchRun, status: 'awaiting_decision' as const, version: 6, failed_candidates: [], failed_candidate_ids: [], failed_candidate_count: 0, completion_basis: 'complete' as const }
    const get = vi.fn()
      .mockImplementationOnce(() => ok(generating))
      .mockImplementationOnce(() => ok(ready))
    const api = transport({ getMatchRun: get } as unknown as Partial<M4TheoryJudgmentTransport>)
    const gateway = createM4TheoryJudgmentGateway(api)

    expect((await gateway.restore({ task: { ...task, theoryPlanId: null } })).matchRun.status).toBe('generating')
    expect((await gateway.restore({ task: { ...task, theoryPlanId: null } })).matchRun.status).toBe('awaiting_decision')
    expect(get).toHaveBeenCalledTimes(2)
  })

  it('sends the complete draft revision, user reasons, roles, relations, and partial acknowledgement to the server', async () => {
    const api = transport()
    const gateway = createM4TheoryJudgmentGateway(api)
    const localDraft: M4DecisionDraft = {
      matchRunId: 'match-1',
      version: 4,
      updatedAt: '2026-08-22T08:01:00Z',
      partialAcknowledgementReason: '先使用已完成候选。',
      decisions: [{ candidateId: 'candidate-1', candidateVersion: 3, action: 'combine', reason: '使用时间约束解释。', roleCode: 'primary', responsibility: '解释时间约束。', relatedSourceIds: ['source-1'], revisedApplicability: '' }, { candidateId: 'candidate-3', candidateVersion: 3, action: 'combine', reason: '使用互惠意愿解释。', roleCode: 'secondary', responsibility: '解释互惠意愿。', relatedSourceIds: ['source-1'], revisedApplicability: '' }],
      relation: { explanation: '共同解释。', premiseCompatibility: '前提兼容。', supportingEvidence: '支持 A\n支持 B', excludingEvidence: '排除 A', distinguishingEvidence: '区分 A' },
    }

    await gateway.saveDraft({ matchRunId: 'match-1', expectedVersion: 4, draft: localDraft, idempotencyKey: 'draft-key' })

    expect(api.saveTheoryDecisionDraft).toHaveBeenCalledWith(expect.objectContaining({
      path: { match_run_id: 'match-1' },
      headers: { 'Idempotency-Key': 'draft-key' },
      body: expect.objectContaining({
        expected_match_run_version: 6,
        expected_draft_version: 4,
        completion_basis: 'partial',
        decisions: expect.arrayContaining([expect.objectContaining({ candidate_id: 'candidate-1', action: 'combine', reason: '使用时间约束解释。', related_candidate_ids: ['candidate-3'] })]),
        use_assignments: expect.arrayContaining([{ candidate_id: 'candidate-1', role_code: 'primary', responsibility: '解释时间约束。' }]),
        relations: [expect.objectContaining({ candidate_ids: ['candidate-1', 'candidate-3'], supporting_evidence: ['支持 A', '支持 B'] })],
        acknowledged_candidate_ids: ['candidate-1', 'candidate-3'],
        failed_candidate_ids: ['candidate-2'],
        partial_completion_acknowledgement_reason: '先使用已完成候选。',
      }),
    }))
  })

  it('persists an unfinished decision without dropping its nullable action or in-progress reason', async () => {
    const api = transport()
    const gateway = createM4TheoryJudgmentGateway(api)
    const unfinished: M4DecisionDraft = {
      matchRunId: 'match-1',
      version: 4,
      updatedAt: '2026-08-22T08:01:00Z',
      partialAcknowledgementReason: '',
      decisions: [{ candidateId: 'candidate-1', candidateVersion: 3, action: null, reason: '刚写到一半', roleCode: '', responsibility: '', relatedSourceIds: [], revisedApplicability: '' }],
      relation: { explanation: '', premiseCompatibility: '', supportingEvidence: '', excludingEvidence: '', distinguishingEvidence: '' },
    }

    await gateway.saveDraft({ matchRunId: 'match-1', expectedVersion: 4, draft: unfinished, idempotencyKey: 'unfinished-key' })

    expect(api.saveTheoryDecisionDraft).toHaveBeenCalledWith(expect.objectContaining({
      body: expect.objectContaining({
        decisions: [{ candidate_id: 'candidate-1', candidate_version: 3, action: null, reason: '刚写到一半', related_candidate_ids: [], related_source_ids: [], revised_applicability: null }],
        acknowledged_candidate_ids: ['candidate-1', 'candidate-3'],
        failed_candidate_ids: ['candidate-2'],
        partial_completion_acknowledgement_reason: null,
      }),
    }))
  })

  it('uses current revisions for retry, acknowledgement, final decision, and exactly-once plan confirmation calls', async () => {
    const api = transport()
    const gateway = createM4TheoryJudgmentGateway(api)
    const restored = await gateway.restore({ task: { ...task, theoryPlanId: null } })

    await gateway.retryCandidate({ matchRunId: 'match-1', matchRunVersion: 6, candidateId: 'candidate-2', candidateVersion: 2, idempotencyKey: 'retry-key' })
    await gateway.acknowledgePartial({ matchRunId: 'match-1', matchRunVersion: 6, failedCandidateIds: ['candidate-2'], acknowledgedCandidateIds: ['candidate-1'], reason: '接受风险。', idempotencyKey: 'ack-key' })
    await gateway.createDecisionSet({ matchRun: restored.matchRun, draft: restored.draft, idempotencyKey: 'decision-key' })
    const plan = await gateway.confirmPlan({ decisionSetId: 'decision-set-1', expectedVersion: 2, idempotencyKey: 'confirm-key' })

    expect(api.retryMatchCandidate).toHaveBeenCalledWith(expect.objectContaining({ path: { match_run_id: 'match-1', candidate_id: 'candidate-2' }, headers: { 'Idempotency-Key': 'retry-key' }, body: { expected_match_run_version: 6, expected_candidate_version: 2 } }))
    expect(api.acknowledgePartialMatch).toHaveBeenCalledWith(expect.objectContaining({ headers: { 'Idempotency-Key': 'ack-key' }, body: { expected_version: 6, failed_candidate_ids: ['candidate-2'], acknowledged_candidate_ids: ['candidate-1'], reason: '接受风险。' } }))
    expect(api.createTheoryDecisions).toHaveBeenCalledWith(expect.objectContaining({ headers: { 'Idempotency-Key': 'decision-key' }, body: expect.objectContaining({ expected_match_run_version: 6, expected_draft_version: 4 }) }))
    expect(api.confirmTheoryPlan).toHaveBeenCalledWith(expect.objectContaining({ headers: { 'Idempotency-Key': 'confirm-key' }, body: { expected_decision_set_version: 2 } }))
    expect(plan).toEqual(expect.objectContaining({ theoryPlanId: 'plan-1', knowledgeReleaseId: 'release-final-1' }))
  })
})
