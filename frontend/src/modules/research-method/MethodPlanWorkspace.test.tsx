import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getCurrentMethodPlan: vi.fn(),
  listMethodPlanVersions: vi.fn(),
  updateMethodPlan: vi.fn(),
  reviewMethodPlan: vi.fn(),
}))

vi.mock('./researchMethodApi', () => api)

import { MethodPlanWorkspace } from './MethodPlanWorkspace'

afterEach(cleanup)

const plan = {
  plan_id: 'plan-1', task_id: 'task-1', framework_id: 'framework-1', framework_version: 1,
  theory_plan_id: 'theory-1', theory_plan_version: 1, method_kind: 'qualitative' as const,
  decision_source: 'system_recommendation', rationale: '系统建议', research_question: '问题',
  theory_summary: '理论', material_constraints: ['材料'], ethical_constraints: ['伦理'],
  theory_concepts: ['照护'], evidence_ref_ids: ['evidence-1'], knowledge_release_id: 'release-1',
  sections: [{ key: 'design', title: '研究设计', content: '原始设计', source: 'system' as const }],
  reviews: [], status: 'draft' as const, version: 1, revision_id: 'rev-1',
  change_summary: '创建', actor: 'system', created_at: '2026-08-31T00:00:00Z',
  restored_from_version: null, stale_reason: null, confirmed_at: null,
}

describe('MethodPlanWorkspace', () => {
  beforeEach(() => {
    api.getCurrentMethodPlan.mockResolvedValue(plan)
    api.listMethodPlanVersions.mockResolvedValue([plan])
    api.updateMethodPlan.mockImplementation(async (_id: string, input: typeof plan) => ({ ...plan, ...input, version: 2 }))
    api.reviewMethodPlan.mockImplementation(async (_id: string, input: { note: string; blocking: boolean }) => ({
      ...plan,
      version: 2,
      status: 'under_review',
      reviews: [{ review_id: 'review-1', note: input.note, blocking: input.blocking, created_at: '2026-08-31T00:00:00Z', resolved_at: null }],
    }))
  })

  it('does not expose the empty create state while the persisted plan is loading', () => {
    api.getCurrentMethodPlan.mockReturnValue(new Promise(() => undefined))
    render(<MethodPlanWorkspace taskId="task-1" />)
    expect(screen.getByRole('status')).toHaveTextContent('正在恢复方法计划')
    expect(screen.queryByRole('button', { name: '建立方法计划草案' })).not.toBeInTheDocument()
  })

  it('lets the researcher edit a plan section and persists it as a user decision', async () => {
    render(<MethodPlanWorkspace taskId="task-1" />)
    const workspace = await screen.findByRole('region', { name: '研究方法计划' })
    const section = await within(workspace).findByLabelText('研究设计')
    fireEvent.change(section, { target: { value: '解释性个案研究' } })
    fireEvent.click(within(workspace).getByRole('button', { name: '保存新版本' }))

    await waitFor(() => expect(api.updateMethodPlan).toHaveBeenCalled())
    expect(api.updateMethodPlan.mock.calls[0][1].sections[0]).toMatchObject({
      key: 'design', content: '解释性个案研究', source: 'user',
    })
  })

  it('submits the researcher review note and blocking choice', async () => {
    render(<MethodPlanWorkspace taskId="task-1" />)
    const workspace = await screen.findByRole('region', { name: '研究方法计划' })
    fireEvent.change(within(workspace).getByLabelText('审校意见'), { target: { value: '补充反身性边界' } })
    fireEvent.click(within(workspace).getByLabelText('阻断确认'))
    fireEvent.click(within(workspace).getByRole('button', { name: '提交审校' }))
    await waitFor(() => expect(api.reviewMethodPlan).toHaveBeenCalledWith('plan-1', {
      expected_version: 1,
      note: '补充反身性边界',
      blocking: true,
    }))
  })
})
