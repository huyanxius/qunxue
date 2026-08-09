import type { KnowledgeEntrySummary } from './types'
import { reviewStatusLabels } from './labels'

interface KnowledgeEntryListProps {
  entries: readonly KnowledgeEntrySummary[]
  state: 'ready' | 'empty' | 'error'
  error?: string
  hasNextPage: boolean
  totalEntries?: number
  loadingMore: boolean
  onSelect: (knowledgeId: string) => void
  onLocate?: (entry: KnowledgeEntrySummary) => void
  onLoadMore: () => void
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
}: KnowledgeEntryListProps) {
  return (
    <section
      className="knowledge-explorer__results"
      aria-labelledby="knowledge-results-title"
      data-result-state={state}
    >
      <h2 id="knowledge-results-title">条目</h2>
      {state === 'error' ? (
        <p className="knowledge-explorer__error" role="alert">{error}</p>
      ) : null}
      {state === 'empty' ? <p>当前条件下没有可浏览条目。</p> : null}
      {totalEntries !== undefined && totalEntries > entries.length ? (
        <p>显示 {entries.length} / {totalEntries} 条</p>
      ) : null}
      {entries.length > 0 ? (
        <ul>
          {entries.map((entry) => (
            <li key={`${entry.knowledgeId}:${entry.contentVersion}`}>
              <div className="knowledge-explorer__result-actions">
                <button type="button" onClick={() => onSelect(entry.knowledgeId)}>
                  <span>{entry.title}</span>
                  <small>
                    {entry.dimension} · {entry.directoryPath.map((node) => node.title).join(' / ')} · {reviewStatusLabels[entry.reviewStatus]}
                  </small>
                </button>
                {onLocate ? (
                  <button
                    type="button"
                    className="knowledge-explorer__locate"
                    aria-label={`在图中定位 ${entry.title}`}
                    onClick={() => onLocate(entry)}
                  >
                    定位图中
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
      {hasNextPage ? (
        <button
          className="knowledge-explorer__load-more"
          type="button"
          disabled={loadingMore}
          onClick={onLoadMore}
        >
          {loadingMore ? '正在读取…' : '继续读取'}
        </button>
      ) : null}
    </section>
  )
}
