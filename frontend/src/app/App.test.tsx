import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AppRoutes } from './App'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function renderRoute(path: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={queryClient}>
        <AppRoutes />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('App routes', () => {
  it('renders the demo knowledge explorer from a direct /knowledge entry', async () => {
    renderRoute('/knowledge')

    expect(
      await screen.findByRole('heading', { name: '可视化知识库' }),
    ).toBeVisible()
    expect(screen.getByRole('note')).toHaveTextContent(
      '不代表正式知识库、学术来源或审核结论',
    )

    fireEvent.click(
      await screen.findByRole('button', { name: /情境概念（演示）/ }),
    )

    expect(
      await screen.findByText('演示来源记录 A'),
    ).toBeVisible()
    expect(screen.getByRole('heading', { name: '显式关系' })).toBeVisible()
  })

  it('navigates from the knowledge explorer back to the home page', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(null, { status: 503 })),
    )
    renderRoute('/knowledge')

    fireEvent.click(screen.getByRole('link', { name: '返回首页' }))

    expect(
      await screen.findByRole('link', { name: '进入可视化知识库' }),
    ).toHaveAttribute('href', '/knowledge')
  })
})
