import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { FoundationPage } from './FoundationPage'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('FoundationPage', () => {
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
