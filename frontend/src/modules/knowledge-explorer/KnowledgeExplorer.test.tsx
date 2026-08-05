import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  KnowledgeExplorer,
  type KnowledgeExplorerDataSource,
  type KnowledgeExplorerDetail,
  type KnowledgeExplorerPage,
  type KnowledgeExplorerRelease,
} from './index'

const release: KnowledgeExplorerRelease = {
  knowledgeReleaseId: 'release-final-1',
  level: 'final',
  contentHash: 'sha256:knowledge-v1',
}

const resultPage: KnowledgeExplorerPage = {
  release,
  entries: [
    {
      knowledgeId: 'knowledge-field-theory',
      contentVersion: 3,
      title: '场域理论',
      category: '理论',
      dimension: '理论体系',
      reviewStatus: 'reviewed',
    },
  ],
}

const detail: KnowledgeExplorerDetail = {
  entry: resultPage.entries[0],
  content: '场域是由位置及其关系构成的分析空间。',
  theoryId: 'theory-field',
  sources: [
    {
      sourceId: 'source-book-1',
      title: '实践与反思',
      contributor: '布迪厄、华康德',
      year: 1998,
      locator: '第 3 章',
      sourceType: '学术著作',
      verificationStatus: 'verified',
      usageBoundary: '用于概念定义，不替代对研究情境的适用性判断。',
    },
  ],
  relations: [
    {
      relationId: 'relation-field-habitus',
      sourceKnowledgeId: 'knowledge-field-theory',
      targetKnowledgeId: 'knowledge-habitus',
      relatedTitle: '惯习',
      relationType: '概念依赖',
      direction: 'directed',
      description: '场域分析通常需要结合行动者的惯习。',
      evidenceSourceIds: ['source-book-1'],
      evidenceGrade: 'A',
      reviewStatus: 'reviewed',
      contentVersion: 2,
    },
  ],
  useEligibility: {
    browseEligible: true,
    ragEligible: true,
    trainingCandidateEligible: false,
    matchEligible: true,
    reviewRecordIds: ['review-knowledge-3'],
  },
}

function dataSource(
  page: KnowledgeExplorerPage = resultPage,
): KnowledgeExplorerDataSource {
  return {
    currentRelease: vi.fn(async () => release),
    search: vi.fn(async () => page),
    getEntry: vi.fn(async () => detail),
  }
}

afterEach(() => {
  cleanup()
})

describe('KnowledgeExplorer', () => {
  it('browses a release and shows sources, relations, and independent use admission', async () => {
    const source = dataSource()

    render(
      <KnowledgeExplorer
        dataSource={source}
        initialKnowledgeId="knowledge-field-theory"
      />,
    )

    expect(await screen.findByRole('heading', { name: '场域理论' })).toBeVisible()
    expect(screen.getByText('实践与反思')).toBeVisible()
    expect(screen.getByText(/使用边界：用于概念定义/)).toBeVisible()
    expect(screen.getByRole('button', { name: '惯习' })).toBeVisible()
    expect(screen.getByText('训练候选').nextElementSibling).toHaveTextContent(
      '未准入',
    )
    expect(screen.getByText('理论匹配').nextElementSibling).toHaveTextContent(
      '已准入',
    )
    expect(source.getEntry).toHaveBeenCalledWith({
      knowledgeId: 'knowledge-field-theory',
      releaseId: 'release-final-1',
    })
  })

  it('passes a submitted query to the injected data source', async () => {
    const source = dataSource()

    render(<KnowledgeExplorer dataSource={source} />)
    await screen.findByRole('button', { name: /场域理论/ })

    fireEvent.change(screen.getByRole('searchbox', { name: '关键词' }), {
      target: { value: '  惯习  ' },
    })
    fireEvent.submit(screen.getByRole('form', { name: '搜索知识库' }))

    await waitFor(() => {
      expect(source.search).toHaveBeenLastCalledWith({
        releaseId: 'release-final-1',
        query: '惯习',
        cursor: undefined,
      })
    })
  })

  it('shows loading and empty-result states', async () => {
    let resolveRelease: ((value: KnowledgeExplorerRelease) => void) | undefined
    const source = dataSource({ ...resultPage, entries: [] })
    source.currentRelease = vi.fn(
      () =>
        new Promise<KnowledgeExplorerRelease>((resolve) => {
          resolveRelease = resolve
        }),
    )

    render(<KnowledgeExplorer dataSource={source} />)

    expect(screen.getByRole('status')).toHaveTextContent('正在读取当前发布')
    resolveRelease?.(release)

    expect(
      await screen.findByText('当前条件下没有可浏览条目。'),
    ).toBeVisible()
  })

  it('shows data-source errors without blanking the page', async () => {
    const source = dataSource()
    source.currentRelease = vi.fn(async () => {
      throw new Error('演示数据读取失败')
    })

    render(<KnowledgeExplorer dataSource={source} />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '演示数据读取失败',
    )
    expect(
      screen.getByRole('heading', { name: '可视化知识库' }),
    ).toBeVisible()
  })
})
