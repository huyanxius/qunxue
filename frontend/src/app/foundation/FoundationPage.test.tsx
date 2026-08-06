import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { FoundationPage } from './FoundationPage'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('FoundationPage', () => {
  it('opens a newly created research task at its protected phenomenon route', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'test-request-key' })
    let requestCount = 0
    const fetchMock = vi.fn(async () => {
      requestCount += 1
      if (requestCount === 1) {
        return new Response(
          JSON.stringify({
            status: 'ok',
            service: '群学致知 API',
            runtime_mode: 'inline_demo',
            persistence: 'sqlite',
            contract_version: '2026-07-foundation',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        )
      }
      return new Response(
        JSON.stringify({
          task_id: 'task-1',
          entry_type: 'direct_input',
          status: 'draft',
          version: 1,
          allowed_actions: ['submit_phenomenon'],
          created_at: '2026-07-28T00:00:00Z',
          updated_at: '2026-07-28T00:00:00Z',
        }),
        { status: 201, headers: { 'Content-Type': 'application/json' } },
      )
    })
    vi.stubGlobal(
      'fetch',
      fetchMock,
    )
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <MemoryRouter>
        <QueryClientProvider client={queryClient}>
          <FoundationPage />
          <RouteLocation />
        </QueryClientProvider>
      </MemoryRouter>,
    )

    await screen.findByText('接口已接通')
    fireEvent.click(screen.getByRole('button', { name: '建立空白研究任务' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2)
      expect(screen.getByTestId('route-location')).toHaveTextContent(
        '/research/task-1/phenomenon',
      )
    })
  })

  it('shows the real backend contract after the health request succeeds', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
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
      ),
    )
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <MemoryRouter>
        <QueryClientProvider client={queryClient}>
          <FoundationPage />
        </QueryClientProvider>
      </MemoryRouter>,
    )

    expect(await screen.findByText('接口已接通')).toBeInTheDocument()
    expect(screen.getByText('2026-07-foundation')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '建立空白研究任务' })).toBeEnabled()
    expect(
      screen.getByRole('link', { name: '进入可视化知识库' }),
    ).toHaveAttribute('href', '/knowledge')
  })
})

function RouteLocation() {
  const location = useLocation()
  return <div data-testid="route-location">{location.pathname}</div>
}
