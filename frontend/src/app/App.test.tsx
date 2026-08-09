import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AppRoutes } from './App'
import { AccountProvider } from '../modules/account'

const cytoscapeMock = vi.hoisted(() => vi.fn(() => ({
  destroy: vi.fn(),
  on: vi.fn(),
})))

vi.mock('cytoscape', () => ({ default: cytoscapeMock }))

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

function knowledgeSummary() {
  return {
    category: '概念',
    category_id: 'C001',
    content_version: 1,
    dimension: '本体论',
    dimension_id: 'D1',
    directory_path: [
      { node_id: 'D1', node_type: 'dimension', title: '本体论' },
      { node_id: 'C001', node_type: 'category', title: '概念' },
    ],
    eligibility: {
      browse_eligible: true,
      match_eligible: false,
      rag_eligible: false,
      review_record_ids: [],
      training_candidate_eligible: false,
    },
    knowledge_id: 'D1:C001',
    review_status: 'pending',
    title: '概念',
  }
}

function knowledgePage() {
  return {
    entries: [knowledgeSummary()],
    knowledge_release_id: 'release-a',
    next_cursor: null,
    stable_order: ['D1:C001'],
  }
}

function knowledgeDetail() {
  return {
    ...knowledgeSummary(),
    aliases: [],
    content: '一段真实条目正文。',
    knowledge_release_id: 'release-a',
    relations: [],
    sources: [],
    theory_profile: null,
  }
}

function knowledgeDetailWithRelation() {
  return {
    ...knowledgeDetail(),
    relations: [
      {
        content_version: 1,
        description: '真实已审核关系。',
        direction: 'directed',
        evidence_grade: 'A',
        evidence_source_ids: [],
        relation_id: 'relation-1',
        relation_type: '概念关联',
        review_status: 'reviewed',
        source_knowledge_id: 'D1:C001',
        target_knowledge_id: 'D1:C002',
      },
    ],
  }
}

function knowledgeDetailWithTheoryProfile() {
  return {
    ...knowledgeDetail(),
    theory_profile: {
      analysis_levels: [],
      applicable_phenomena: [],
      competing_or_complementary_theory_ids: [],
      content_version: 1,
      core_propositions: [],
      exclusion_signals: [],
      match_eligible: true,
      observable_evidence: [],
      prerequisites: [],
      related_knowledge_ids: ['D1:C001'],
      review_status: 'reviewed',
      source_ids: [],
      theory_id: 'theory-social-capital',
      title: '社会资本理论',
    },
  }
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function requestUrl(input: RequestInfo | URL) {
  if (typeof input === 'string') return new URL(input)
  if (input instanceof URL) return input
  return new URL(input.url)
}

describe('App routes', () => {
  it('provides distinct desktop and mobile navigation surfaces', async () => {
    renderRoute('/knowledge')

    expect(
      await screen.findByRole('navigation', { name: '桌面主导航' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('navigation', { name: '移动主导航' }),
    ).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: '图' })).toHaveLength(2)
    expect(screen.getAllByRole('link', { name: '图' })[0]).toHaveAttribute(
      'href',
      '/knowledge/graph',
    )
  })

  it('renders the graph workspace from its independent route', async () => {
    renderRoute('/knowledge/graph?knowledge_release_id=release-a')

    expect(await screen.findByRole('heading', { name: '知识图谱' })).toBeVisible()
    expect(screen.getByRole('region', { name: '全屏知识图谱工作台' })).toBeVisible()
  })

  it.each([
    ['/', '从社会现象找到可比较理论，再形成研究框架。'],
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

  it('returns home after logging out from my research', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = input as Request
      if (request.method === 'GET' && request.url.endsWith('/api/session')) {
        return new Response(JSON.stringify({
          session_id: '25b191bb-2d85-4a88-8863-2cabf506a7a8',
          status: 'active',
          version: 1,
          allowed_actions: ['logout'],
          user: {
            user_id: '95306bf9-194d-4677-be2d-eef4f6aa86d1',
            email: 'researcher@example.com',
            display_name: null,
          },
          expires_at: '2026-08-14T00:00:00Z',
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      if (request.method === 'GET') {
        return new Response(JSON.stringify({ items: [], next_cursor: null }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      return new Response(JSON.stringify({
        status: 'logged_out',
        version: 1,
        allowed_actions: [],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <MemoryRouter initialEntries={['/my']} useTransitions={false}>
        <QueryClientProvider client={queryClient}>
          <AccountProvider>
            <AppRoutes />
            <RouteLocation />
          </AccountProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: '退出' }))

    expect(await screen.findByRole('link', { name: '浏览知识库' })).toBeVisible()
    expect(screen.getByTestId('route-location')).toHaveTextContent('/')
  })

  it('resolves a first knowledge visit to one fixed release before loading its directory', async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const request = requestUrl(input)
      return request.pathname === '/api/knowledge/releases/current'
        ? json({
            content_hash: 'sha256:release-a',
            knowledge_release_id: 'release-a',
            level: 'preview',
          })
        : json(knowledgePage())
    })
    vi.stubGlobal('fetch', fetch)

    renderRoute('/knowledge')

    expect(await screen.findByRole('heading', { name: '条目' })).toBeVisible()
    await waitFor(() => {
      expect(screen.getByTestId('route-location')).toHaveTextContent(
        '/knowledge?knowledge_release_id=release-a',
      )
    })
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('keeps the selected release and filters while opening an independent detail route', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json(knowledgePage())))
    renderRoute('/knowledge?knowledge_release_id=release-a&query=%E6%A6%82%E5%BF%B5&dimension_id=D1&category_id=C001')

    const results = (await screen.findByRole('heading', { name: '条目' })).closest('section')
    if (!results) throw new Error('知识结果区域缺失')
    fireEvent.click(await within(results).findByRole('button', { name: /^概念/ }))

    expect(screen.getByTestId('route-location')).toHaveTextContent(
      '/knowledge/D1%3AC001?knowledge_release_id=release-a&query=%E6%A6%82%E5%BF%B5&dimension_id=D1&category_id=C001',
    )
  })

  it('opens a release-pinned detail and returns to the supplied research task', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json(knowledgeDetail())))
    renderRoute(
      '/knowledge/D1%3AC001?knowledge_release_id=release-a&return_to=%2Fresearch%2Ftask-1%2Fmatch',
      { status: 'authenticated' },
    )

    expect(await screen.findByText('一段真实条目正文。')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: '返回研究任务' }))

    expect(await screen.findByRole('heading', { name: '匹配理论' })).toBeVisible()
    expect(screen.getByTestId('route-location')).toHaveTextContent('/research/task-1/match')
  })

  it('returns from a detail to a safe graph workspace context', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json(knowledgeDetail())))
    const graphContext = '/knowledge/graph?knowledge_release_id=release-a&query=%E7%A4%BE%E4%BC%9A&center=D1%3AC001&pending=1'
    renderRoute(
      `/knowledge/D1%3AC001?knowledge_release_id=release-a&return_to=${encodeURIComponent(graphContext)}`,
    )

    expect(await screen.findByText('一段真实条目正文。')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: '返回知识图谱' }))

    expect(screen.getByTestId('route-location')).toHaveTextContent(graphContext)
  })

  it('exposes the structural graph on the knowledge page without eagerly requesting edges', async () => {
    const fetch = vi.fn(async () => json(knowledgePage()))
    vi.stubGlobal('fetch', fetch)
    renderRoute('/knowledge?knowledge_release_id=release-a')

    expect(await screen.findByRole('button', { name: '打开知识图谱' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: '知识关系图' })).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('keeps reviewed relation details factual without a second graph request', async () => {
    const fetch = vi.fn(async () => json(knowledgeDetailWithRelation()))
    vi.stubGlobal('fetch', fetch)
    renderRoute('/knowledge/D1%3AC001?knowledge_release_id=release-a')

    expect(await screen.findByText('真实已审核关系。')).toBeVisible()
    expect(screen.getByRole('button', { name: '返回知识库' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: '知识关系图' })).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('keeps only the theory ID in the URL when starting research from knowledge', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = requestUrl(input)
      if (request.pathname === '/api/knowledge/entries/D1%3AC001') {
        return json(knowledgeDetailWithTheoryProfile())
      }
      if (request.pathname === '/api/phenomenon-examples') return json({ items: [] })
      return json(knowledgeDetailWithTheoryProfile())
    }))
    renderRoute('/knowledge/D1%3AC001?knowledge_release_id=release-a', { status: 'authenticated' })

    fireEvent.click(await screen.findByRole('button', { name: '以此理论开始研究' }))

    expect(await screen.findByText('起始线索：社会资本理论')).toBeVisible()
    expect(screen.getByTestId('route-location')).toHaveTextContent(
      /^\/research\/new\?seed_theory_id=theory-social-capital$/,
    )
  })

  it('resolves a deep knowledge entry to one fixed release before reading its detail', async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const request = requestUrl(input)
      return request.pathname === '/api/knowledge/releases/current'
        ? json({
            content_hash: 'sha256:release-a',
            knowledge_release_id: 'release-a',
            level: 'preview',
          })
        : json(knowledgeDetail())
    })
    vi.stubGlobal('fetch', fetch)

    renderRoute('/knowledge/D1%3AC001')

    expect(await screen.findByText('一段真实条目正文。')).toBeVisible()
    await waitFor(() => {
      expect(screen.getByTestId('route-location')).toHaveTextContent(
        '/knowledge/D1%3AC001?knowledge_release_id=release-a',
      )
    })
    expect(fetch).toHaveBeenCalledTimes(2)
  })
})
