import { useState } from 'react'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { KnowledgeEntryPage, KnowledgeExplorerPage } from './index'
import type { KnowledgeUrlState } from './urlState'

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function urlFor(input: RequestInfo | URL) {
  if (typeof input === 'string') return new URL(input)
  if (input instanceof URL) return input
  return new URL(input.url)
}

function summary() {
  return {
    category: '1. 古典社会学奠基',
    category_id: 'D1:I. 古典社会学奠基/1. 古典社会学奠基',
    content_version: 1,
    dimension: '本体论',
    dimension_id: 'D1',
    directory_path: [
      { node_id: 'D1', node_type: 'dimension', title: '本体论' },
      { node_id: 'D1:I. 古典社会学奠基', node_type: 'category', title: 'I. 古典社会学奠基' },
      {
        node_id: 'D1:I. 古典社会学奠基/1. 古典社会学奠基',
        node_type: 'category',
        title: '1. 古典社会学奠基',
      },
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

function page(entries = [summary()]) {
  return {
    entries,
    knowledge_release_id: 'release-a',
    next_cursor: null,
    stable_order: entries.map((entry) => entry.knowledge_id),
    total_count: entries.length,
  }
}

function directory() {
  return {
    knowledge_release_id: 'release-a',
    nodes: [
      { entry_count: 1, node_id: 'D1', node_type: 'dimension', parent_node_id: null, title: '本体论' },
      { entry_count: 1, node_id: 'D1:I. 古典社会学奠基', node_type: 'category', parent_node_id: 'D1', title: 'I. 古典社会学奠基' },
      { entry_count: 1, node_id: 'D1:I. 古典社会学奠基/1. 古典社会学奠基', node_type: 'category', parent_node_id: 'D1:I. 古典社会学奠基', title: '1. 古典社会学奠基' },
      ...['D2', 'D3', 'D4', 'D5', 'D6', 'D7'].map((nodeId, index) => ({
        entry_count: 0,
        node_id: nodeId,
        node_type: 'dimension',
        parent_node_id: null,
        title: ['实践论', '方法论', '价值论', '认识论', '学派传统', '学科史'][index],
      })),
    ],
  }
}

function knowledgeFetch(input: RequestInfo | URL) {
  const request = urlFor(input)
  return request.pathname === '/api/knowledge/directory'
    ? json(directory())
    : json(page())
}

function detail() {
  return {
    ...summary(),
    aliases: ['概念别名'],
    content: '## 正文标题\n\n一段真实条目正文。\n\n> **观点—文献依据（1条）**\n>\n> P1 | [A] 一段真实条目正文。\n>\n> **文献：** 示例文献\n>\n> **支持范围：** 直接支持该观点。\n\n## T4 当代发展\n\n一段当代发展正文。',
    content_version: 2,
    knowledge_release_id: 'release-a',
    relations: [
      {
        content_version: 1,
        description: '经审核的概念关系。',
        direction: 'directed',
        evidence_grade: 'A',
        evidence_source_ids: ['source-1'],
        relation_id: 'relation-reviewed',
        relation_type: '概念关联',
        review_status: 'reviewed',
        source_knowledge_id: 'D1:C001',
        target_knowledge_id: 'D1:C002',
      },
    ],
    sources: [
      {
        authors_or_institution: ['知识库导入'],
        locator: 'knowledge/D1.md#c001',
        publication: null,
        source_id: 'source-1',
        source_type: 'repository_markdown',
        title: '知识库原始 Markdown',
        url: null,
        use_boundary: '待学术核验',
        verification_status: 'pending',
        year: null,
      },
    ],
    theory_profile: {
      analysis_levels: ['中观'],
      applicable_phenomena: ['社会行动'],
      competing_or_complementary_theory_ids: [],
      content_version: 1,
      core_propositions: ['概念命题'],
      exclusion_signals: [],
      match_eligible: false,
      observable_evidence: [],
      prerequisites: [],
      related_knowledge_ids: ['D1:C001'],
      review_status: 'pending',
      source_ids: ['source-1'],
      theory_id: 'theory-1',
      title: '概念理论',
    },
  }
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('knowledge pages', () => {
  it('opens as a persistent knowledge tree with a focused dimension overview', async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) => knowledgeFetch(input))
    vi.stubGlobal('fetch', fetch)

    render(
      <KnowledgeExplorerPage
        state={{ releaseId: 'release-a' }}
        onOpenEntry={vi.fn()}
        onReleaseResolved={vi.fn()}
        onStateChange={vi.fn()}
      />,
    )

    const dimensionButton = await screen.findByRole('button', { name: '浏览 本体论 目录' })
    expect(dimensionButton).toBeVisible()
    expect(within(dimensionButton).getByText('D1')).toBeVisible()
    expect(await screen.findByRole('heading', { name: '本体论' })).toBeVisible()
    expect(screen.getByRole('navigation', { name: '知识目录' })).toBeVisible()
    expect(screen.getByRole('button', { name: '收起 本体论' })).toBeVisible()
    expect(screen.getByRole('button', { name: '进入 I. 古典社会学奠基' })).toBeVisible()
    expect(screen.queryByRole('button', { name: /打开 概念/ })).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch.mock.calls.map(([input]) => urlFor(input).pathname)).toEqual([
      '/api/knowledge/directory',
    ])
  })

  it('keeps the graph shortcut named when its visible label is hidden on narrow screens', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => knowledgeFetch(input)))

    render(
      <KnowledgeExplorerPage
        state={{ releaseId: 'release-a' }}
        onOpenEntry={vi.fn()}
        onOpenGraph={vi.fn()}
        onReleaseResolved={vi.fn()}
        onStateChange={vi.fn()}
      />,
    )

    expect(await screen.findByRole('button', { name: '打开知识图谱' })).toBeVisible()
    expect(screen.getByRole('button', { name: '打开知识图谱' })).toHaveAttribute(
      'aria-label',
      '打开知识图谱',
    )
  })

  it('shows loaded and total results while keeping the next page explicit', async () => {
    const entries = Array.from({ length: 20 }, (_, index) => ({
      ...summary(), knowledge_id: `D1:C${index + 1}`, title: `条目 ${index + 1}`,
    }))
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = urlFor(input)
      return request.pathname === '/api/knowledge/directory'
        ? json(directory())
        : json({ ...page(entries), next_cursor: 'cursor-20', total_count: 101 })
    }))

    render(
      <KnowledgeExplorerPage
        state={{ releaseId: 'release-a', query: '条目' }}
        onOpenEntry={vi.fn()}
        onReleaseResolved={vi.fn()}
        onStateChange={vi.fn()}
      />,
    )

    expect(await screen.findByText('已显示 20 条，共 101 条')).toBeVisible()
    expect(screen.getByRole('button', { name: '继续加载 81 条未显示' })).toBeVisible()
  })

  it('keeps the knowledge tree visible while a selected category shows results', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => knowledgeFetch(input)))

    render(
      <KnowledgeExplorerPage
        state={{
          releaseId: 'release-a',
          dimensionId: 'D1',
          categoryId: 'D1:I. 古典社会学奠基/1. 古典社会学奠基',
        }}
        onOpenEntry={vi.fn()}
        onReleaseResolved={vi.fn()}
        onStateChange={vi.fn()}
      />,
    )

    expect(await screen.findByRole('heading', { name: '条目' })).toBeVisible()
    expect(screen.getByRole('button', { name: '返回 本体论 目录' })).toBeVisible()
    expect(screen.getByRole('navigation', { name: '知识目录' })).toBeVisible()
    expect(screen.getByRole('button', { name: '浏览 本体论 目录' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  it('drills through parent categories before applying an exact leaf filter', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => knowledgeFetch(input)))
    const onStateChange = vi.fn()

    render(
      <KnowledgeExplorerPage
        state={{ releaseId: 'release-a', dimensionId: 'D1' }}
        onOpenEntry={vi.fn()}
        onReleaseResolved={vi.fn()}
        onStateChange={onStateChange}
      />,
    )

    fireEvent.click(await screen.findByRole('button', { name: '进入 I. 古典社会学奠基' }))
    expect(onStateChange).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: '浏览 1. 古典社会学奠基' }))
    expect(onStateChange).toHaveBeenCalledWith(expect.objectContaining({
      dimensionId: 'D1',
      categoryId: 'D1:I. 古典社会学奠基/1. 古典社会学奠基',
    }))
  })

  it('keeps the loaded result window when the URL records another page', async () => {
    const firstEntries = Array.from({ length: 20 }, (_, index) => ({
      ...summary(), knowledge_id: `D1:C${index + 1}`, title: `条目 ${index + 1}`,
    }))
    const secondEntries = Array.from({ length: 20 }, (_, index) => ({
      ...summary(), knowledge_id: `D1:C${index + 21}`, title: `条目 ${index + 21}`,
    }))
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = urlFor(input)
      if (request.pathname === '/api/knowledge/directory') return json(directory())
      if (request.searchParams.has('cursor')) {
        return json({ ...page(secondEntries), next_cursor: 'cursor-40', total_count: 101 })
      }
      return json({ ...page(firstEntries), next_cursor: 'cursor-20', total_count: 101 })
    }))

    function StatefulExplorer() {
      const [state, setState] = useState<KnowledgeUrlState>({ releaseId: 'release-a', query: '条目' })
      return (
        <KnowledgeExplorerPage
          state={state}
          onOpenEntry={vi.fn()}
          onReleaseResolved={() => undefined}
          onStateChange={setState}
        />
      )
    }

    render(<StatefulExplorer />)
    fireEvent.click(await screen.findByRole('button', { name: '继续加载 81 条未显示' }))

    await waitFor(() => expect(screen.getAllByRole('button', { name: /打开 条目/ })).toHaveLength(40))
    expect(screen.getByText('已显示 40 条，共 101 条')).toBeVisible()
  })

  it('hands a complete search result path to the graph without opening detail', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => knowledgeFetch(input)))
    const onLocateEntry = vi.fn()

    render(
      <KnowledgeExplorerPage
        state={{ releaseId: 'release-a', query: '概念' }}
        onLocateEntry={onLocateEntry}
        onOpenEntry={vi.fn()}
        onReleaseResolved={vi.fn()}
        onStateChange={vi.fn()}
      />,
    )

    fireEvent.click(await screen.findByRole('button', { name: '在图中定位 概念' }))

    expect(onLocateEntry).toHaveBeenCalledWith(expect.objectContaining({
      knowledgeId: 'D1:C001',
      directoryPath: expect.arrayContaining([
        expect.objectContaining({ nodeId: 'D1', nodeType: 'dimension' }),
      ]),
    }))
  })

  it('exposes every active filter as removable state', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => knowledgeFetch(input)))
    const onStateChange = vi.fn()

    render(
      <KnowledgeExplorerPage
        state={{
          releaseId: 'release-a',
          query: '概念',
          dimensionId: 'D1',
          categoryId: 'D1:I. 古典社会学奠基/1. 古典社会学奠基',
        }}
        onOpenEntry={vi.fn()}
        onReleaseResolved={vi.fn()}
        onStateChange={onStateChange}
      />,
    )

    fireEvent.click(await screen.findByRole('button', { name: '移除关键词 概念' }))
    expect(onStateChange).toHaveBeenCalledWith(expect.objectContaining({ query: undefined }))
    expect(screen.getByRole('button', { name: '移除维度 本体论' })).toBeVisible()
    expect(screen.getByRole('button', { name: /移除分类 1\. 古典社会学奠基/ })).toBeVisible()
    expect(screen.getByRole('button', { name: '清除全部条件' })).toBeVisible()
  })

  it('resolves the initial release without rewinding newer URL state', async () => {
    let resolveCurrentRelease: ((response: Response) => void) | undefined
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => {
      resolveCurrentRelease = resolve
    })))
    const onReleaseResolved = vi.fn()
    const onStateChange = vi.fn()
    const { rerender } = render(
      <KnowledgeExplorerPage
        state={{ query: '先前查询' }}
        onOpenEntry={vi.fn()}
        onReleaseResolved={onReleaseResolved}
        onStateChange={onStateChange}
      />,
    )

    await waitFor(() => {
      expect(resolveCurrentRelease).toBeTypeOf('function')
    })

    rerender(
      <KnowledgeExplorerPage
        state={{ query: '最新查询' }}
        onOpenEntry={vi.fn()}
        onReleaseResolved={onReleaseResolved}
        onStateChange={onStateChange}
      />,
    )
    if (!resolveCurrentRelease) throw new Error('当前发布请求未发出')
    resolveCurrentRelease(json({
      content_hash: 'sha256:release-a',
      knowledge_release_id: 'release-a',
      level: 'preview',
    }))

    await waitFor(() => {
      expect(onReleaseResolved).toHaveBeenCalledWith('release-a')
    })
    expect(onStateChange).not.toHaveBeenCalled()
  })

  it('shows an unavailable state when the current release cannot be read', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 503 })))

    render(
      <KnowledgeExplorerPage
        state={{}}
        onOpenEntry={vi.fn()}
        onReleaseResolved={vi.fn()}
        onStateChange={vi.fn()}
      />,
    )

    expect(await screen.findByRole('alert')).toHaveTextContent('知识服务暂时不可用')
  })

  it('presents real reviewed relations and a theory seed without adopting it', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = urlFor(input)
      return request.pathname === '/api/knowledge/entries'
        ? json(page())
        : json(detail())
    }))
    const onStartResearch = vi.fn()

    render(
      <KnowledgeEntryPage
        knowledgeId="D1:C001"
        releaseId="release-a"
        onReleaseResolved={vi.fn()}
        onReturnToResearch={vi.fn()}
        onStartResearch={onStartResearch}
      />,
    )

    expect(await screen.findByRole('heading', { name: '概念' })).toBeVisible()
    expect(screen.queryByText('正文节选')).not.toBeInTheDocument()
    expect(screen.getAllByText('一段真实条目正文。')).toHaveLength(1)
    const outline = screen.getByRole('navigation', { name: '本文目录' })
    expect(outline).toBeVisible()
    expect(within(outline).getByRole('link', { name: '正文标题' })).toHaveAttribute('href', '#正文标题')
    expect(screen.getByRole('heading', { name: '正文标题' })).toBeVisible()
    expect(screen.getByRole('heading', { name: '正文标题' })).toHaveAttribute('id', '正文标题')
    expect(screen.getByRole('heading', { name: 'T4 当代发展' })).toHaveAttribute('data-stage', '4')
    const evidenceClaim = screen.getByText('一段真实条目正文。', { selector: 'p' })
    const evidenceNote = screen.getByRole('note', { name: '文献依据，1 条' })
    expect(evidenceClaim).toHaveAttribute('tabindex', '0')
    expect(evidenceClaim).toHaveAttribute('aria-describedby', evidenceNote.id)
    expect(evidenceNote).toHaveAttribute('data-content-role', 'evidence')
    expect(screen.getByText('文献：', { selector: 'strong' })).toBeInTheDocument()
    const articleContent = evidenceClaim.closest('.knowledge-reader__content')
    expect(articleContent).toHaveAttribute('data-evidence-display', 'annotations')
    expect(screen.getByRole('radio', { name: '点击批注显示文献' })).toHaveAttribute('aria-checked', 'true')

    fireEvent.click(screen.getByRole('button', { name: '打开第 1 条文献依据' }))
    expect(screen.getByRole('note', { name: '文献依据，1 条' })).toHaveAttribute('data-open', 'true')

    fireEvent.click(screen.getByRole('radio', { name: '悬浮正文显示文献' }))
    expect(articleContent).toHaveAttribute('data-evidence-display', 'hover')

    fireEvent.click(screen.getByRole('radio', { name: '默认展开全部文献' }))
    expect(articleContent).toHaveAttribute('data-evidence-display', 'expanded')
    expect(screen.getByRole('button', { name: '划线批注（暂未开放）' })).toBeDisabled()
    expect(screen.getByText('知识库原始 Markdown')).toBeVisible()
    expect(screen.getAllByText('待核验')).not.toHaveLength(0)
    expect(screen.getByText('D1:C002')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: '以此理论开始研究' }))
    expect(onStartResearch).toHaveBeenCalledWith({
      theoryId: 'theory-1',
      theoryName: '概念理论',
    })
  })

  it('renders a successful detail slot without another request', async () => {
    const fetch = vi.fn(async () => json(detail()))
    vi.stubGlobal('fetch', fetch)

    render(
      <KnowledgeEntryPage
        knowledgeId="D1:C001"
        releaseId="release-a"
        onReleaseResolved={vi.fn()}
        onStartResearch={vi.fn()}
        renderAfterDetail={(entry) => <p>组合条目 {entry.knowledgeId}</p>}
      />,
    )

    expect(await screen.findByText('组合条目 D1:C001')).toBeVisible()
    expect(fetch).toHaveBeenCalledTimes(1)
  })

})
