import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ResearchProjectWorkspacePage } from './ResearchProjectWorkspacePage'

const agentInstances = vi.hoisted(() => ({ count: 0 }))

vi.mock('../agent/ResearchAgentConversationPage', () => ({
  ResearchAgentConversationPage: ({ conversationId, taskId }: { conversationId: string; taskId: string }) => {
    const [instance] = useState(() => ++agentInstances.count)
    return <aside aria-label="研究 Agent 对话栏" data-instance={instance}>{conversationId}:{taskId}</aside>
  },
}))

vi.mock('./ResearchDocumentWorkbench', () => ({
  ResearchDocumentWorkbench: ({ workspaceMode }: { workspaceMode: string }) => (
    <section aria-label="文档中心">{workspaceMode}</section>
  ),
}))

vi.mock('../../modules/research-materials', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../modules/research-materials')>()
  return {
    ...actual,
    ResearchMaterialsPanel: ({ initialDetailMode, initialMaterialId, initialSegmentId }: {
      initialDetailMode: string
      initialMaterialId: string | null
      initialSegmentId: string | null
    }) => <section aria-label="材料中心">{initialDetailMode}:{initialMaterialId}:{initialSegmentId}</section>,
  }
})

vi.mock('../../modules/research-method', () => ({
  MethodPlanWorkspace: () => <section aria-label="方法中心">方法</section>,
}))

vi.mock('../../modules/research-exchange', () => ({
  ResearchArchivePanel: () => <section aria-label="项目归档与交换">归档</section>,
}))

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  agentInstances.count = 0
  window.localStorage.clear()
})

function json(body: unknown) {
  return Response.json(body, { headers: { 'Content-Type': 'application/json' } })
}

function task() {
  return {
    task_id: 'task-1',
    entry_type: 'material_input',
    entry_mode: 'existing_research',
    lifecycle_status: 'in_progress',
    project_title: '社区照护田野研究',
    project_stage: '分析与编码',
    method_orientation: '质性访谈',
    last_central_tool: 'materials',
    status: 'draft',
    version: 1,
    allowed_actions: ['submit_phenomenon'],
    seed_theory_id: null,
    seed_theory_name: null,
    created_at: '2026-08-31T00:00:00Z',
    updated_at: '2026-08-31T00:00:00Z',
  }
}

function navigation() {
  return {
    task_id: 'task-1',
    conversation_id: 'conversation-1',
    knowledge_release_id: 'release-1',
    current_theory_plan_id: 'theory-plan-1',
    current_framework_id: 'framework-1',
    resume_path: '/research/task-1/phenomenon',
  }
}

function LocationProbe() {
  const location = useLocation()
  return <output aria-label="当前地址">{location.pathname}{location.search}</output>
}

function renderWorkspace(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(input instanceof Request ? input.url : input)
    if (url.pathname === '/api/research-tasks/task-1/navigation') return json(navigation())
    if (url.pathname === '/api/research-tasks/task-1') return json(task())
    return json({})
  }))
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/research/:task_id/workspace/:tool?" element={<ResearchProjectWorkspacePage userId="user-1" />} />
        </Routes>
        <LocationProbe />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('ResearchProjectWorkspacePage', () => {
  it('keeps one project-bound Agent mounted while central tools change', async () => {
    renderWorkspace('/research/task-1/workspace/materials?material_id=material-1&segment_id=segment-1')

    expect(await screen.findByRole('heading', { name: '社区照护田野研究' })).toBeVisible()
    expect(screen.getByRole('region', { name: '材料中心' })).toHaveTextContent('source:material-1:segment-1')
    const agent = screen.getByRole('complementary', { name: '研究 Agent 对话栏' })
    expect(agent).toHaveAttribute('data-instance', '1')
    expect(agent).toHaveTextContent('conversation-1:task-1')

    fireEvent.click(screen.getByRole('link', { name: '分析' }))

    expect(await screen.findByRole('region', { name: '材料中心' })).toHaveTextContent('analysis::')
    expect(screen.getByRole('complementary', { name: '研究 Agent 对话栏' })).toHaveAttribute('data-instance', '1')
    expect(screen.getByLabelText('当前地址')).toHaveTextContent('/research/task-1/workspace/analysis')
  })

  it('uses the project lifecycle central tool when opening the workspace without a tool', async () => {
    renderWorkspace('/research/task-1/workspace')

    await waitFor(() => expect(screen.getByLabelText('当前地址')).toHaveTextContent(
      '/research/task-1/workspace/materials',
    ))
    expect(screen.getByRole('region', { name: '材料中心' })).toBeVisible()
  })

  it('adds project archive through the unified workspace public route', async () => {
    renderWorkspace('/research/task-1/workspace/map')

    const navigation = await screen.findByRole('navigation', { name: '研究中心工具' })
    expect(navigation.querySelectorAll('a')).toHaveLength(7)
    expect(screen.getByRole('link', { name: '地图' })).toHaveAttribute('href', '/research/task-1/workspace/map')
    expect(screen.getByRole('link', { name: '文稿' })).toHaveAttribute('href', '/research/task-1/workspace/writing')
    expect(screen.getByRole('link', { name: '归档' })).toHaveAttribute('href', '/research/task-1/workspace/archive')

    fireEvent.click(screen.getByRole('link', { name: '归档' }))
    expect(await screen.findByRole('region', { name: '项目归档与交换' })).toBeVisible()
    expect(screen.getByRole('complementary', { name: '研究 Agent 对话栏' })).toHaveAttribute('data-instance', '1')
  })
})
