import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { FoundationPage } from './FoundationPage'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('FoundationPage', () => {
  it('shows the product boundary and all four stable content provenance marks', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            status: 'ok',
            service: '群学致知 API',
            runtime_mode: 'mock',
            persistence: 'sqlite',
            contract_version: '2026-08-m1',
            capability: 'mock',
            knowledge_release_id: 'knowledge-demo-v1',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    const { container } = render(
      <MemoryRouter>
        <QueryClientProvider client={queryClient}>
          <FoundationPage />
        </QueryClientProvider>
      </MemoryRouter>,
    )

    expect(
      screen.getByRole('heading', {
        name: '从社会现象找到可比较理论，再形成研究框架。',
      }),
    ).toBeVisible()
    expect(screen.getByText('产品输出止于研究框架')).toBeVisible()
    expect(await screen.findByText('演示数据')).toBeVisible()

    expect(container.querySelector('.content-mark--verified')).toHaveTextContent(
      '已审核知识',
    )
    expect(container.querySelector('.content-mark--analysis')).toHaveTextContent(
      '系统分析',
    )
    expect(container.querySelector('.content-mark--external')).toHaveTextContent(
      '库外线索',
    )
    expect(container.querySelector('.content-mark--user')).toHaveTextContent(
      '用户内容',
    )
  })

  it('keeps both peer entrances navigable when the health request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(null, { status: 503 })),
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

    expect(await screen.findByText('接口暂不可用')).toBeVisible()
    expect(screen.getByRole('link', { name: '开始一项研究' })).toHaveAttribute(
      'href',
      '/research/new',
    )
    expect(screen.getByRole('link', { name: '浏览知识库' })).toHaveAttribute(
      'href',
      '/knowledge',
    )
  })

  it('shows the real backend contract after the health request succeeds', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            status: 'ok',
            service: '群学致知 API',
            runtime_mode: 'mock',
            persistence: 'sqlite',
            contract_version: '2026-07-foundation',
            capability: 'mock',
            knowledge_release_id: 'knowledge-demo-v1',
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

    expect(await screen.findByText('系统可用')).toBeInTheDocument()
    expect(screen.getByText('2026-07-foundation')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '开始一项研究' })).toHaveAttribute(
      'href',
      '/research/new',
    )
    expect(
      screen.getByRole('link', { name: '浏览知识库' }),
    ).toHaveAttribute('href', '/knowledge')
  })
})
