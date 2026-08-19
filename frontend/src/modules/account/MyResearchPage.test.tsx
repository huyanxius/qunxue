import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

it('shows a scannable research row and requires dialog confirmation before deletion', async () => {
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

  expect(await screen.findByRole('row', { name: /成员流动后，社区互助为何持续减少/ })).toBeVisible()
  expect(screen.getByText('下一步：查看候选理论')).toBeVisible()
  expect(screen.getByText('匹配生成中')).toBeVisible()
  expect(screen.getByText('成员流动后，社区互助为何持续减少？')).toBeVisible()
  expect(screen.getByText('2 个理论')).toBeVisible()

  fireEvent.click(screen.getByRole('button', { name: /打开研究操作/ }))
  expect(screen.getByRole('menuitem', { name: '继续研究' })).toHaveAttribute(
    'href',
    '/research/95306bf9-194d-4677-be2d-eef4f6aa86d1/match',
  )

  fireEvent.click(screen.getByRole('menuitem', { name: '删除研究' }))
  expect(deleted).toBe(false)
  expect(screen.getByRole('dialog', { name: '永久删除这项研究？' })).toBeVisible()
  expect(screen.getByText('删除后，任务及其派生内容无法恢复。')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: '确认永久删除' }))

  await waitFor(() => expect(deleted).toBe(true))
  expect(await screen.findByRole('heading', { name: '还没有研究任务' })).toBeVisible()
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

  const errorState = await screen.findByRole('alert')
  expect(within(errorState).getByRole('heading', { name: '暂时无法读取研究任务' })).toBeVisible()
  fireEvent.click(within(errorState).getByRole('button', { name: '重试' }))

  expect(await screen.findByRole('heading', { name: '还没有研究任务' })).toBeVisible()
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

it('moves focus into the delete dialog and restores it when dismissed with Escape', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
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
      current_match_run_id: 'b32448bd-18ef-44a8-89fc-e24d735edfb6',
      current_framework_id: null,
      created_at: '2026-08-07T00:00:00Z',
      updated_at: '2026-08-07T01:00:00Z',
    }],
    next_cursor: null,
  }), { status: 200, headers: { 'Content-Type': 'application/json' } })))
  renderPage()

  await screen.findByRole('row', { name: /成员流动后，社区互助为何持续减少/ })
  const trigger = screen.getByRole('button', { name: /打开研究操作/ })
  fireEvent.click(trigger)
  fireEvent.click(screen.getByRole('menuitem', { name: '删除研究' }))

  const dialog = await screen.findByRole('dialog', { name: '永久删除这项研究？' })
  const cancel = within(dialog).getByRole('button', { name: '取消' })
  expect(cancel).toHaveFocus()
  fireEvent.keyDown(dialog, { key: 'Escape' })

  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(trigger).toHaveFocus()
})
