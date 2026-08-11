import { afterEach, describe, expect, it, vi } from 'vitest'

import type { FrameworkResponse } from '../../api/generated'
import {
  restoreFrameworkViaApi,
  saveFrameworkViaApi,
  toFrameworkView,
} from './frameworkApi'


function frameworkResponse(overrides: Partial<FrameworkResponse> = {}): FrameworkResponse {
  return {
    allowed_actions: ['update', 'start_review'],
    audit: null,
    content_origin: 'system_generated',
    created_at: '2026-08-11T00:00:00Z',
    draft: {
      alternative_explanations: ['资源供给变化'],
      concept_mappings: [{
        candidate_id: '10000000-0000-0000-0000-000000000001',
        theory_concept: '重复互动',
        meaning_in_study: '稳定出现的联系',
        empirical_indicators: ['互助频率'],
        unresolved_questions: ['如何区分资源效应'],
      }],
      ethical_boundaries: ['不上传未授权材料'],
      evidence_requirements: [{
        current_gap: '缺少时间顺序',
        distinguishing_signal: '资源不变时互助仍随互动变化',
        excluding_signal: '互动与互助无可观察联系',
        purpose: '区分互动与资源解释',
        related_candidate_ids: ['10000000-0000-0000-0000-000000000001'],
        required_material: '去标识化互动记录',
        requirement_id: 'requirement-1',
        supporting_signal: '重复互动增加时互助更稳定',
      }],
      inference_links: [],
      method_plan: null,
      next_actions: ['补充时间序列'],
      scope_and_limitations: ['仅解释已确认现象'],
      unresolved_items: ['缺少区分性材料'],
    },
    framework_id: '20000000-0000-0000-0000-000000000001',
    input: {
      analysis_unit: '社区成员',
      confirmed_research_question: '成员流动如何影响社区互助？',
      context: null,
      method_intent: { constraints: [], method_kind: null, source: 'user_confirmed' },
      original_research_question: '成员流动如何影响社区互助？',
      question_adjustment_reason: null,
      research_object: '社区成员',
      theory_plan: {
        adopted_candidate_ids: ['10000000-0000-0000-0000-000000000001'],
        allowed_actions: ['create_framework'],
        confirmed_at: '2026-08-11T00:00:00Z',
        confirmed_phenomenon: {
          allowed_actions: ['start_matching'],
          confirmed_at: '2026-08-11T00:00:00Z',
          content_hash: 'sha256:phenomenon',
          context: null,
          evidence_refs: [],
          phenomenon: '成员流动影响社区互助',
          phenomenon_query_id: '90000000-0000-0000-0000-000000000001',
          research_intent: null,
          source_ref_ids: [],
          status: 'confirmed',
          task_id: '60000000-0000-0000-0000-000000000001',
          version: 1,
        },
        decisions: [{
          action: 'adopt',
          candidate_id: '10000000-0000-0000-0000-000000000001',
          candidate_version: 1,
          decision_id: '30000000-0000-0000-0000-000000000001',
          reason: '解释重复互动与互惠规范',
          recorded_at: '2026-08-11T00:00:00Z',
          related_candidate_ids: [],
          related_source_ids: [],
          revised_applicability: null,
        }],
        decision_set_id: '40000000-0000-0000-0000-000000000001',
        knowledge_release_id: 'release-a',
        match_run_id: '50000000-0000-0000-0000-000000000001',
        phenomenon_query_id: '90000000-0000-0000-0000-000000000001',
        phenomenon_version: 1,
        relations: [],
        task_id: '60000000-0000-0000-0000-000000000001',
        theory_plan_id: '70000000-0000-0000-0000-000000000001',
        use_assignments: [{
          candidate_id: '10000000-0000-0000-0000-000000000001',
          responsibility: '解释重复互动与互惠规范',
          role_code: 'primary',
        }],
        version: 1,
      },
      theory_plan_id: '70000000-0000-0000-0000-000000000001',
      theory_plan_version: 1,
    },
    knowledge_release_id: 'release-a',
    model: null,
    previous_revision_id: null,
    revision_id: '80000000-0000-0000-0000-000000000001',
    revision_reason: null,
    status: 'draft',
    task_id: '60000000-0000-0000-0000-000000000001',
    unresolved_blocking_audit: false,
    version: 1,
    ...overrides,
  }
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => vi.unstubAllGlobals())

describe('frameworkApi', () => {
  it('restores the current framework and its append-only versions through generated SDK calls', async () => {
    const response = frameworkResponse()
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(input instanceof Request ? input.url : input.toString(), 'http://localhost')
      if (url.pathname.endsWith('/navigation')) {
        return json({ current_framework_id: response.framework_id })
      }
      if (url.pathname.endsWith('/versions')) {
        return json({ framework_id: response.framework_id, versions: [response] })
      }
      return json(response)
    })
    vi.stubGlobal('fetch', fetch)

    const restored = await restoreFrameworkViaApi(response.task_id)

    expect(restored?.current.confirmedResearchQuestion).toBe('成员流动如何影响社区互助？')
    expect(restored?.current.materialRequirements).toEqual(['去标识化互动记录'])
    expect(restored?.versions).toHaveLength(1)
    expect(fetch).toHaveBeenCalledTimes(3)
  })

  it('preserves structured evidence fields while saving editable lists as a new version', async () => {
    const response = frameworkResponse()
    const requests: Request[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push(input instanceof Request ? input : new Request(input, init))
      return json(frameworkResponse({ content_origin: 'user_modified', version: 2 }))
    }))
    const view = toFrameworkView(response)

    await saveFrameworkViaApi(response, {
      ...view,
      alternativeExplanations: ['资源变化', '选择效应'],
      nextActions: ['补充时间序列'],
    }, '补充竞争解释')

    const request = requests[0]
    expect(request?.method).toBe('PATCH')
    const body = await request?.json()
    expect(body.draft.evidence_requirements).toEqual(response.draft.evidence_requirements)
    expect(body.draft.alternative_explanations).toEqual(['资源变化', '选择效应'])
    expect(body.revision_reason).toBe('补充竞争解释')
  })
})
