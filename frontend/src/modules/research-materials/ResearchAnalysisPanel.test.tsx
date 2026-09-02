import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ResearchAnalysisPanel } from './ResearchAnalysisPanel'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function requestOf(input: RequestInfo | URL, init?: RequestInit): Request {
  return input instanceof Request ? input : new Request(String(input), init)
}

const material = {
  material_id: 'material-1', task_id: 'task-1', filename: '社区访谈.docx',
  media_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  size_bytes: 2048, status: 'ready', version: 1, parse_version: 1,
  segment_count: 3, updated_at: '2026-08-29T00:00:00Z', error_code: null,
}

describe('ResearchAnalysisPanel', () => {
  it('opens the current evidence-gap loop', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(requestOf(input, init).url).pathname
      if (path.endsWith('/research-cycle')) return response({
        schema_version: 'research-cycle-v1', task_id: 'task-1', version: 2,
        content_hash: 'sha256:cycle-2', analysis_content_hash: 'sha256:analysis-1',
        theory_plan_id: null, theory_plan_version: null, evidence: [],
        gaps: [{
          gap_id: 'gap-1', source_kind: 'analysis', source_id: 'comparison-1',
          description: '缺少未迁移家庭作为对照。', suggested_action: '下一轮纳入一个未迁移家庭。',
          destination: 'sampling', priority: 'high', analysis_content_hash: 'sha256:analysis-1',
          theory_plan_id: null, theory_plan_version: null, status: 'open',
        }],
        project_facts: {
          material_count: 1, material_kinds: [['interview_transcript', 1]], case_count: 1,
          case_material_coverage: [['家庭甲', 1]], consent_scopes: [], sensitivity_levels: [],
          pending_deidentification_count: 0, sampling_batches: [],
          analysis_counts: [['codes', 0], ['memos', 0], ['comparisons', 1]],
        },
        reporting_hints: [], research_map_patch: { nodes: [], relations: [] },
      })
      if (path.endsWith('/analysis')) return response({ task_id: 'task-1', annotations: [], codes: [], memos: [], comparisons: [] })
      if (path.endsWith('/materials/material-1')) return response({ ...material, segments: [] })
      return response({ task_id: 'task-1', items: [material] })
    }))

    render(<ResearchAnalysisPanel taskId="task-1" />)
    const panel = await screen.findByRole('region', { name: '分析' })

    expect(await within(panel).findByRole('region', { name: '证据缺口与下一轮材料' })).toHaveTextContent('缺少未迁移家庭作为对照。')
  })

  it('persists a qualitative method choice and refreshes the stable workspace snapshot', async () => {
    const analysisSnapshot = {
      task_id: 'task-1', annotations: [], codes: [], memos: [], comparisons: [],
      method_presets: [
        { method: 'thematic_analysis', label: '主题分析', primary_view: 'themes', matrix_axes: ['个案', '主题'], prompts: '发展共享意义模式。', guardrails: '代码不等于主题。' },
        { method: 'case_study', label: '个案研究', primary_view: 'case_matrix', matrix_axes: ['个案', '分析命题'], prompts: '先做个案内解释。', guardrails: '属性不代替个案解释。' },
      ],
      workspace: {
        schema_version: 'qualitative-workspace-v1', content_hash: 'f'.repeat(64),
        method_preset: { method: 'thematic_analysis', version: 0, updated_at: '1970-01-01T00:00:00Z' },
        codebook_entries: [], memo_links: [], case_profiles: [], formal_themes: [], candidate_themes: [], matrix_cells: [],
      },
    }
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestOf(input, init)
      const path = new URL(request.url).pathname
      if (path.endsWith('/analysis/workspace/method') && request.method === 'PUT') {
        return response({ method: 'case_study', version: 1, updated_at: '2026-08-31T00:00:00Z' })
      }
      if (path.endsWith('/analysis')) return response(analysisSnapshot)
      if (path.endsWith('/materials/material-1')) return response({ ...material, segments: [] })
      return response({ task_id: 'task-1', items: [material] })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<ResearchAnalysisPanel taskId="task-1" />)
    const panel = await screen.findByRole('region', { name: '分析' })
    const method = await within(panel).findByRole('combobox', { name: '方法取向' })
    fireEvent.change(method, { target: { value: 'case_study' } })

    await waitFor(() => expect(fetchMock.mock.calls.some((call) => {
      const request = requestOf(...call)
      return request.method === 'PUT' && new URL(request.url).pathname.endsWith('/analysis/workspace/method')
    })).toBe(true))
    await waitFor(() => expect(fetchMock.mock.calls.filter((call) => new URL(requestOf(...call).url).pathname.endsWith('/analysis'))).toHaveLength(2))
  })

  it('persists a user-confirmed case comparison through the analysis boundary', async () => {
    const annotations = [
      {
        annotation_id: 'annotation-a', task_id: 'task-1', material_id: 'material-1', parse_id: 'parse-1', segment_id: 'segment-a',
        segment_content_hash: 'a'.repeat(64), quote: '姐姐承担了大部分照护', quote_hash: 'b'.repeat(64), quote_start: 0, quote_end: 11,
        locator: { page: 4, section_path: [], paragraph: 12, line_start: null, line_end: null, char_start: null, char_end: null, block_index: null },
        annotation_kind: 'descriptive', case_label: '家庭 A', observed_at: '迁移后', note: '责任集中', reflection: null, created_at: '2026-08-30T00:00:00Z',
      },
      {
        annotation_id: 'annotation-b', task_id: 'task-1', material_id: 'material-2', parse_id: 'parse-2', segment_id: 'segment-b',
        segment_content_hash: 'c'.repeat(64), quote: '弟弟与父亲仍在分担照护', quote_hash: 'd'.repeat(64), quote_start: 0, quote_end: 12,
        locator: { page: 7, section_path: [], paragraph: 8, line_start: null, line_end: null, char_start: null, char_end: null, block_index: null },
        annotation_kind: 'descriptive', case_label: '家庭 B', observed_at: '迁移后', note: '多人分担', reflection: null, created_at: '2026-08-30T00:00:00Z',
      },
    ]
    const created = {
      comparison_id: 'comparison-user', task_id: 'task-1', title: '照护责任比较', question: '迁移是否必然导致责任集中？',
      case_labels: ['案例：家庭 A', '案例：家庭 B'], time_labels: [],
      findings: [{ kind: 'support', statement: '家庭 A 的责任集中。', annotation_ids: ['annotation-a'] }],
      competing_explanations: [], evidence_gaps: [], next_steps: [], theory_implication: '需要加入家庭资源条件。',
      source: 'user', status: 'confirmed', version: 2, created_at: '2026-08-30T00:00:00Z', decided_at: '2026-08-30T00:00:01Z', decision_reason: '用户创建并确认',
    }
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestOf(input, init)
      const path = new URL(request.url).pathname
      if (path.endsWith('/analysis/comparisons') && request.method === 'POST') return response(created, 201)
      if (path.endsWith('/analysis')) return response({ task_id: 'task-1', annotations, codes: [], memos: [], comparisons: [] })
      if (path.endsWith('/materials/material-1')) return response({ ...material, segments: [] })
      return response({ task_id: 'task-1', items: [material] })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<ResearchAnalysisPanel taskId="task-1" />)
    const panel = await screen.findByRole('region', { name: '分析' })
    fireEvent.click(await within(panel).findByRole('button', { name: '建立案例比较' }))
    const form = within(panel).getByRole('form', { name: '建立案例比较' })
    fireEvent.click(within(form).getByRole('checkbox', { name: '案例：家庭 A' }))
    fireEvent.click(within(form).getByRole('checkbox', { name: '案例：家庭 B' }))
    fireEvent.click(within(form).getByRole('checkbox', { name: /姐姐承担了大部分照护/ }))
    fireEvent.change(within(form).getByRole('textbox', { name: '比较标题' }), { target: { value: created.title } })
    fireEvent.change(within(form).getByRole('textbox', { name: '比较问题' }), { target: { value: created.question } })
    fireEvent.change(within(form).getByRole('textbox', { name: '支持证据' }), { target: { value: created.findings[0].statement } })
    fireEvent.change(within(form).getByRole('textbox', { name: '理论含义' }), { target: { value: created.theory_implication } })
    fireEvent.click(within(form).getByRole('button', { name: '保存案例比较' }))

    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) => {
      const request = requestOf(input, init)
      return request.method === 'POST' && new URL(request.url).pathname.endsWith('/analysis/comparisons')
    })).toBe(true))
    expect(await within(panel).findByRole('article', { name: '已确认案例比较：照护责任比较' })).toBeVisible()
  })

  it('sends a reason and visible version when confirming an Agent comparison', async () => {
    const candidate = {
      comparison_id: 'comparison-agent', task_id: 'task-1', title: '两个家庭的责任重组', question: '家庭资源是否改变迁移影响？',
      case_labels: ['案例：家庭 A', '案例：家庭 B'], time_labels: [],
      findings: [{ kind: 'support', statement: '两个家庭呈现不同变化。', annotation_ids: [] }],
      competing_explanations: ['经济资源差异'], evidence_gaps: ['缺少家庭成员追访'],
      next_steps: [{ kind: 'interview', action: '追访家庭成员', priority: 'high' }], theory_implication: '需加入资源边界。',
      source: 'agent', status: 'candidate', version: 4, created_at: '2026-08-30T00:00:00Z', decided_at: null, decision_reason: null,
    }
    const confirmed = { ...candidate, status: 'confirmed', version: 5, decided_at: '2026-08-30T00:00:01Z', decision_reason: '已核对原文' }
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestOf(input, init)
      const path = new URL(request.url).pathname
      if (path.endsWith('/analysis/comparisons/comparison-agent/decision') && request.method === 'POST') return response(confirmed)
      if (path.endsWith('/analysis')) return response({ task_id: 'task-1', annotations: [], codes: [], memos: [], comparisons: [candidate] })
      if (path.endsWith('/materials/material-1')) return response({ ...material, segments: [] })
      return response({ task_id: 'task-1', items: [material] })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<ResearchAnalysisPanel taskId="task-1" />)
    const panel = await screen.findByRole('region', { name: '分析' })
    const comparison = await within(panel).findByRole('article', { name: '案例比较候选：两个家庭的责任重组' })
    fireEvent.change(within(comparison).getByRole('textbox', { name: '案例比较判断依据' }), { target: { value: '已核对原文' } })
    fireEvent.click(within(comparison).getByRole('button', { name: '确认案例比较' }))

    await waitFor(async () => {
      const call = fetchMock.mock.calls.find(([input, init]) => new URL(requestOf(input, init).url).pathname.endsWith('/comparison-agent/decision'))
      expect(call).toBeDefined()
      expect(await requestOf(...call!).json()).toEqual({ decision: 'confirmed', reason: '已核对原文', expected_version: 4 })
    })
  })

})
