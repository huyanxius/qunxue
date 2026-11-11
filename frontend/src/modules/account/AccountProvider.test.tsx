import { QueryClient, QueryClientProvider, QueryObserver } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { AccountProvider, useAccount } from './AccountProvider'
import { RecentResearchPanel } from './RecentResearchPanel'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

it('marks an established session as expired after a protected API returns 401', async () => {
  let sessionReads = 0
  const fetchMock = vi.fn(async () => {
    sessionReads += 1
    if (sessionReads === 1) {
      return new Response(JSON.stringify({
        session_id: '25b191bb-2d85-4a88-8863-2cabf506a7a8',
        status: 'active',
        version: 1,
        allowed_actions: ['logout'],
        user: { user_id: '95306bf9-194d-4677-be2d-eef4f6aa86d1', email: 'researcher@example.com', display_name: null },
        expires_at: '2026-08-14T00:00:00Z',
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }
    return new Response(
      JSON.stringify({ error: { code: 'unauthenticated', message: '请先登录。', trace_id: 'trace-2' } }),
      { status: 401, headers: { 'Content-Type': 'application/json' } },
    )
  })
  vi.stubGlobal('fetch', fetchMock)
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <AccountProvider><SessionProbe /></AccountProvider>
    </QueryClientProvider>,
  )
  expect(await screen.findByText('authenticated')).toBeVisible()

  fireEvent.click(screen.getByRole('button', { name: '重新读取会话' }))

  await waitFor(() => expect(screen.getByText('expired')).toBeVisible())
})

function SessionProbe() {
  const { retrySession, sessionState } = useAccount()
  return (
    <>
      <span>{sessionState.status}</span>
      <button type="button" onClick={retrySession}>重新读取会话</button>
    </>
  )
}

function researchResponse(taskId: string, title: string) {
  return Response.json({ items: [{
    adopted_theory_count: 0,
    allowed_actions: ['confirm_phenomenon'],
    blocker: null,
    created_at: '2026-08-08T08:00:00Z',
    current_framework_id: null,
    current_match_run_id: null,
    current_material_intake_run_id: null,
    current_phenomenon_candidate_id: 'candidate-1',
    current_stage: 'phenomenon_confirmation',
    entry_type: 'direct',
    next_action_label: '确认现象',
    phenomenon_summary: { phenomenon: title, research_intent: null },
    resume_path: `/research/${taskId}/phenomenon`,
    retry: null,
    seed_theory_id: null,
    seed_theory_name: null,
    stage_label: '现象待确认',
    status: 'active',
    task_id: taskId,
    updated_at: '2026-08-08T08:00:00Z',
    version: 1,
  }], next_cursor: null })
}

function renderAccountResearch(listResearch: (request: Request) => Promise<Response>) {
  const session = (userId: string) => Response.json({
    session_id: `session-${userId}`,
    status: 'active',
    version: 1,
    allowed_actions: ['logout'],
    user: { user_id: userId, email: `${userId}@example.invalid`, display_name: null },
    expires_at: '2026-12-01T00:00:00Z',
  })
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    switch (new URL(request.url).pathname) {
      case '/api/session': return session('first')
      case '/api/session/logout': return Response.json({
        session_id: 'session-first', status: 'revoked', version: 2, allowed_actions: [],
      })
      case '/api/session/login': return session('second')
      case '/api/research-tasks': return listResearch(request)
      default: return new Response(null, { status: 404 })
    }
  }))
  const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000 } } })
  render(
    <QueryClientProvider client={queryClient}>
      <AccountProvider><AccountResearch /></AccountProvider>
    </QueryClientProvider>,
  )
  return queryClient
}

async function switchToSecondAccount() {
  fireEvent.click(screen.getByRole('button', { name: '退出登录' }))
  fireEvent.click(await screen.findByRole('button', { name: '登录第二个账号' }))
  expect(await screen.findByText('second@example.invalid')).toBeVisible()
}

// FE-01: a pending refresh must not render the previous account's cached research.
it('hides the first account’s recent research while the second account is loading', async () => {
  const firstTitle = '第一位研究者的合成课题'
  const listResearch = vi.fn()
    .mockResolvedValueOnce(researchResponse('task-1', firstTitle))
    .mockReturnValue(new Promise<Response>(() => {}))
  renderAccountResearch(listResearch)
  expect(await screen.findByText(firstTitle)).toBeVisible()

  await switchToSecondAccount()
  await waitFor(() => expect(listResearch).toHaveBeenCalledTimes(2))

  expect(screen.queryByText(firstTitle)).not.toBeInTheDocument()
})

function deferredResponse() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((complete) => { resolve = complete })
  return { promise, resolve }
}

it.each([200, 401])('ignores a late %i response from the previous session’s research request', async (status) => {
  const first = deferredResponse()
  const second = deferredResponse()
  const listResearch = vi.fn<(request: Request) => Promise<Response>>()
    .mockReturnValueOnce(first.promise)
    .mockReturnValueOnce(second.promise)
  const queryClient = renderAccountResearch(listResearch)
  const knowledgeKey = ['knowledge', 'home-preview']
  queryClient.setQueryData(knowledgeKey, '公共知识预览')
  await waitFor(() => expect(listResearch).toHaveBeenCalledTimes(1))
  const [firstQuery] = queryClient.getQueryCache().findAll({ fetchStatus: 'fetching' })

  await switchToSecondAccount()
  const [currentQuery] = queryClient.getQueryCache().findAll({ fetchStatus: 'fetching' })
  const observer = new QueryObserver(queryClient, { queryKey: currentQuery.queryKey, enabled: false })
  const unsubscribe = observer.subscribe(() => undefined)
  try {
    const firstTitle = '迟到的第一位研究者课题'
    const lateResponse = status === 200
      ? researchResponse('task-1', firstTitle)
      : Response.json({ error: { code: 'unauthenticated' } }, { status })
    const readResponse = vi.spyOn(lateResponse, 'text')
    first.resolve(lateResponse)
    await waitFor(() => expect(readResponse).toHaveBeenCalledOnce())
    await act(async () => { await readResponse.mock.results[0].value })

    expect(observer.getCurrentResult()).toMatchObject({ data: undefined, isPending: true })
    expect(screen.getByText('second@example.invalid')).toBeVisible()
    expect(screen.queryByText(firstTitle)).not.toBeInTheDocument()
    expect(listResearch.mock.calls[0][0].signal.aborted).toBe(true)
    expect(queryClient.getQueryState(firstQuery.queryKey)).toBeUndefined()
    expect(queryClient.getQueryData(knowledgeKey)).toBe('公共知识预览')

    const secondTitle = '第二位研究者的合成课题'
    second.resolve(researchResponse('task-2', secondTitle))
    expect(await screen.findByText(secondTitle)).toBeVisible()
  } finally {
    unsubscribe()
  }
})

function AccountResearch() {
  const { sessionState, login, logout } = useAccount()
  if (sessionState.status === 'anonymous') {
    return (
      <button type="button" onClick={() => void login('second@example.invalid', 'test-password')}>
        登录第二个账号
      </button>
    )
  }
  if (sessionState.status !== 'authenticated') return null
  return (
    <>
      <p>{sessionState.session.user.email}</p>
      <button type="button" onClick={() => void logout()}>退出登录</button>
      <RecentResearchPanel />
    </>
  )
}
