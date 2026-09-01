import { afterEach, describe, expect, it, vi } from 'vitest'

import { getResearchCycleSnapshot } from './researchAnalysisApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('research cycle generated-client boundary', () => {
  it('loads the current traceable loop projection through the generated operation', async () => {
    const snapshot = {
      schema_version: 'research-cycle-v1',
      task_id: 'task-1',
      version: 3,
      content_hash: 'sha256:cycle-3',
      analysis_content_hash: 'sha256:analysis-2',
      theory_plan_id: 'theory-plan-1',
      theory_plan_version: 2,
      evidence: [],
      gaps: [],
      project_facts: {
        material_count: 1,
        material_kinds: [['interview_transcript', 1]],
        case_count: 1,
        case_material_coverage: [['家庭甲', 1]],
        consent_scopes: [['project_only', 1]],
        sensitivity_levels: [['sensitive', 1]],
        pending_deidentification_count: 0,
        sampling_batches: ['第一轮'],
        analysis_counts: [['codes', 1], ['memos', 0], ['comparisons', 1]],
      },
      reporting_hints: [],
      research_map_patch: { nodes: [], relations: [] },
    }
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify(snapshot), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getResearchCycleSnapshot('task-1')).resolves.toEqual(snapshot)
    const input = fetchMock.mock.calls[0][0]
    const request = input instanceof Request ? input : new Request(String(input), fetchMock.mock.calls[0][1])
    expect(request.method).toBe('GET')
    expect(new URL(request.url).pathname).toBe('/api/research-tasks/task-1/research-cycle')
  })
})
