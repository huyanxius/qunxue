import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
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

const secondResearch = {
  ...research,
  task_id: 'task-2',
  phenomenon_summary: { ...research.phenomenon_summary, phenomenon_query_id: 'phenomenon-2', phenomenon: '社区互助网络如何形成' },
  conversation_id: 'conversation-2',
  resume_path: '/research/task-2/match',
}

describe('ResearchMaterialsPage', () => {
  it('keeps the new-research guidance above the materials background when no research exists', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = new URL(input instanceof Request ? input.url : String(input), 'http://localhost').pathname
      if (path === '/api/research-tasks') return json({ items: [], next_cursor: null })
      return json({}, 404)
    }))

    render(
      <MemoryRouter initialEntries={['/research/materials']}>
        <ResearchMaterialsPage userId="user-1" />
      </MemoryRouter>,
    )

    const emptyState = await screen.findByRole('region', { name: '还没有研究' })
    expect(emptyState).toHaveTextContent('先建立一项研究')
    expect(within(emptyState).getByRole('link', { name: '新建研究' })).toHaveAttribute('href', '/research/new')
  })

  it('confirms when a material upload has finished', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = input instanceof Request ? input : new Request(String(input), init)
      const path = new URL(request.url, 'http://localhost').pathname
      if (path === '/api/research-tasks') return json({ items: [research], next_cursor: null })
      if (path === '/api/research-tasks/task-1/materials' && request.method === 'GET') {
        return json({ task_id: 'task-1', items: [] })
      }
      if (path === '/api/research-tasks/task-1/materials' && request.method === 'POST') {
        return json({
          material_id: 'material-audio', task_id: 'task-1', filename: '访谈.m4a',
          media_type: 'audio/mp4', size_bytes: 1024, status: 'uploaded', version: 1,
          parse_version: null, segment_count: 0, updated_at: '2026-09-02T10:00:00Z',
          error_code: null, material_kind: 'other',
        }, 201)
      }
      return json({}, 404)
    }))

    render(
      <MemoryRouter initialEntries={['/research/materials']}>
        <ResearchMaterialsPage userId="user-1" />
      </MemoryRouter>,
    )

    const library = await screen.findByRole('region', { name: '全部研究材料' })
    fireEvent.click(within(library).getByRole('button', { name: '添加材料' }))
    const input = within(library).getByRole('dialog', { name: '添加材料' })
      .querySelector<HTMLInputElement>('input[type="file"]')
    expect(input).not.toBeNull()
    fireEvent.change(input!, { target: { files: [new File(['audio'], '访谈.m4a', { type: 'audio/mp4' })] } })

    expect(await within(library).findByText('材料已添加')).toBeVisible()
    expect(within(library).getByRole('link', { name: /访谈\.m4a/ })).toBeVisible()
  })

  it('shows materials from every research as cards without a research-selection gate', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = new URL(input instanceof Request ? input.url : String(input), 'http://localhost').pathname
      if (path === '/api/research-tasks') return json({ items: [research, secondResearch], next_cursor: null })
      if (path === '/api/research-tasks/task-1/materials') return json({ task_id: 'task-1', items: [{ material_id: 'material-1', task_id: 'task-1', filename: '家庭照护访谈.md', media_type: 'text/markdown', size_bytes: 2048, status: 'ready', version: 1, parse_version: 1, segment_count: 12, updated_at: '2026-09-01T10:00:00Z', error_code: null, material_kind: 'interview_transcript' }] })
      if (path === '/api/research-tasks/task-2/materials') return json({ task_id: 'task-2', items: [{ material_id: 'material-2', task_id: 'task-2', filename: '社区观察记录.pdf', media_type: 'application/pdf', size_bytes: 4096, status: 'processing', version: 1, parse_version: null, segment_count: 0, updated_at: '2026-09-02T10:00:00Z', error_code: null, material_kind: 'observation_record' }] })
      return json({}, 404)
    }))

    render(
      <MemoryRouter initialEntries={['/research/materials']}>
        <ResearchMaterialsPage userId="user-1" />
      </MemoryRouter>,
    )

    const library = await screen.findByRole('region', { name: '全部研究材料' })
    expect(await within(library).findByRole('link', { name: /家庭照护访谈\.md/ })).toHaveAttribute('href', '/research/materials?task_id=task-1&material_id=material-1')
    expect(await within(library).findByRole('link', { name: /社区观察记录\.pdf/ })).toHaveAttribute('href', '/research/materials?task_id=task-2&material_id=material-2')
    expect(screen.queryByRole('region', { name: '选择研究' })).not.toBeInTheDocument()
    const addMaterialButton = within(library).getByRole('button', { name: '添加材料' })
    expect(addMaterialButton).toHaveAttribute('aria-expanded', 'false')
    expect(within(library).queryByRole('dialog', { name: '添加材料' })).not.toBeInTheDocument()

    fireEvent.click(addMaterialButton)

    const uploadPopover = within(library).getByRole('dialog', { name: '添加材料' })
    expect(uploadPopover).toBeVisible()
    expect(uploadPopover).toHaveClass('qx-popover-surface')
    expect(addMaterialButton).toHaveAttribute('aria-expanded', 'true')
    expect(within(library).getByRole('combobox', { name: '材料所属研究' })).toHaveValue('task-1')

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(within(library).queryByRole('dialog', { name: '添加材料' })).not.toBeInTheDocument()
    expect(addMaterialButton).toHaveAttribute('aria-expanded', 'false')
  })

  it('opens a selected material directly without another research workspace layer', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = new URL(input instanceof Request ? input.url : String(input), 'http://localhost').pathname
      if (path === '/api/research-tasks') return json({ items: [research], next_cursor: null })
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

    const reader = await screen.findByRole('region', { name: '材料阅读' })
    expect(within(reader).getByRole('region', { name: '研究材料' })).toBeVisible()
    expect(within(reader).getByRole('button', { name: '关闭研究材料' })).toBeVisible()
    expect(within(reader).queryByRole('complementary', { name: '研究 Agent 对话栏' })).not.toBeInTheDocument()
  })
})
