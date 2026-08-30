import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ResearchMaterialsPage } from './ResearchMaterialsPage'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  window.localStorage.clear()
  window.sessionStorage.clear()
})

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const research = {
  task_id: 'task-1', entry_type: 'direct_input', status: 'in_progress',
  current_stage: 'theory_matching', stage_label: '理论判断', next_action_label: '继续理论判断', version: 2,
  allowed_actions: ['review_theory_candidates'], seed_theory_id: null, seed_theory_name: null,
  phenomenon_summary: { phenomenon_query_id: 'phenomenon-1', version: 1, phenomenon: '照护劳动如何被家庭成员重新分配', research_intent: '理解家庭内部的责任协商' },
  adopted_theory_count: 1, current_phenomenon_candidate_id: 'candidate-1', current_material_intake_run_id: null,
  current_match_run_id: 'match-1', current_theory_plan_id: null, current_framework_id: null,
  resume_path: '/research/task-1/match', blocker: null, retry: null,
  knowledge_release_id: 'release-1', conversation_id: 'conversation-1', source_turn_id: 'turn-1',
  created_at: '2026-08-30T00:00:00Z', updated_at: '2026-08-30T01:00:00Z',
}

describe('ResearchMaterialsPage', () => {
  it('keeps project scope, source workspace, and the shared Agent visible together', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = new URL(input instanceof Request ? input.url : String(input), 'http://localhost').pathname
      if (path === '/api/research-tasks') return json({ items: [research], next_cursor: null })
      if (path === '/api/research-tasks/task-1/navigation') return json(research)
      if (path === '/api/research-tasks/task-1/materials') return json({ task_id: 'task-1', items: [] })
      if (path === '/api/research-tasks/task-1/analysis') return json({ task_id: 'task-1', annotations: [], codes: [], memos: [], comparisons: [] })
      if (path === '/api/agent/conversations/conversation-1') return json({ conversation_id: 'conversation-1', title: '照护劳动研究', created_at: research.created_at, updated_at: research.updated_at, turn_count: 0, turns: [] })
      if (path === '/api/agent/conversations') return json({ items: [], next_cursor: null })
      return json({}, 404)
    }))

    render(
      <MemoryRouter initialEntries={['/research/materials?task_id=task-1']}>
        <ResearchMaterialsPage userId="user-1" />
      </MemoryRouter>,
    )

    const workbench = await screen.findByRole('region', { name: '研究材料工作台' })
    expect(within(workbench).getByRole('combobox', { name: '当前研究' })).toHaveValue('task-1')
    expect(within(workbench).getByRole('link', { name: '返回研究选择' })).toHaveAttribute('href', '/research/materials')
    expect(within(workbench).getByRole('link', { name: '返回这项研究' })).toHaveAttribute('href', '/research/task-1/match')
    expect(within(workbench).getByRole('region', { name: '研究材料' })).toBeVisible()
    expect(within(workbench).getByRole('complementary', { name: '研究 Agent 对话栏' })).toBeVisible()
    expect(within(workbench).queryByRole('dialog', { name: '研究材料' })).not.toBeInTheDocument()
  })
})
