import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Fragment, type ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as researchApi from '../../api/researchWorkspace'
import { ResearchDocumentWorkbench } from './ResearchDocumentWorkbench'

vi.mock('../../api/client', () => ({ apiClient: {} }))
vi.mock('./ResearchMapCanvas', () => ({
  ResearchMapCanvas: ({ projection, expandedNodeContent, onSelectNode }: {
    projection: { nodes: Array<{ id: string; kind: string; title: string }> }
    expandedNodeContent: Readonly<Record<string, ReactNode>>
    onSelectNode: (node: { id: string; kind: string; title: string }) => void
  }) => (
    <section aria-label="研究论证地图">
      {projection.nodes.map((node) => <button type="button" key={node.id} aria-label={`${node.kind === 'document' ? '研究章节' : '研究节点'}：${node.title}`} onClick={() => onSelectNode(node)}>{node.title}</button>)}
      {Object.entries(expandedNodeContent).map(([id, content]) => <Fragment key={id}>{content}</Fragment>)}
    </section>
  ),
}))
vi.mock('../agent/ResearchAgentConversationPage', () => ({
  ResearchAgentConversationPage: ({ taskId, workspace }: { taskId: string | null; workspace: string }) => (
    <aside aria-label="研究 Agent 对话栏" data-task-id={taskId ?? ''} data-workspace={workspace} />
  ),
}))

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  window.localStorage.clear()
})

describe('ResearchDocumentWorkbench', () => {
  it('keeps document research on the canvas as editable section nodes beside the shared Agent', async () => {
    render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <Routes>
          <Route path="/research/:task_id/:stage" element={<ResearchDocumentWorkbench />} />
        </Routes>
      </MemoryRouter>,
    )

    const questionCard = await screen.findByRole('button', { name: '研究章节：研究问题' })
    expect(screen.getByRole('region', { name: '研究论证地图' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '研究章节：核心现象' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '研究章节：候选理论' })).toBeInTheDocument()
    fireEvent.click(questionCard)
    expect(screen.getByRole('region', { name: '研究文档节点' })).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: '文档结构' })).not.toBeInTheDocument()
    const agent = screen.getByRole('complementary', { name: '研究 Agent 对话栏' })
    expect(agent).toHaveAttribute('data-task-id', 'task-1')
    expect(agent).toHaveAttribute('data-workspace', 'research')
    expect(screen.getByText(/这一部分会随着研究推进形成可编辑内容/)).toBeInTheDocument()
    expect(document.querySelector('.research-document-editor .ProseMirror')).not.toBeInTheDocument()
  })

  it('lets the Agent panel be resized from the divider', async () => {
    const page = render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <Routes>
          <Route path="/research/:task_id/:stage" element={<ResearchDocumentWorkbench />} />
        </Routes>
      </MemoryRouter>,
    )

    const workspace = page.container.querySelector<HTMLElement>('.research-document-workbench__workspace')!
    Object.defineProperty(workspace, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({ width: 1000, height: 800, top: 0, right: 1000, bottom: 800, left: 0, x: 0, y: 0, toJSON: () => ({}) }),
    })
    const separator = screen.getByRole('separator', { name: '调整 Agent 对话栏宽度' })
    Object.defineProperty(separator, 'setPointerCapture', { configurable: true, value: vi.fn() })
    Object.defineProperty(separator, 'releasePointerCapture', { configurable: true, value: vi.fn() })

    fireEvent.pointerDown(separator, { pointerId: 1, clientX: 570 })
    fireEvent.pointerMove(separator, { pointerId: 1, clientX: 500 })
    fireEvent.pointerUp(separator, { pointerId: 1 })

    expect(separator).toHaveAttribute('aria-valuenow', '500')
    expect(workspace.style.getPropertyValue('--rdw-agent-width')).toBe('500px')
  })

  it('keeps mouse dragging available when pointer events are not emitted', () => {
    const page = render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <Routes>
          <Route path="/research/:task_id/:stage" element={<ResearchDocumentWorkbench />} />
        </Routes>
      </MemoryRouter>,
    )

    const workspace = page.container.querySelector<HTMLElement>('.research-document-workbench__workspace')!
    Object.defineProperty(workspace, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({ width: 1000, height: 800, top: 0, right: 1000, bottom: 800, left: 0, x: 0, y: 0, toJSON: () => ({}) }),
    })
    const separator = screen.getByRole('separator', { name: '调整 Agent 对话栏宽度' })

    fireEvent.mouseDown(separator, { button: 0, clientX: 570 })
    fireEvent.mouseMove(window, { clientX: 460 })
    fireEvent.mouseUp(window)

    expect(separator).toHaveAttribute('aria-valuenow', '540')
    expect(window.localStorage.getItem('qunxue.research.agent-panel-width')).toBe('540')
  })

  it('states the preview boundary when the research agent is not available', async () => {
    render(
      <MemoryRouter initialEntries={['/research/task-1/framework']}>
        <Routes>
          <Route path="/research/:task_id/:stage" element={<ResearchDocumentWorkbench />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: '研究章节：研究问题' }))
    expect(await screen.findByText(/当前 Agent 运行环境未连接/)).toBeInTheDocument()
    expect(screen.getAllByText(/不会把静态示例当作真实研究结果/).length).toBeGreaterThan(0)
  })

  it('starts M4 matching from the server navigation snapshot', async () => {
    const navigation = {
      task_id: 'task-1',
      version: 3,
      allowed_actions: ['start_matching'],
      blocker: null,
      retry: null,
      current_match_run_id: null,
      current_theory_plan_id: null,
      current_framework_id: null,
      knowledge_release_id: 'release-pinned-1',
      phenomenon_summary: {
        phenomenon: '社区互助为何减少？',
        phenomenon_query_id: 'phenomenon-1',
        research_intent: '解释互助变化机制',
        version: 2,
      },
      resume_path: '/research/task-1/match',
    }
    vi.spyOn(researchApi, 'getResearchTaskNavigation').mockResolvedValue({ data: navigation } as never)
    vi.spyOn(researchApi, 'listResearchDocuments').mockResolvedValue({ data: { items: [] } } as never)
    vi.spyOn(researchApi, 'listResearchTaskDocumentProposals').mockResolvedValue({ data: { items: [] } } as never)
    const createMatchRun = vi.spyOn(researchApi, 'createMatchRun').mockResolvedValue({
      data: {
        match_run_id: 'match-1',
        status: 'awaiting_decision',
        knowledge_release_id: 'release-pinned-1',
        candidate_page: {
          candidates: [{
            candidate_id: 'candidate-1',
            version: 1,
            title: '社会资本理论',
            applicability_rationale: '可解释稳定关系如何支持互助。',
          }],
        },
        failed_candidate_ids: [],
      },
    } as never)

    render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <Routes>
          <Route path="/research/:task_id/match" element={<ResearchDocumentWorkbench />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: '研究章节：候选理论' }))
    fireEvent.click(await screen.findByRole('button', { name: '开始理论匹配' }))

    expect(await screen.findByRole('heading', { name: '社会资本理论' })).toBeVisible()
    expect(createMatchRun).toHaveBeenCalledWith({
      path: { task_id: 'task-1' },
      headers: { 'Idempotency-Key': expect.any(String) },
      body: {
        expected_task_version: 3,
        phenomenon_query_id: 'phenomenon-1',
        phenomenon_version: 2,
        knowledge_release_id: 'release-pinned-1',
      },
    })
  })

  it('executes the server retry contract after an empty matching run', async () => {
    const navigation = {
      task_id: 'task-1',
      version: 4,
      allowed_actions: ['start_matching'],
      blocker: {
        code: 'no_reliable_candidate',
        message: '固定知识发布中没有可正式采用的理论候选，请调整研究现象后重试。',
        recoverable: true,
        action: 'start_matching',
      },
      retry: {
        method: 'POST',
        href: '/api/research-tasks/task-1/match-runs',
        action: 'start_matching',
        label: '重新匹配',
      },
      current_match_run_id: 'match-empty',
      current_theory_plan_id: null,
      current_framework_id: null,
      knowledge_release_id: 'release-pinned-1',
      phenomenon_summary: {
        phenomenon: '社区互助为何减少？',
        phenomenon_query_id: 'phenomenon-1',
        research_intent: null,
        version: 2,
      },
      resume_path: '/research/task-1/match',
    }
    vi.spyOn(researchApi, 'getResearchTaskNavigation').mockResolvedValue({ data: navigation } as never)
    vi.spyOn(researchApi, 'listResearchDocuments').mockResolvedValue({ data: { items: [] } } as never)
    vi.spyOn(researchApi, 'listResearchTaskDocumentProposals').mockResolvedValue({ data: { items: [] } } as never)
    vi.spyOn(researchApi, 'listTheoryDecisions').mockResolvedValue({ data: { decision_sets: [] } } as never)
    vi.spyOn(researchApi, 'getMatchRun').mockResolvedValue({
      data: {
        match_run_id: 'match-empty',
        status: 'no_reliable_candidate',
        knowledge_release_id: 'release-pinned-1',
        candidate_page: { candidates: [] },
        failed_candidate_ids: [],
      },
    } as never)
    const createMatchRun = vi.spyOn(researchApi, 'createMatchRun').mockResolvedValue({
      data: {
        match_run_id: 'match-retry',
        status: 'no_reliable_candidate',
        knowledge_release_id: 'release-pinned-1',
        candidate_page: { candidates: [] },
        failed_candidate_ids: [],
      },
    } as never)

    render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <Routes>
          <Route path="/research/:task_id/match" element={<ResearchDocumentWorkbench />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: '研究章节：候选理论' }))
    fireEvent.click(await screen.findByRole('button', { name: '重新匹配' }))

    await waitFor(() => expect(createMatchRun).toHaveBeenCalledTimes(1))
    expect(createMatchRun.mock.calls[0]?.[0].body.expected_task_version).toBe(4)
  })

  it('reuses one matching idempotency key after a network failure', async () => {
    const navigation = {
      task_id: 'task-1',
      version: 3,
      allowed_actions: ['start_matching'],
      blocker: null,
      retry: null,
      current_match_run_id: null,
      current_theory_plan_id: null,
      current_framework_id: null,
      knowledge_release_id: 'release-pinned-1',
      phenomenon_summary: {
        phenomenon: '社区互助为何减少？',
        phenomenon_query_id: 'phenomenon-1',
        research_intent: null,
        version: 2,
      },
      resume_path: '/research/task-1/match',
    }
    vi.spyOn(researchApi, 'getResearchTaskNavigation').mockResolvedValue({ data: navigation } as never)
    vi.spyOn(researchApi, 'listResearchDocuments').mockResolvedValue({ data: { items: [] } } as never)
    vi.spyOn(researchApi, 'listResearchTaskDocumentProposals').mockResolvedValue({ data: { items: [] } } as never)
    const createMatchRun = vi.spyOn(researchApi, 'createMatchRun')
      .mockRejectedValueOnce(new Error('网络连接中断'))
      .mockResolvedValueOnce({
        data: {
          match_run_id: 'match-after-retry',
          status: 'awaiting_decision',
          knowledge_release_id: 'release-pinned-1',
          candidate_page: { candidates: [] },
          failed_candidate_ids: [],
        },
      } as never)

    render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <Routes>
          <Route path="/research/:task_id/match" element={<ResearchDocumentWorkbench />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: '研究章节：候选理论' }))
    fireEvent.click(await screen.findByRole('button', { name: '开始理论匹配' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('网络连接中断')
    fireEvent.click(screen.getByRole('button', { name: '开始理论匹配' }))

    await waitFor(() => expect(createMatchRun).toHaveBeenCalledTimes(2))
    expect(createMatchRun.mock.calls.map(([options]) => options.headers['Idempotency-Key'])).toEqual([
      createMatchRun.mock.calls[0]?.[0].headers['Idempotency-Key'],
      createMatchRun.mock.calls[0]?.[0].headers['Idempotency-Key'],
    ])
  })

  it('enters M5 only through the latest server resume path after theory-plan confirmation', async () => {
    const navigation = {
      task_id: 'task-1',
      current_match_run_id: 'match-1',
      current_theory_plan_id: null,
      current_framework_id: null,
      knowledge_release_id: 'release-formal-1',
      phenomenon_summary: { phenomenon: '社区互助为何减少？' },
      resume_path: '/research/task-1/match',
    }
    vi.spyOn(researchApi, 'getResearchTaskNavigation').mockResolvedValue({ data: navigation } as never)
    vi.spyOn(researchApi, 'listResearchDocuments').mockResolvedValue({ data: { items: [] } } as never)
    vi.spyOn(researchApi, 'listResearchTaskDocumentProposals').mockResolvedValue({ data: { items: [] } } as never)
    vi.spyOn(researchApi, 'getMatchRun').mockResolvedValue({
      data: {
        match_run_id: 'match-1',
        knowledge_release_id: 'release-formal-1',
        candidate_page: { candidates: [] },
      },
    } as never)
    vi.spyOn(researchApi, 'listTheoryDecisions').mockResolvedValue({
      data: {
        decision_sets: [{
          decision_set_id: 'decision-set-1',
          version: 1,
          allowed_actions: ['confirm_theory_plan'],
          decisions: [],
        }],
      },
    } as never)
    vi.spyOn(researchApi, 'confirmTheoryPlan').mockResolvedValue({ data: { theory_plan_id: 'plan-1' } } as never)
    vi.spyOn(researchApi, 'readResearchTaskNavigationViaApi').mockResolvedValue({
      ...navigation,
      resume_path: '/research/task-1/framework',
    } as never)

    render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <Routes>
          <Route path="/research/:task_id/match" element={<ResearchDocumentWorkbench />} />
          <Route path="/research/:task_id/framework" element={<h1>M5 服务端恢复目标</h1>} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.queryByText('release-formal-1')).not.toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: '研究章节：候选理论' }))
    fireEvent.click(await screen.findByRole('button', { name: '确认理论方案，进入 M5' }))

    expect(await screen.findByRole('heading', { name: 'M5 服务端恢复目标' })).toBeVisible()
    await waitFor(() => expect(researchApi.readResearchTaskNavigationViaApi).toHaveBeenCalledWith('task-1'))
  })
})
