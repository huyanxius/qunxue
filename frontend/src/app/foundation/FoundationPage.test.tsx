import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { FoundationPage } from './FoundationPage'

const cytoscapeMock = vi.hoisted(() => vi.fn(() => ({
  destroy: vi.fn(),
  elements: vi.fn(() => ({})),
  fit: vi.fn(),
  on: vi.fn(),
})))

vi.mock('cytoscape', () => ({ default: cytoscapeMock }))

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <FoundationPage />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('FoundationPage', () => {
  it('leads with user value and an explicitly marked research demo', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ error: { code: 'offline' } }, 503)))

    const { container } = renderPage()

    expect(
      screen.getByRole('heading', {
        name: /从真实困惑.*找到可研究的问题。/,
      }),
    ).toBeVisible()
    expect(screen.getByRole('link', { name: '体验研究流程' })).toHaveAttribute(
      'href',
      '#research-demo',
    )
    expect(container.querySelector('header.public-header')).toBeInTheDocument()
    expect(container.querySelector('.app-frame')).not.toBeInTheDocument()
    expect(screen.getByText('可交互演示')).toBeVisible()
    expect(screen.queryByText('运行模式')).not.toBeInTheDocument()
    expect(screen.queryByText('契约版本')).not.toBeInTheDocument()
    expect(screen.queryByText('知识发布')).not.toBeInTheDocument()
    expect(screen.getAllByRole('tabpanel', { hidden: true })).toHaveLength(3)

    fireEvent.click(screen.getByRole('tab', { name: /比较候选/ }))
    expect(screen.getAllByText('解释重点')).toHaveLength(2)
    expect(screen.getByText(/选择仍由你完成/)).toBeVisible()
  })

  it('renders real knowledge entries without exposing release identifiers', async () => {
    Object.defineProperty(window, 'scrollY', { configurable: true, value: 0 })
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = input as Request
      const url = new URL(request.url)
      if (url.pathname === '/api/knowledge/releases/current') {
        return json({
          knowledge_release_id: 'release-private-hash',
          level: 'preview',
          content_hash: 'sha256:release-private-hash',
        })
      }
      if (url.pathname === '/api/knowledge/entries') {
        return json({
          knowledge_release_id: 'release-private-hash',
          entries: [
            {
              knowledge_id: 'D1:C001',
              content_version: 1,
              title: '历史唯物主义',
              category_id: 'C001',
              category: '古典社会学奠基',
              dimension_id: 'D1',
              dimension: '本体论',
              directory_path: [
                { node_id: 'D1', node_type: 'dimension', title: '本体论' },
                { node_id: 'C001', node_type: 'category', title: '古典社会学奠基' },
              ],
              review_status: 'pending',
              eligibility: {
                browse_eligible: true,
                rag_eligible: false,
                training_candidate_eligible: false,
                match_eligible: false,
                review_record_ids: [],
              },
            },
          ],
          stable_order: ['D1:C001'],
          next_cursor: null,
        })
      }
      if (url.pathname.startsWith('/api/knowledge/entries/')) {
        return json({
          aliases: [],
          category: '古典社会学奠基',
          category_id: 'C001',
          content: '# 历史唯物主义\n社会存在与社会意识之间存在可研究的关系。',
          content_version: 1,
          dimension: '本体论',
          dimension_id: 'D1',
          directory_path: [
            { node_id: 'D1', node_type: 'dimension', title: '本体论' },
            { node_id: 'C001', node_type: 'category', title: '古典社会学奠基' },
          ],
          eligibility: {
            browse_eligible: true,
            rag_eligible: false,
            training_candidate_eligible: false,
            match_eligible: false,
            review_record_ids: [],
          },
          knowledge_id: 'D1:C001',
          knowledge_release_id: 'release-private-hash',
          relations: [],
          review_status: 'pending',
          sources: [],
          theory_profile: null,
          title: '历史唯物主义',
        })
      }
      if (url.pathname === '/api/knowledge/relations') {
        return json({
          knowledge_release_id: 'release-private-hash',
          relations: [],
          stable_order: [],
          total_count: 0,
          next_cursor: null,
        })
      }
      return json({ error: { code: 'not_found' } }, 404)
    }))

    renderPage()

    expect((await screen.findAllByText('历史唯物主义'))[0]).toBeVisible()
    expect(await screen.findByText('待核验')).toBeVisible()
    const ticker = screen.getByRole('region', { name: /知识索引流/ })
    const tickerTrack = ticker.querySelector<HTMLElement>('.knowledge-ticker__track')
    expect(tickerTrack).not.toBeNull()
    Object.defineProperty(tickerTrack, 'scrollWidth', { configurable: true, value: 1200 })

    Object.defineProperty(window, 'scrollY', { configurable: true, value: 100 })
    fireEvent.scroll(window)
    expect(tickerTrack).toHaveStyle({ transform: 'translate3d(-320px, 0, 0)' })

    Object.defineProperty(window, 'scrollY', { configurable: true, value: 50 })
    fireEvent.scroll(window)
    expect(tickerTrack).toHaveStyle({ transform: 'translate3d(-160px, 0, 0)' })
    expect(screen.queryByText('release-private-hash')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '继续浏览知识库' })).toHaveAttribute(
      'href',
      '/knowledge',
    )
    expect(await screen.findByRole('region', { name: '节点式知识图谱' })).toBeInTheDocument()
  })

  it('keeps a recovery path when live knowledge cannot be loaded', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ error: { code: 'offline' } }, 503)))

    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent('暂时无法读取知识内容')
    expect(screen.getByRole('button', { name: '重新加载知识' })).toBeVisible()
    expect(screen.getByRole('link', { name: '直接进入知识库' })).toHaveAttribute(
      'href',
      '/knowledge',
    )
  })
})
