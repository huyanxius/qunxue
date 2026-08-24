import type { CSSProperties } from 'react'
import { ArrowSquareOutIcon } from '@phosphor-icons/react'

import type { KnowledgeEntrySummary } from './types'
import { describeTaxonomyNode, dimensionTone } from './taxonomyPresentation'

interface KnowledgeEntryListProps {
  entries: readonly KnowledgeEntrySummary[]
  state: 'loading' | 'ready' | 'empty' | 'error'
  error?: string
  hasNextPage: boolean
  totalEntries: number
  loadingMore: boolean
  onSelect: (knowledgeId: string) => void
  onLocate?: (entry: KnowledgeEntrySummary) => void
  onLoadMore: () => void
  onRetry: () => void
}

export function KnowledgeEntryList({
  entries,
  state,
  error,
  hasNextPage,
  totalEntries,
  loadingMore,
  onSelect,
  onLocate,
  onLoadMore,
  onRetry,
}: KnowledgeEntryListProps) {
  const remaining = Math.max(0, totalEntries - entries.length)

  function contextPath(entry: KnowledgeEntrySummary) {
    const end = entry.directoryPath.length >= 4 ? -2 : -1
    return entry.directoryPath.slice(1, end).map((node) => node.title).join(' / ') || '七维知识目录'
  }

  return (
    <section className="knowledge-explorer__results" aria-labelledby="knowledge-results-title" data-result-state={state}>
      <header className="knowledge-explorer__results-heading">
        <div>
          <p>搜索结果</p>
          <h2 id="knowledge-results-title">条目</h2>
        </div>
        {state === 'ready' ? <p aria-live="polite">已显示 {entries.length} 条，共 {totalEntries} 条</p> : null}
      </header>

      {state === 'loading' ? (
        <div className="knowledge-explorer__result-skeleton" role="status" aria-label="正在读取条目">
          {[0, 1, 2, 3].map((index) => <span key={index} />)}
        </div>
      ) : null}
      {state === 'error' ? (
        <div className="knowledge-explorer__state" role="alert">
          <strong>条目没有成功载入</strong><p>{error}</p>
          <button type="button" onClick={onRetry}>重新读取</button>
        </div>
      ) : null}
      {state === 'empty' ? (
        <div className="knowledge-explorer__state">
          <strong>没有找到符合条件的条目</strong>
          <p>可以移除部分筛选，或换一个更宽的理论关键词。</p>
        </div>
      ) : null}

      {entries.length > 0 ? (
        <ol className="knowledge-explorer__result-list">
          {entries.map((entry, index) => {
            const category = describeTaxonomyNode(entry.category)
            return (
            <li
              key={`${entry.knowledgeId}:${entry.contentVersion}`}
              data-dimension-tone={dimensionTone(entry.dimensionId)}
              style={{ '--entry-index': index } as CSSProperties}
            >
              <span className="knowledge-explorer__result-index" aria-hidden="true">
                {entry.knowledgeId.split(':').at(-1)}
              </span>
              <button className="knowledge-explorer__result-main" type="button" aria-label={`打开 ${entry.title}`} onClick={() => onSelect(entry.knowledgeId)}>
                <span className="knowledge-explorer__result-kicker">
                  <span>{entry.dimensionId} {entry.dimension}</span>
                  <span data-node-kind={category.kind}>{category.badge ?? '分类'} {category.label}</span>
                </span>
                <strong>{entry.title}</strong>
                <small>{contextPath(entry)}</small>
              </button>
              <div className="knowledge-explorer__result-meta">
                {onLocate ? (
                  <button type="button" aria-label={`在图中定位 ${entry.title}`} onClick={() => onLocate(entry)}>
                    定位图谱 <ArrowSquareOutIcon size={13} weight="regular" aria-hidden="true" />
                  </button>
                ) : null}
              </div>
            </li>
            )
          })}
        </ol>
      ) : null}

      {hasNextPage ? (
        <button className="knowledge-explorer__load-more" type="button" disabled={loadingMore} aria-label={`继续加载 ${remaining} 条未显示`} onClick={onLoadMore}>
          <span>{loadingMore ? '正在读取下一批' : '继续加载'}</span>
          <small>{remaining} 条未显示</small>
        </button>
      ) : null}
    </section>
  )
}
