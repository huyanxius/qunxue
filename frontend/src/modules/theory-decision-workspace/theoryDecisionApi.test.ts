import { afterEach, expect, it, vi } from 'vitest'

import {
  confirmTheoryPlanViaApi,
  deferTheoryPlanViaApi,
  restoreTheoryWorkspaceViaApi,
  saveTheoryDecisionsViaApi,
} from './theoryDecisionApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

it('restores the persisted match, decisions and confirmed plan through generated endpoints', async () => {
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const request = input as Request
    if (request.url.includes('/navigation')) {
      return json({ current_match_run_id: 'match-1' })
    }
    if (request.url.endsWith('/api/match-runs/match-1')) {
      return json({
        match_run_id: 'match-1', task_id: 'task-1', version: 1,
        status: 'awaiting_decision', knowledge_release_id: 'release-1',
        completion_basis: 'complete',
        candidate_page: { candidates: [], stable_order: [], next_cursor: null },
      })
    }
    return json({
      decision_sets: [{
        decision_set_id: 'set-1', version: 1,
        decisions: [{ candidate_id: 'candidate-1', action: 'combine', reason: '联合解释', revised_applicability: null }],
        use_assignments: [{ candidate_id: 'candidate-1', role_code: 'primary', responsibility: '核心解释' }],
        relations: [{
          candidate_ids: ['candidate-1', 'candidate-2'], relation_kind: 'complementary',
          explanation: '层次互补', premise_compatibility: '兼容', supporting_evidence: ['支持'],
          excluding_evidence: ['排除'], distinguishing_evidence: ['区分'],
        }],
      }],
      deferred_plan: { reason: '等待材料', deferred_at: '2026-08-11T00:00:00Z' },
      confirmed_plan: {
        theory_plan_id: 'plan-1', adopted_candidate_ids: ['candidate-1'],
        confirmed_at: '2026-08-11T00:00:00Z',
      },
    })
  })
  vi.stubGlobal('fetch', fetch)

  const restored = await restoreTheoryWorkspaceViaApi('task-1')

  expect(restored.matchRunId).toBe('match-1')
  expect(restored.latestDecisionSet?.decisionSetId).toBe('set-1')
  expect(restored.latestDecisionSet?.useAssignments?.[0].roleCode).toBe('primary')
  expect(restored.latestDecisionSet?.relations?.[0].relationKind).toBe('complementary')
  expect(restored.deferredPlan?.reason).toBe('等待材料')
  expect(restored.confirmedPlan?.theoryPlanId).toBe('plan-1')
  expect(fetch.mock.calls.map(([input]) => (input as Request).url)).toEqual([
    expect.stringContaining('/api/research-tasks/task-1/navigation'),
    expect.stringContaining('/api/match-runs/match-1'),
    expect.stringContaining('/api/match-runs/match-1/decisions'),
  ])
})

it('persists a whole-plan deferral through the generated endpoint', async () => {
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const request = input as Request
    expect(request.url).toContain('/api/match-runs/match-1/defer')
    expect(await request.json()).toEqual({
      expected_match_run_version: 1,
      reason: '等待补充材料',
    })
    return json({ reason: '等待补充材料', deferred_at: '2026-08-11T00:00:00Z' })
  })
  vi.stubGlobal('fetch', fetch)

  const result = await deferTheoryPlanViaApi({
    matchRunId: 'match-1', matchRunVersion: 1, reason: '等待补充材料',
  })

  expect(result.reason).toBe('等待补充材料')
})

it('writes user decisions and confirmation without handwritten transport DTOs', async () => {
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const request = input as Request
    if (request.url.includes('/decisions')) {
      const body = await request.json()
      expect(body.decisions[0]).toEqual(expect.objectContaining({
        candidate_id: 'candidate-1',
        action: 'adopt',
        reason: '解释关系变化',
      }))
      return json({
        decision_set_id: 'set-1', version: 1, decisions: [],
        use_assignments: [], relations: [],
      }, 201)
    }
    return json({
      theory_plan_id: 'plan-1',
      adopted_candidate_ids: ['candidate-1'],
      confirmed_at: '2026-08-11T00:00:00Z',
    })
  })
  vi.stubGlobal('fetch', fetch)

  const saved = await saveTheoryDecisionsViaApi({
    matchRunId: 'match-1',
    matchRunVersion: 1,
    completionBasis: 'complete',
    decisions: [{
      candidateId: 'candidate-1', candidateVersion: 1, action: 'adopt',
      reason: '解释关系变化', relatedSourceIds: ['source-1'],
      relatedCandidateIds: [], revisedApplicability: null,
    }],
    useAssignments: [{
      candidateId: 'candidate-1', roleCode: 'primary', responsibility: '核心解释',
    }],
    relations: [],
  })
  const confirmed = await confirmTheoryPlanViaApi({
    decisionSetId: saved.decisionSetId,
    version: saved.version,
  })

  expect(confirmed.theoryPlanId).toBe('plan-1')
})
