import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ResearchAnalysisSnapshot } from './researchAnalysisModel'
import { QualitativeWorkspacePanel } from './QualitativeWorkspacePanel'

afterEach(cleanup)

const annotation = {
  annotation_id: 'annotation-1', task_id: 'task-1', material_id: 'material-1', parse_id: 'parse-1',
  segment_id: 'segment-1', segment_content_hash: 'a'.repeat(64), quote: '邻居转告后完成了申请',
  quote_hash: 'b'.repeat(64), quote_start: 0, quote_end: 11,
  locator: { page: 1, section_path: [], paragraph: 2, line_start: null, line_end: null, char_start: null, char_end: null, block_index: null },
  annotation_kind: 'descriptive' as const, case_label: '县城个案', observed_at: null,
  note: '非正式网络传递资源信息', reflection: null, created_at: '2026-08-31T00:00:00Z',
  source_available: true, unavailable_reason: null,
}

const negativeAnnotation = {
  ...annotation,
  annotation_id: 'annotation-2',
  segment_id: 'segment-2',
  quote: '申请已经完成',
  quote_end: 6,
  case_label: '城市个案',
  note: '没有描述信息渠道',
}

const snapshot = {
  task_id: 'task-1',
  annotations: [annotation, negativeAnnotation],
  codes: [{
    code_id: 'code-1', task_id: 'task-1', label: '资源信息渠道', definition: '获得制度资源信息的渠道。',
    annotation_ids: ['annotation-1', 'annotation-2'], rationale: '研究者核对原文后建立。', source: 'user', status: 'confirmed', version: 2,
    created_at: '2026-08-31T00:00:00Z', decided_at: '2026-08-31T00:00:00Z', decision_reason: '确认',
    conversation_id: null, agent_run_id: null, agent_turn_id: null, tool_call_id: null,
  }],
  memos: [{
    memo_id: 'memo-1', task_id: 'task-1', title: '组织渠道并非必要条件', content: '县城个案构成反例。', memo_kind: 'analytic',
    annotation_ids: ['annotation-1'], code_ids: ['code-1'], source: 'user', status: 'confirmed', version: 2,
    created_at: '2026-08-31T00:00:00Z', decided_at: '2026-08-31T00:00:00Z', decision_reason: '确认',
    conversation_id: null, agent_run_id: null, agent_turn_id: null, tool_call_id: null,
  }],
  comparisons: [],
  method_presets: [
    { method: 'thematic_analysis', label: '主题分析', primary_view: 'themes', matrix_axes: ['个案', '主题'], prompts: '发展共享意义模式。', guardrails: '代码不等于主题。' },
    { method: 'case_study', label: '个案研究', primary_view: 'case_matrix', matrix_axes: ['个案', '分析命题'], prompts: '先做个案内解释，再做跨个案比较。', guardrails: '属性用于筛选，不把个案压缩为变量行。' },
  ],
  workspace: {
    schema_version: 'qualitative-workspace-v1', content_hash: 'c'.repeat(64),
    method_preset: { method: 'thematic_analysis', version: 0, updated_at: '1970-01-01T00:00:00Z' },
    codebook_entries: [], memo_links: [], case_profiles: [], matrix_cells: [], formal_themes: [],
    candidate_themes: [{
      theme_id: 'theme-candidate', label: '资源可见性的分层', central_concept: '关系网络影响资源可见性。',
      code_ids: ['code-1'], annotation_ids: ['annotation-1'], source: 'agent', status: 'candidate', version: 1,
      created_at: '2026-08-31T00:00:00Z', decided_at: null, decision_reason: null,
    }],
  },
} as ResearchAnalysisSnapshot

function callbacks() {
  return {
    onConfigureCodebook: vi.fn(async () => undefined),
    onTransitionCodebook: vi.fn(async () => undefined),
    onCreateTheme: vi.fn(async () => undefined),
    onConfirmTheme: vi.fn(async () => undefined),
    onAttachMemo: vi.fn(async () => undefined),
    onSaveCaseProfile: vi.fn(async () => undefined),
    onSaveMatrixCell: vi.fn(async () => undefined),
    onSetMethod: vi.fn(async () => undefined),
  }
}

describe('QualitativeWorkspacePanel', () => {
  it('changes only the method view preset and keeps its methodological guardrail visible', async () => {
    const actions = callbacks()
    render(<QualitativeWorkspacePanel snapshot={snapshot} {...actions} />)

    expect(screen.getByText('代码不等于主题。')).toBeVisible()
    fireEvent.change(screen.getByRole('combobox', { name: '方法取向' }), { target: { value: 'case_study' } })

    expect(actions.onSetMethod).toHaveBeenCalledWith({ method: 'case_study', expected_version: null })
    expect(screen.getByText('先做个案内解释，再做跨个案比较。')).toBeVisible()
    expect(screen.getByText('属性用于筛选，不把个案压缩为变量行。')).toBeVisible()
  })

  it('builds a bounded codebook entry from separately selected positive and negative source examples', async () => {
    const actions = callbacks()
    render(<QualitativeWorkspacePanel snapshot={snapshot} {...actions} />)

    fireEvent.click(screen.getByRole('button', { name: '补全代码本：资源信息渠道' }))
    const form = screen.getByRole('form', { name: '编辑代码本：资源信息渠道' })
    fireEvent.change(within(form).getByRole('textbox', { name: '纳入规则' }), { target: { value: '明确描述信息进入渠道' } })
    fireEvent.change(within(form).getByRole('textbox', { name: '排除规则' }), { target: { value: '只描述申请结果' } })
    fireEvent.click(within(form).getByRole('checkbox', { name: '正例：邻居转告后完成了申请' }))
    fireEvent.click(within(form).getByRole('checkbox', { name: '反例：申请已经完成' }))
    fireEvent.click(within(form).getByRole('button', { name: '保存代码本边界' }))

    expect(actions.onConfigureCodebook).toHaveBeenCalledWith('code-1', {
      expected_version: null,
      inclusion_rules: ['明确描述信息进入渠道'],
      exclusion_rules: ['只描述申请结果'],
      parent_code_id: null,
      positive_example_annotation_ids: ['annotation-1'],
      negative_example_annotation_ids: ['annotation-2'],
    })
    expect(screen.getByText('Agent 主题候选 · 待确认')).toBeVisible()
    expect(screen.getByText('资源可见性的分层')).toBeVisible()
  })

  it('keeps a failed formal-object save visible in the workspace', async () => {
    const actions = callbacks()
    actions.onConfigureCodebook.mockRejectedValueOnce(new Error('代码本版本已变更，请重新核对。'))
    render(<QualitativeWorkspacePanel snapshot={snapshot} {...actions} />)

    fireEvent.click(screen.getByRole('button', { name: '补全代码本：资源信息渠道' }))
    const form = screen.getByRole('form', { name: '编辑代码本：资源信息渠道' })
    fireEvent.change(within(form).getByRole('textbox', { name: '纳入规则' }), { target: { value: '明确描述信息进入渠道' } })
    fireEvent.change(within(form).getByRole('textbox', { name: '排除规则' }), { target: { value: '只描述申请结果' } })
    fireEvent.click(within(form).getByRole('checkbox', { name: '正例：邻居转告后完成了申请' }))
    fireEvent.click(within(form).getByRole('checkbox', { name: '反例：申请已经完成' }))
    fireEvent.click(within(form).getByRole('button', { name: '保存代码本边界' }))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('代码本版本已变更，请重新核对。'))
  })

  it('creates a source-grounded case profile without deriving upstream case identity from labels', async () => {
    const actions = callbacks()
    render(<QualitativeWorkspacePanel snapshot={snapshot} {...actions} />)

    fireEvent.click(screen.getByRole('button', { name: '个案档案' }))
    fireEvent.click(screen.getByRole('button', { name: '建立个案档案' }))
    const form = screen.getByRole('form', { name: '建立个案档案' })
    fireEvent.change(within(form).getByRole('textbox', { name: '个案引用' }), { target: { value: 'case-ref-from-upstream' } })
    fireEvent.change(within(form).getByRole('textbox', { name: '显示名称' }), { target: { value: '县城个案' } })
    fireEvent.change(within(form).getByRole('textbox', { name: '属性名称' }), { target: { value: '地区' } })
    fireEvent.change(within(form).getByRole('textbox', { name: '属性值' }), { target: { value: '县城' } })
    fireEvent.change(within(form).getByRole('textbox', { name: '个案摘要' }), { target: { value: '依靠邻里获得资源信息。' } })
    fireEvent.click(within(form).getByRole('checkbox', { name: '个案原文：邻居转告后完成了申请' }))
    fireEvent.click(within(form).getByRole('checkbox', { name: '个案备忘：组织渠道并非必要条件' }))
    fireEvent.click(within(form).getByRole('button', { name: '保存个案档案' }))

    expect(actions.onSaveCaseProfile).toHaveBeenCalledWith({
      expected_version: null,
      case_ref: 'case-ref-from-upstream',
      display_label: '县城个案',
      attributes: [{ name: '地区', value: '县城' }],
      summary: '依靠邻里获得资源信息。',
      annotation_ids: ['annotation-1'],
      memo_ids: ['memo-1'],
    })
  })
})
