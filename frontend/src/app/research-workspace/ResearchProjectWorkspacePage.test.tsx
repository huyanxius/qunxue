import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useState, type ReactNode } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ResearchDocumentWorkspaceContext } from './ResearchDocumentWorkbench'
import { ResearchProjectWorkspacePage } from './ResearchProjectWorkspacePage'

const agentInstances = vi.hoisted(() => ({ count: 0 }))

vi.mock('../agent/ResearchAgentConversationPage', () => ({
  ResearchAgentConversationPage: ({ conversationId, taskId, onConversationStarted }: { conversationId: string; taskId: string; onConversationStarted?: (identity: { conversation_id: string; task_id: string }) => void }) => {
    const [instance] = useState(() => ++agentInstances.count)
    return <aside aria-label="研究 Agent 对话栏" data-instance={instance}>{conversationId}:{taskId}<button onClick={() => onConversationStarted?.({ conversation_id: 'conversation-created', task_id: taskId })}>开始首轮</button></aside>
  },
}))

vi.mock('./ResearchDocumentWorkbench', () => ({
  ResearchDocumentWorkbench: ({ workspaceMode, onWorkspaceContextChange }: { workspaceMode: string; onWorkspaceContextChange?: (context: ResearchDocumentWorkspaceContext) => void }) => (
    <section aria-label="文档中心">{workspaceMode}<button onClick={() => onWorkspaceContextChange?.({ mode: 'framework', documentId: 'document-1', sectionId: 'research_question', documentVersion: 2, theoryPlanId: null })}>定位章节</button></section>
  ),
}))

vi.mock('../../modules/research-materials', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../modules/research-materials')>()
  return {
    ...actual,
    ResearchMaterialsPanel: ({ initialMaterialId, initialSegmentId, agentPanel, analysisPanel, workspaceNavigation, onWorkspaceLocationChange }: {
      onWorkspaceLocationChange?: (next: { materialId: string; parseId: string; segmentId: string }) => void
      agentPanel?: ReactNode
      analysisPanel?: ReactNode
      workspaceNavigation?: ReactNode
      initialMaterialId: string | null
      initialSegmentId: string | null
    }) => <section aria-label="材料中心">{initialMaterialId}:{initialSegmentId}{workspaceNavigation}{analysisPanel}{agentPanel}<button onClick={() => onWorkspaceLocationChange?.({ materialId: 'material-2', parseId: 'parse-2', segmentId: 'segment-2' })}>定位材料</button></section>,
    ResearchAnalysisPanel: () => <section aria-label="分析中心">分析</section>,
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

function renderWorkspace(path: string, conversationTaskId = 'task-1', primaryConversationId: string | null = 'conversation-1') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(input instanceof Request ? input.url : input)
    if (url.pathname === '/api/agent/conversations/conversation-b') return json({ conversation_id: 'conversation-b', task_id: conversationTaskId, title: '后续对话', created_at: '2026-09-05T00:00:00Z', updated_at: '2026-09-05T00:00:00Z', turn_count: 0, turns: [] })
    if (url.pathname === '/api/research-tasks/task-1/navigation') return json({ ...navigation(), conversation_id: primaryConversationId })
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
  it('preserves a later project conversation through tool navigation', async () => {
    renderWorkspace('/research/task-1/workspace/map?conversation_id=conversation-b')
    const tools = await screen.findByRole('navigation', { name: '研究中心工具' })
    expect(screen.getByRole('complementary', { name: '研究 Agent 对话栏' })).toHaveTextContent('conversation-b:task-1')
    expect(within(tools).getByRole('link', { name: '文稿' })).toHaveAttribute('href', '/research/task-1/workspace/writing?conversation_id=conversation-b')
    fireEvent.click(within(tools).getByRole('link', { name: '文稿' }))
    expect(screen.getByLabelText('当前地址')).toHaveTextContent('/research/task-1/workspace/writing?conversation_id=conversation-b')
    const requests = vi.mocked(fetch).mock.calls.map(([input]) => new URL(input instanceof Request ? input.url : String(input)).pathname)
    expect(requests).toContain('/api/agent/conversations/conversation-b')
  })

  it('rejects a conversation from another project before displaying the workspace', async () => {
    renderWorkspace('/research/task-1/workspace/map?conversation_id=conversation-b', 'another-task')
    expect(await screen.findByText('这段对话不属于当前研究项目。')).toBeVisible()
    expect(screen.queryByRole('navigation', { name: '研究中心工具' })).not.toBeInTheDocument()
  })

  it('preserves explicit conversation identity when resolving a missing tool', async () => {
    renderWorkspace('/research/task-1/workspace?conversation_id=conversation-b')
    await waitFor(() => expect(screen.getByLabelText('当前地址')).toHaveTextContent('/research/task-1/workspace/materials?conversation_id=conversation-b'))
  })

  it('preserves conversation identity when selecting a document section', async () => {
    renderWorkspace('/research/task-1/workspace/writing?conversation_id=conversation-b')
    fireEvent.click(await screen.findByRole('button', { name: '定位章节' }))
    expect(screen.getByLabelText('当前地址')).toHaveTextContent('/research/task-1/workspace/writing?document_id=document-1&section_id=research_question&version=2&conversation_id=conversation-b')
  })

  it('preserves conversation identity when locating a material segment', async () => {
    renderWorkspace('/research/task-1/workspace/materials?material_id=material-1&conversation_id=conversation-b&batch_run_id=batch-1')
    fireEvent.click(await screen.findByRole('button', { name: '定位材料' }))
    expect(screen.getByLabelText('当前地址')).toHaveTextContent('/research/task-1/workspace/materials?material_id=material-2&parse_id=parse-2&segment_id=segment-2&batch_run_id=batch-1&conversation_id=conversation-b')
  })

  it('records the first conversation before completion without remounting the active Agent', async () => {
    renderWorkspace('/research/task-1/workspace/map', 'task-1', null)
    fireEvent.click(await screen.findByRole('button', { name: '开始首轮' }))
    expect(screen.getByLabelText('当前地址')).toHaveTextContent('/research/task-1/workspace/map?conversation_id=conversation-created')
    expect(screen.getByRole('complementary', { name: '研究 Agent 对话栏' })).toHaveAttribute('data-instance', '1')
    fireEvent.click(screen.getByRole('link', { name: '材料' }))
    expect(screen.getByLabelText('当前地址')).toHaveTextContent('/research/task-1/workspace/materials?conversation_id=conversation-created')
    expect(screen.getByRole('complementary', { name: '研究 Agent 对话栏' })).toHaveTextContent('conversation-created:task-1')
  })

  it('opens the document full screen with the project Agent and analysis inside the reader', async () => {
    renderWorkspace('/research/task-1/workspace/materials?material_id=material-1&segment_id=segment-1')
    const reader = await screen.findByRole('region', { name: '材料中心' })
    expect(reader).toHaveTextContent('material-1:segment-1')
    expect(within(reader).getByRole('complementary', { name: '研究 Agent 对话栏' })).toHaveTextContent('conversation-1:task-1')
    expect(within(reader).getByRole('region', { name: '分析中心' })).toBeVisible()
    expect(within(reader).getByRole('link', { name: '返回材料库' })).toHaveAttribute('href', '/research/materials')
    expect(screen.queryByRole('navigation', { name: '桌面主导航' })).not.toBeInTheDocument()
    expect(screen.queryByTestId('research-workspace-layout')).not.toBeInTheDocument()
  })

  it('uses the project lifecycle central tool when opening the workspace without a tool', async () => {
    renderWorkspace('/research/task-1/workspace')

    await waitFor(() => expect(screen.getByLabelText('当前地址')).toHaveTextContent(
      '/research/task-1/workspace/materials',
    ), { timeout: 5000 })
    expect(screen.getByRole('region', { name: '材料中心' })).toBeVisible()
    expect(screen.getByRole('navigation', { name: '桌面主导航' })).toBeVisible()
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

  it('switches the mobile workspace between content and Agent without remounting either pane', async () => {
    renderWorkspace('/research/task-1/workspace/materials')

    const switcher = await screen.findByRole('group', { name: '移动工作区视图' })
    const layout = screen.getByTestId('research-workspace-layout')
    const agent = screen.getByRole('complementary', { name: '研究 Agent 对话栏' })

    expect(layout).toHaveAttribute('data-mobile-pane', 'center')
    expect(within(switcher).getByRole('button', { name: '内容' })).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(within(switcher).getByRole('button', { name: 'Agent' }))

    expect(layout).toHaveAttribute('data-mobile-pane', 'agent')
    expect(within(switcher).getByRole('button', { name: 'Agent' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('complementary', { name: '研究 Agent 对话栏' })).toBe(agent)
    expect(agent).toHaveAttribute('data-instance', '1')
  })
})
