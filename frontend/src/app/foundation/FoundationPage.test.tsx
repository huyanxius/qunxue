import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useParams } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { FoundationPage } from './FoundationPage'

function TaskRouteProbe() {
  const { task_id = '' } = useParams<{ task_id: string }>()
  return <p>task route: {task_id}</p>
}

function renderFoundationPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  return render(
    <MemoryRouter initialEntries={['/']}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/" element={<FoundationPage />} />
          <Route path="/research/:task_id" element={<TaskRouteProbe />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('FoundationPage', () => {
  it('submits a valid phenomenon and navigates to the task page', async () => {
    const fetchMock = vi.fn()
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            status: 'ok',
            service: '群学致知 API',
            runtime_mode: 'inline_demo',
            persistence: 'sqlite',
            contract_version: '2026-07-foundation',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            task_id: '9c2fb49f-cfd0-41f1-9556-118371c9de65',
            phenomenon: 'Team jokes disappear after a leadership change.',
            research_intent: 'Study shifts in safety signals.',
            context: 'Observed across two weekly rituals.',
            source: 'user_input',
            created_at: '2026-08-05T00:00:00Z',
            updated_at: '2026-08-05T00:00:00Z',
          }),
          { status: 201, headers: { 'Content-Type': 'application/json' } },
        ),
      )
    vi.stubGlobal('fetch', fetchMock)

    renderFoundationPage()

    fireEvent.change(screen.getByLabelText('研究现象 *'), {
      target: { value: 'Team jokes disappear after a leadership change.' },
    })
    fireEvent.change(screen.getByLabelText('研究意图'), {
      target: { value: 'Study shifts in safety signals.' },
    })
    fireEvent.change(screen.getByLabelText('补充背景'), {
      target: { value: 'Observed across two weekly rituals.' },
    })
    fireEvent.click(screen.getByRole('button', { name: '创建研究任务' }))

    expect(
      await screen.findByText('task route: 9c2fb49f-cfd0-41f1-9556-118371c9de65'),
    ).toBeInTheDocument()
  })

  it('blocks submission when phenomenon is blank', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          status: 'ok',
          service: '群学致知 API',
          runtime_mode: 'inline_demo',
          persistence: 'sqlite',
          contract_version: '2026-07-foundation',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    renderFoundationPage()

    fireEvent.click(screen.getByRole('button', { name: '创建研究任务' }))

    expect(
      await screen.findByText('请先描述你想研究的社会现象。'),
    ).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('shows a retry message after a server failure and keeps user input', async () => {
    const fetchMock = vi.fn()
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            status: 'ok',
            service: '群学致知 API',
            runtime_mode: 'inline_demo',
            persistence: 'sqlite',
            contract_version: '2026-07-foundation',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            error: {
              code: 'internal_server_error',
              message: 'unexpected service failure',
              trace_id: 'trace-123',
            },
          }),
          { status: 500, headers: { 'Content-Type': 'application/json' } },
        ),
      )
    vi.stubGlobal('fetch', fetchMock)

    renderFoundationPage()

    fireEvent.change(screen.getByLabelText('研究现象 *'), {
      target: { value: 'A fragile routine breaks after the server failure.' },
    })
    fireEvent.click(screen.getByRole('button', { name: '创建研究任务' }))

    expect(
      await screen.findByText('服务暂时无法保存这条研究任务，请稍后重试。'),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('研究现象 *')).toHaveValue(
      'A fragile routine breaks after the server failure.',
    )
  })
})
