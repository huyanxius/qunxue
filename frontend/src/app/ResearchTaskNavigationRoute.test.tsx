import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation, useNavigate, useParams } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ResearchTaskNavigationRoute } from './ResearchTaskNavigationRoute'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function navigation(resumePath: string) {
  return {
    adopted_theory_count: 0,
    allowed_actions: ['review_theory_candidates'],
    blocker: null,
    conversation_id: 'conversation-1',
    created_at: '2026-08-21T08:00:00Z',
    current_framework_id: null,
    current_match_run_id: 'match-1',
    current_material_intake_run_id: null,
    current_phenomenon_candidate_id: null,
    current_stage: 'theory_matching',
    current_theory_plan_id: null,
    entry_type: 'direct_input',
    knowledge_release_id: 'release-formal-1',
    next_action_label: '查看候选理论',
    phenomenon_summary: null,
    resume_path: resumePath,
    retry: null,
    seed_theory_id: null,
    seed_theory_name: null,
    source_run_id: 'run-1',
    source_turn_id: 'turn-1',
    stage_label: '匹配生成中',
    status: 'in_progress',
    task_id: 'task-1',
    updated_at: '2026-08-21T09:00:00Z',
    version: 3,
  }
}

function LocationProbe() {
  const location = useLocation()
  return <output aria-label="当前地址">{location.pathname}{location.search}</output>
}

function StageProbe() {
  const { stage } = useParams<{ stage?: string }>()
  return <h1>{stage ?? 'canonical'}</h1>
}

function NavigationControls() {
  const navigate = useNavigate()
  return (
    <>
      <button type="button" onClick={() => navigate(-1)}>返回上一页</button>
      <button type="button" onClick={() => navigate('/app?research=all')}>打开全部研究</button>
      <button type="button" onClick={() => navigate('/research/task-1/match')}>重新打开研究</button>
    </>
  )
}

function renderNavigationRoute(path: string, initialEntries = [path]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={initialEntries} initialIndex={initialEntries.length - 1}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/app" element={<h1>工作台</h1>} />
          <Route
            path="/research/:task_id"
            element={<ResearchTaskNavigationRoute><StageProbe /></ResearchTaskNavigationRoute>}
          />
          <Route
            path="/research/:task_id/:stage"
            element={<ResearchTaskNavigationRoute><StageProbe /></ResearchTaskNavigationRoute>}
          />
        </Routes>
        <LocationProbe />
        <NavigationControls />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('ResearchTaskNavigationRoute', () => {
  it('loads server navigation before rendering a canonical stage route', async () => {
    let resolveNavigation!: (response: Response) => void
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => {
      resolveNavigation = resolve
    }))
    vi.stubGlobal('fetch', fetchMock)

    renderNavigationRoute('/research/task-1/match')

    expect(screen.queryByRole('heading', { name: 'match' })).not.toBeInTheDocument()
    expect(screen.getByText('正在恢复研究进度')).toBeVisible()
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())

    resolveNavigation(new Response(JSON.stringify(navigation('/research/task-1/match')), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))

    expect(await screen.findByRole('heading', { name: 'match' })).toBeVisible()
  })

  it('keeps an explicit stage route stable instead of jumping to the server resume path', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      JSON.stringify(navigation('/research/task-1/match')),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    )))

    renderNavigationRoute(
      '/research/task-1/framework',
      ['/app?research=all', '/research/task-1/framework'],
    )

    expect(await screen.findByRole('heading', { name: 'framework' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'match' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('当前地址')).toHaveTextContent('/research/task-1/framework')

    fireEvent.click(screen.getByRole('button', { name: '返回上一页' }))
    expect(await screen.findByRole('heading', { name: '工作台' })).toBeVisible()
  })

  it('resolves the task-only entry through the same server resume path', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      JSON.stringify(navigation('/research/task-1/match')),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    )))

    renderNavigationRoute('/research/task-1')

    expect(await screen.findByRole('heading', { name: 'match' })).toBeVisible()
    expect(screen.getByLabelText('当前地址')).toHaveTextContent('/research/task-1/match')
  })

  it('keeps retry and return actions available when navigation cannot be loaded', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ error: { code: 'offline' } }), {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify(navigation('/research/task-1/match')), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
    vi.stubGlobal('fetch', fetchMock)

    renderNavigationRoute('/research/task-1/match')

    const failure = await screen.findByRole('alert')
    expect(failure).toHaveTextContent('研究进度暂时无法恢复')
    expect(screen.getByRole('link', { name: '返回工作台' })).toHaveAttribute('href', '/app?research=all')
    fireEvent.click(screen.getByRole('button', { name: '重试' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'match' })).toBeVisible())
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('refuses a resume path that escapes the requested research task', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      JSON.stringify(navigation('/research/another-task/match')),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    )))

    renderNavigationRoute('/research/task-1')

    expect(await screen.findByRole('alert')).toHaveTextContent('研究进度暂时无法恢复')
    expect(screen.getByLabelText('当前地址')).toHaveTextContent('/research/task-1')
    expect(screen.queryByRole('heading', { name: 'match' })).not.toBeInTheDocument()
  })

  it('waits for fresh server navigation when a cached task is reopened from the workbench archive', async () => {
    let resolveReopenedNavigation!: (response: Response) => void
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(navigation('/research/task-1/match')), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => {
        resolveReopenedNavigation = resolve
      }))
    vi.stubGlobal('fetch', fetchMock)

    renderNavigationRoute('/research/task-1/match')
    expect(await screen.findByRole('heading', { name: 'match' })).toBeVisible()

    fireEvent.click(screen.getByRole('button', { name: '打开全部研究' }))
    expect(await screen.findByRole('heading', { name: '工作台' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: '重新打开研究' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(screen.queryByRole('heading', { name: 'match' })).not.toBeInTheDocument()
    expect(screen.getByText('正在恢复研究进度')).toBeVisible()

    resolveReopenedNavigation(new Response(JSON.stringify(navigation('/research/task-1/match')), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    expect(await screen.findByRole('heading', { name: 'match' })).toBeVisible()
  })
})
