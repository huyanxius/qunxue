import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
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

// FE-01: a pending refresh must not render the previous account's cached research.
it.fails('hides the first account’s recent research while the second account is loading', async () => {
  const session = (userId: string) => Response.json({
    session_id: `session-${userId}`,
    status: 'active',
    version: 1,
    allowed_actions: ['logout'],
    user: { user_id: userId, email: `${userId}@example.invalid`, display_name: null },
    expires_at: '2026-12-01T00:00:00Z',
  })
  const firstTitle = '第一位研究者的合成课题'
  const listResearch = vi.fn()
    .mockResolvedValueOnce(Response.json({ items: [{
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
      phenomenon_summary: { phenomenon: firstTitle, research_intent: null },
      resume_path: '/research/task-1/phenomenon',
      retry: null,
      seed_theory_id: null,
      seed_theory_name: null,
      stage_label: '现象待确认',
      status: 'active',
      task_id: 'task-1',
      updated_at: '2026-08-08T08:00:00Z',
      version: 1,
    }], next_cursor: null }))
    .mockReturnValue(new Promise<Response>(() => {}))
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    switch (new URL(request.url).pathname) {
      case '/api/session': return session('first')
      case '/api/session/logout': return Response.json({
        session_id: 'session-first', status: 'revoked', version: 2, allowed_actions: [],
      })
      case '/api/session/login': return session('second')
      case '/api/research-tasks': return listResearch()
      default: return new Response(null, { status: 404 })
    }
  }))
  const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000 } } })
  render(
    <QueryClientProvider client={queryClient}>
      <AccountProvider><AccountResearch /></AccountProvider>
    </QueryClientProvider>,
  )
  expect(await screen.findByText(firstTitle)).toBeVisible()

  fireEvent.click(screen.getByRole('button', { name: '退出登录' }))
  fireEvent.click(await screen.findByRole('button', { name: '登录第二个账号' }))
  expect(await screen.findByText('second@example.invalid')).toBeVisible()
  await waitFor(() => expect(listResearch).toHaveBeenCalledTimes(2))

  expect(screen.queryByText(firstTitle)).not.toBeInTheDocument()
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
