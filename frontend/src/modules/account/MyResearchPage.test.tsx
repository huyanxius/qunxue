import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { MyResearchPage } from './MyResearchPage'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MyResearchPage />
    </QueryClientProvider>,
  )
}

it('shows the real stage entry path and requires a second delete confirmation', async () => {
  let deleted = false
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const request = input as Request
    if (request.method === 'DELETE') {
      deleted = true
      return new Response(JSON.stringify({
        task_id: '95306bf9-194d-4677-be2d-eef4f6aa86d1',
        version: 2,
        allowed_actions: [],
        deleted: true,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }
    return new Response(JSON.stringify({
      items: [{
        task_id: '95306bf9-194d-4677-be2d-eef4f6aa86d1',
        entry_type: 'direct_input',
        status: 'in_progress',
        current_stage: 'theory_matching',
        version: 4,
        allowed_actions: ['review_theory_candidates'],
        seed_theory_id: null,
        phenomenon_summary: {
          phenomenon_query_id: '59f192dd-85fc-41bf-abaf-d66caa7df958',
          version: 2,
          phenomenon: '成员流动后，社区互助为何持续减少？',
          research_intent: null,
        },
        adopted_theory_count: 2,
        current_phenomenon_candidate_id: null,
        current_match_run_id: 'b32448bd-18ef-44a4-89fc-e24d735edfb6',
        current_framework_id: null,
        created_at: '2026-08-07T00:00:00Z',
        updated_at: '2026-08-07T01:00:00Z',
      }],
      next_cursor: null,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }))
  renderPage()

  expect(await screen.findByRole('link', { name: '继续研究' })).toHaveAttribute(
    'href',
    '/research/95306bf9-194d-4677-be2d-eef4f6aa86d1/match',
  )
  expect(screen.getByText('匹配生成中')).toBeVisible()
  expect(screen.getByText('成员流动后，社区互助为何持续减少？')).toBeVisible()
  expect(screen.getByText(/已采用 2 个理论/)).toBeVisible()
  expect(screen.getByText(/创建于/)).toBeVisible()
  expect(screen.getByText(/更新于/)).toBeVisible()

  fireEvent.click(screen.getByRole('button', { name: '删除研究' }))
  expect(deleted).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: '确认永久删除' }))

  await waitFor(() => expect(deleted).toBe(true))
  expect(await screen.findByText('还没有研究任务。')).toBeVisible()
})

it('retries the real research list after a service failure', async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({
      error: { code: 'internal_server_error', message: 'failed', trace_id: 'trace-1' },
    }), { status: 500, headers: { 'Content-Type': 'application/json' } }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ items: [], next_cursor: null }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
  vi.stubGlobal('fetch', fetchMock)
  renderPage()

  expect(await screen.findByText('暂时无法读取研究列表，请稍后重试。')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: '重试' }))

  expect(await screen.findByText('还没有研究任务。')).toBeVisible()
  expect(fetchMock).toHaveBeenCalledTimes(2)
})
