import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { AccountProvider, useAccount } from './AccountProvider'

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
