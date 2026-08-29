import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ResearchAnalysisSnapshot } from './researchAnalysisModel'
import { ResearchAnalysisWorkspace } from './ResearchAnalysisWorkspace'

afterEach(cleanup)

const snapshot: ResearchAnalysisSnapshot = {
  task_id: 'task-1',
  comparisons: [],
  annotations: [{
    annotation_id: 'annotation-1', task_id: 'task-1', material_id: 'material-1', parse_id: 'parse-1',
    segment_id: 'segment-1', segment_content_hash: 'a'.repeat(64), quote: '姐姐承担了大部分照护',
    quote_hash: 'b'.repeat(64), quote_start: 5, quote_end: 16,
    locator: { page: 4, section_path: ['家庭安排'], paragraph: 12, line_start: null, line_end: null, char_start: null, char_end: null, block_index: null },
    annotation_kind: 'descriptive', case_label: '家庭 A', observed_at: '迁移后',
    note: '照护责任集中到姐姐', reflection: '检查性别分工的先验假设', created_at: '2026-08-30T00:00:00Z',
    source_available: true, unavailable_reason: null,
  }],
  codes: [
    {
      code_id: 'code-confirmed', task_id: 'task-1', label: '照护责任性别化', definition: '照护劳动按性别集中分配。',
      annotation_ids: ['annotation-1'], rationale: '研究者核对原文后建立。', source: 'user', status: 'confirmed', version: 1,
      created_at: '2026-08-30T00:00:00Z', decided_at: '2026-08-30T00:00:00Z', decision_reason: null,
      conversation_id: null, agent_run_id: null, agent_turn_id: null, tool_call_id: null,
    },
    {
      code_id: 'code-candidate', task_id: 'task-1', label: '家庭责任重组', definition: '迁移后责任重新分配。',
      annotation_ids: ['annotation-1'], rationale: '还需要研究者判断是否过度概括。', source: 'agent', status: 'candidate', version: 2,
      created_at: '2026-08-30T00:00:00Z', decided_at: null, decision_reason: null,
      conversation_id: 'conversation-1', agent_run_id: 'run-1', agent_turn_id: 'turn-1', tool_call_id: 'tool-1',
    },
  ],
  memos: [
    {
      memo_id: 'memo-confirmed', task_id: 'task-1', title: '竞争解释', content: '经济资源差异也可能解释责任安排。', memo_kind: 'analytic',
      annotation_ids: ['annotation-1'], code_ids: ['code-confirmed'], source: 'user', status: 'confirmed', version: 1,
      created_at: '2026-08-30T00:00:00Z', decided_at: '2026-08-30T00:00:00Z', decision_reason: null,
      conversation_id: null, agent_run_id: null, agent_turn_id: null, tool_call_id: null,
    },
  ],
}

const comparisonSnapshot: ResearchAnalysisSnapshot = {
  ...snapshot,
  annotations: [
    ...snapshot.annotations,
    {
      annotation_id: 'annotation-2', task_id: 'task-1', material_id: 'material-2', parse_id: 'parse-2',
      segment_id: 'segment-2', segment_content_hash: 'c'.repeat(64), quote: '弟弟开始承担接送与采购',
      quote_hash: 'd'.repeat(64), quote_start: 2, quote_end: 14,
      locator: { page: 7, section_path: ['日常安排'], paragraph: 8, line_start: null, line_end: null, char_start: null, char_end: null, block_index: null },
      annotation_kind: 'descriptive', case_label: '家庭 B', observed_at: '迁移前',
      note: '照护责任没有集中到单一成员', reflection: null, created_at: '2026-08-30T00:00:00Z',
      source_available: true, unavailable_reason: null,
    },
  ],
  comparisons: [
    {
      comparison_id: 'comparison-candidate', task_id: 'task-1', title: '迁移前后的照护责任', question: '迁移如何改变家庭照护分工？',
      case_labels: ['案例：家庭 A', '案例：家庭 B'], time_labels: ['迁移前', '迁移后'],
      findings: [
        { kind: 'support', statement: '家庭 A 的照护责任在迁移后集中。', annotation_ids: ['annotation-1'] },
        { kind: 'counterexample', statement: '家庭 B 仍然由多位成员分担。', annotation_ids: ['annotation-2'] },
        { kind: 'contradict', statement: '两个案例对迁移影响呈现相反方向。', annotation_ids: ['annotation-1', 'annotation-2'] },
      ],
      competing_explanations: ['家庭经济资源差异可能比迁移更关键。'],
      evidence_gaps: ['缺少其他家庭成员的叙述。'],
      next_steps: [{ kind: 'interview', action: '追访两个家庭的其他照护者。', priority: 'high' }],
      theory_implication: '责任重组理论需加入资源条件边界。', source: 'agent', status: 'candidate', version: 3,
      created_at: '2026-08-30T00:00:00Z', decided_at: null, decision_reason: null,
      conversation_id: 'conversation-2', agent_run_id: 'run-2', agent_turn_id: 'turn-2', tool_call_id: 'tool-2',
    },
  ],
}

describe('ResearchAnalysisWorkspace', () => {
  it('shows confirmed user records separately from Agent candidates', () => {
    render(
      <ResearchAnalysisWorkspace
        snapshot={snapshot}
        selectedMaterialId="material-1"
        onCreateCode={vi.fn()}
        onCreateMemo={vi.fn()}
        onDecideCode={vi.fn()}
        onDecideMemo={vi.fn()}
      />,
    )

    const analysis = screen.getByRole('region', { name: '质性分析' })
    expect(within(analysis).getByText('照护责任性别化')).toBeVisible()
    expect(within(analysis).getByText('竞争解释')).toBeVisible()
    expect(within(analysis).getByRole('article', { name: '候选编码：家庭责任重组' })).toBeVisible()
    expect(within(analysis).getAllByText(/^研究者确认/)).toHaveLength(2)
  })

  it('creates a user code only from explicitly selected annotations', () => {
    const createCode = vi.fn(async () => undefined)
    render(
      <ResearchAnalysisWorkspace
        snapshot={snapshot}
        selectedMaterialId="material-1"
        onCreateCode={createCode}
        onCreateMemo={vi.fn()}
        onDecideCode={vi.fn()}
        onDecideMemo={vi.fn()}
      />,
    )
    const analysis = screen.getByRole('region', { name: '质性分析' })
    fireEvent.click(within(analysis).getByRole('button', { name: '建立编码' }))
    const form = within(analysis).getByRole('form', { name: '建立编码' })
    fireEvent.click(within(form).getByRole('checkbox', { name: /姐姐承担了大部分照护/ }))
    fireEvent.change(within(form).getByRole('textbox', { name: '编码名称' }), { target: { value: '照护责任重组' } })
    fireEvent.change(within(form).getByRole('textbox', { name: '编码定义' }), { target: { value: '责任在家庭成员之间重新分配' } })
    fireEvent.change(within(form).getByRole('textbox', { name: '建立依据' }), { target: { value: '核对原文后建立' } })
    fireEvent.click(within(form).getByRole('button', { name: '保存编码' }))

    expect(createCode).toHaveBeenCalledWith({
      label: '照护责任重组',
      definition: '责任在家庭成员之间重新分配',
      rationale: '核对原文后建立',
      annotation_ids: ['annotation-1'],
    })
  })

  it('creates a typed user memo with explicit annotation and code links', () => {
    const createMemo = vi.fn(async () => undefined)
    render(
      <ResearchAnalysisWorkspace
        snapshot={snapshot}
        selectedMaterialId="material-1"
        onCreateCode={vi.fn()}
        onCreateMemo={createMemo}
        onDecideCode={vi.fn()}
        onDecideMemo={vi.fn()}
      />,
    )
    const analysis = screen.getByRole('region', { name: '质性分析' })
    fireEvent.click(within(analysis).getByRole('button', { name: '写分析备忘' }))
    const form = within(analysis).getByRole('form', { name: '写分析备忘' })
    fireEvent.click(within(form).getByRole('checkbox', { name: /姐姐承担了大部分照护/ }))
    fireEvent.click(within(form).getByRole('checkbox', { name: /照护责任性别化/ }))
    fireEvent.change(within(form).getByRole('textbox', { name: '备忘标题' }), { target: { value: '并非唯一解释' } })
    fireEvent.change(within(form).getByRole('textbox', { name: '备忘内容' }), { target: { value: '还需检查经济资源差异' } })
    fireEvent.change(within(form).getByRole('combobox', { name: '备忘类型' }), { target: { value: 'reflexive' } })
    fireEvent.click(within(form).getByRole('button', { name: '保存备忘' }))

    expect(createMemo).toHaveBeenCalledWith({
      title: '并非唯一解释',
      content: '还需检查经济资源差异',
      memo_kind: 'reflexive',
      annotation_ids: ['annotation-1'],
      code_ids: ['code-confirmed'],
    })
  })

  it('shows every comparison diagnostic and requires a reason plus CAS version for an Agent candidate', () => {
    const decideComparison = vi.fn(async () => undefined)
    render(
      <ResearchAnalysisWorkspace
        snapshot={comparisonSnapshot}
        selectedMaterialId="material-1"
        materialNames={{ 'material-1': '家庭 A 访谈.docx', 'material-2': '家庭 B 田野笔记.md' }}
        onCreateCode={vi.fn()}
        onCreateMemo={vi.fn()}
        onDecideCode={vi.fn()}
        onDecideMemo={vi.fn()}
        onCreateComparison={vi.fn()}
        onDecideComparison={decideComparison}
      />,
    )

    const candidate = screen.getByRole('article', { name: '案例比较候选：迁移前后的照护责任' })
    expect(within(candidate).getByText('支持证据')).toBeVisible()
    expect(within(candidate).getByText('反例')).toBeVisible()
    expect(within(candidate).getByText('矛盾材料')).toBeVisible()
    expect(within(candidate).getByText('竞争解释')).toBeVisible()
    expect(within(candidate).getByText('证据缺口')).toBeVisible()
    expect(within(candidate).getByText('下一步行动')).toBeVisible()
    const confirm = within(candidate).getByRole('button', { name: '确认案例比较' })
    expect(confirm).toBeDisabled()
    fireEvent.change(within(candidate).getByRole('textbox', { name: '案例比较判断依据' }), { target: { value: '  已逐条回到两个案例原文核对  ' } })
    fireEvent.click(confirm)

    expect(decideComparison).toHaveBeenCalledWith('comparison-candidate', 'confirmed', '已逐条回到两个案例原文核对', 3)
  })

  it('creates a traceable user comparison only after two units and source annotations are selected', () => {
    const createComparison = vi.fn(async () => undefined)
    render(
      <ResearchAnalysisWorkspace
        snapshot={{ ...comparisonSnapshot, comparisons: [] }}
        selectedMaterialId="material-1"
        materialNames={{ 'material-1': '家庭 A 访谈.docx', 'material-2': '家庭 B 田野笔记.md' }}
        onCreateCode={vi.fn()}
        onCreateMemo={vi.fn()}
        onDecideCode={vi.fn()}
        onDecideMemo={vi.fn()}
        onCreateComparison={createComparison}
        onDecideComparison={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '建立案例比较' }))
    const form = screen.getByRole('form', { name: '建立案例比较' })
    fireEvent.click(within(form).getByRole('checkbox', { name: '案例：家庭 A' }))
    fireEvent.click(within(form).getByRole('checkbox', { name: '案例：家庭 B' }))
    fireEvent.click(within(form).getByRole('checkbox', { name: /姐姐承担了大部分照护/ }))
    fireEvent.click(within(form).getByRole('checkbox', { name: /弟弟开始承担接送与采购/ }))
    fireEvent.change(within(form).getByRole('textbox', { name: '比较标题' }), { target: { value: '两个家庭的照护责任重组' } })
    fireEvent.change(within(form).getByRole('textbox', { name: '比较问题' }), { target: { value: '迁移是否必然导致照护责任集中？' } })
    fireEvent.change(within(form).getByRole('textbox', { name: '支持证据' }), { target: { value: '家庭 A 在迁移后出现责任集中。' } })
    fireEvent.change(within(form).getByRole('textbox', { name: '反例' }), { target: { value: '家庭 B 仍保持多人分担。' } })
    fireEvent.change(within(form).getByRole('textbox', { name: '矛盾材料' }), { target: { value: '同样的迁移时点呈现不同变化。' } })
    fireEvent.change(within(form).getByRole('textbox', { name: '竞争解释' }), { target: { value: '经济资源差异可能更关键。' } })
    fireEvent.change(within(form).getByRole('textbox', { name: '证据缺口' }), { target: { value: '缺少其他照护者的叙述。' } })
    fireEvent.change(within(form).getByRole('textbox', { name: '理论含义' }), { target: { value: '责任重组需要加入资源条件边界。' } })
    fireEvent.change(within(form).getByRole('textbox', { name: '下一步行动' }), { target: { value: '追访两个家庭的其他照护者。' } })
    fireEvent.click(within(form).getByRole('button', { name: '保存案例比较' }))

    expect(createComparison).toHaveBeenCalledWith({
      title: '两个家庭的照护责任重组',
      question: '迁移是否必然导致照护责任集中？',
      case_labels: ['案例：家庭 A', '案例：家庭 B'],
      time_labels: [],
      findings: [
        { kind: 'support', statement: '家庭 A 在迁移后出现责任集中。', annotation_ids: ['annotation-1', 'annotation-2'] },
        { kind: 'counterexample', statement: '家庭 B 仍保持多人分担。', annotation_ids: ['annotation-1', 'annotation-2'] },
        { kind: 'contradict', statement: '同样的迁移时点呈现不同变化。', annotation_ids: ['annotation-1', 'annotation-2'] },
      ],
      competing_explanations: ['经济资源差异可能更关键。'],
      evidence_gaps: ['缺少其他照护者的叙述。'],
      next_steps: [{ kind: 'interview', action: '追访两个家庭的其他照护者。', priority: 'medium' }],
      theory_implication: '责任重组需要加入资源条件边界。',
    })
  })
})
