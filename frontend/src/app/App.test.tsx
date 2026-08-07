import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AppRoutes } from './App'
import { AccountProvider } from '../modules/account'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function renderRoute(
  path: string,
  sessionState: { status: 'authenticated' | 'anonymous' | 'expired' | 'loading' } = {
    status: 'anonymous',
  },
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={queryClient}>
        <AppRoutes sessionState={sessionState} />
        <RouteLocation />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

function RouteLocation() {
  const location = useLocation()
  return <div data-testid="route-location">{`${location.pathname}${location.search}${location.hash}`}</div>
}

describe('App routes', () => {
  it.each([
    ['/', '把一个模糊的现象，留成可以追问的研究起点。'],
    ['/knowledge', '可视化知识库'],
    ['/knowledge/knowledge-field-theory', '知识条目'],
    ['/research/new', '新建研究任务'],
    ['/research/task-1/phenomenon', '确认现象'],
    ['/research/task-1/match', '匹配理论'],
    ['/research/task-1/framework', '研究框架'],
    ['/my', '我的研究'],
  ])('renders %s from a direct entry for an authenticated visitor', async (path, title) => {
    renderRoute(path, { status: 'authenticated' })

    expect(
      await screen.findByRole('heading', { name: title }),
    ).toBeVisible()
  })

  it.each([
    ['/login', '登录'],
    ['/register', '注册'],
  ])('renders the public account route %s for an anonymous visitor', async (path, title) => {
    renderRoute(path)

    expect(await screen.findByRole('heading', { name: title })).toBeVisible()
  })

  it.each([
    '/research/new?source=home',
    '/research/task-1/phenomenon',
    '/research/task-1/match',
    '/research/task-1/framework',
    '/my',
  ])('sends anonymous visitors to login while preserving %s', async (path) => {
    renderRoute(path)

    expect(await screen.findByRole('heading', { name: '登录' })).toBeVisible()
    expect(screen.getByTestId('route-location')).toHaveTextContent(
      `/login?redirect=${encodeURIComponent(path)}`,
    )
  })

  it('keeps an authenticated visitor on a protected route', async () => {
    renderRoute('/research/task-1/phenomenon', { status: 'authenticated' })

    expect(
      await screen.findByRole('heading', { name: '确认现象' }),
    ).toBeVisible()
    expect(screen.queryByRole('heading', { name: '登录' })).not.toBeInTheDocument()
  })

  it('waits for the session boundary before deciding on a protected route', async () => {
    renderRoute('/my', { status: 'loading' })

    expect(await screen.findByRole('status')).toHaveTextContent('正在确认登录状态')
    expect(screen.queryByRole('heading', { name: '登录' })).not.toBeInTheDocument()
  })

  it('uses a same-origin redirect after login', async () => {
    renderRoute('/login?redirect=%2Fresearch%2Ftask-1%2Fframework')

    expect(await screen.findByRole('button', { name: '登录并继续' })).toBeVisible()
    expect(screen.getByRole('link', { name: '创建账号' })).toHaveAttribute(
      'href',
      `/register?redirect=${encodeURIComponent('/research/task-1/framework')}`,
    )
  })

  it('rejects an external login redirect', async () => {
    renderRoute('/login?redirect=https%3A%2F%2Fevil.example%2Ftakeover')

    expect(await screen.findByRole('link', { name: '创建账号' })).toHaveAttribute(
      'href',
      `/register?redirect=${encodeURIComponent('/')}`,
    )
  })

  it('rejects a malformed login redirect without crashing the page', async () => {
    renderRoute('/login?redirect=%2F%2F%5B')

    expect(await screen.findByRole('heading', { name: '登录' })).toBeVisible()
    expect(screen.getByRole('link', { name: '创建账号' })).toHaveAttribute(
      'href',
      `/register?redirect=${encodeURIComponent('/')}`,
    )
  })

  it('preserves a protected route hash through login', async () => {
    const destination = '/research/task-1/phenomenon?source=home#evidence'
    renderRoute(destination)

    expect(await screen.findByRole('heading', { name: '登录' })).toBeVisible()
    expect(screen.getByTestId('route-location')).toHaveTextContent(
      `/login?redirect=${encodeURIComponent(destination)}`,
    )
    expect(screen.getByRole('link', { name: '创建账号' })).toHaveAttribute(
      'href',
      `/register?redirect=${encodeURIComponent(destination)}`,
    )
  })

  it('returns to the protected deep link after a real login response', async () => {
    const destination = '/research/task-1/framework?from=my#methods'
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = input as Request
      if (request.method === 'GET') {
        return new Response(
          JSON.stringify({ error: { code: 'unauthenticated', message: '请先登录。', trace_id: 'trace-1' } }),
          { status: 401, headers: { 'Content-Type': 'application/json' } },
        )
      }
      return new Response(JSON.stringify({
        session_id: '25b191bb-2d85-4a88-8863-2cabf506a7a8',
        status: 'active',
        version: 1,
        allowed_actions: ['logout'],
        user: { user_id: '95306bf9-194d-4677-be2d-eef4f6aa86d1', email: 'researcher@example.com', display_name: null },
        expires_at: '2026-08-14T00:00:00Z',
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <MemoryRouter initialEntries={[`/login?redirect=${encodeURIComponent(destination)}`]}>
        <QueryClientProvider client={queryClient}>
          <AccountProvider>
            <AppRoutes />
            <RouteLocation />
          </AccountProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    )

    fireEvent.change(await screen.findByLabelText('邮箱'), { target: { value: 'researcher@example.com' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'research-passphrase' } })
    fireEvent.click(screen.getByRole('button', { name: '登录并继续' }))

    expect(await screen.findByRole('heading', { name: '研究框架' })).toBeVisible()
    expect(screen.getByTestId('route-location')).toHaveTextContent(destination)
  })

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
