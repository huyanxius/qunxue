import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { KnowledgeEntryPage, KnowledgeExplorerPage } from './index'

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
  }
}

function detail() {
  return {
    ...summary(),
    aliases: ['概念别名'],
    content: '## 正文标题\n\n一段真实条目正文。\n\n> **文献：**示例文献',
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
  it('shows the fixed roots and only the complete release directory', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json(page())))

    render(
      <KnowledgeExplorerPage
        state={{ releaseId: 'release-a' }}
        onOpenEntry={vi.fn()}
        onReleaseResolved={vi.fn()}
        onStateChange={vi.fn()}
      />,
    )

    expect(await screen.findByRole('button', { name: /本体论/ })).toBeVisible()
    const branch = screen.getByText('I. 古典社会学奠基').closest('details')
    expect(branch).toBeInstanceOf(HTMLDetailsElement)
    expect(branch).not.toHaveAttribute('open')
    expect(screen.getAllByText('当前发布暂无可浏览条目')).not.toHaveLength(0)
  })

  it('bounds unfiltered results while retaining the full release directory', async () => {
    const entries = Array.from({ length: 101 }, (_, index) => ({
      ...summary(),
      knowledge_id: `D1:C${index + 1}`,
      title: `条目 ${index + 1}`,
    }))
    vi.stubGlobal('fetch', vi.fn(async () => json(page(entries))))

    render(
      <KnowledgeExplorerPage
        state={{ releaseId: 'release-a' }}
        onOpenEntry={vi.fn()}
        onReleaseResolved={vi.fn()}
        onStateChange={vi.fn()}
      />,
    )

    expect(await screen.findByText('显示 100 / 101 条')).toBeVisible()
  })

  it('hands a complete search result path to the graph without opening detail', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json(page())))
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
    expect(screen.getByRole('heading', { name: '正文标题' })).toBeVisible()
    expect(screen.getByText('文献：', { selector: 'strong' })).toBeVisible()
    expect(screen.getByText('知识库原始 Markdown')).toBeVisible()
    expect(screen.getByText(/核验状态：待核验/)).toBeVisible()
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
