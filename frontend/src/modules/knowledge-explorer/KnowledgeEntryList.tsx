import type { KnowledgeExplorerEntry } from './types'
import { reviewStatusLabels } from './labels'

interface KnowledgeEntryListProps {
  entries: readonly KnowledgeExplorerEntry[]
  state: 'loading' | 'ready' | 'error'
  error: string
  selectedKnowledgeId?: string
  hasNextPage: boolean
  onSelect: (knowledgeId: string) => void
  onLoadMore: () => void
}

export function KnowledgeEntryList({
  entries,
  state,
  error,
  selectedKnowledgeId,
  hasNextPage,
  onSelect,
  onLoadMore,
}: KnowledgeEntryListProps) {
  return (
    <section
      className="knowledge-explorer__results"
      aria-labelledby="knowledge-results-title"
      aria-busy={state === 'loading'}
    >
      <h2 id="knowledge-results-title">条目</h2>
      {state === 'loading' && entries.length === 0 ? (
        <p role="status">正在读取当前发布……</p>
      ) : null}
      {state === 'error' ? (
        <p className="knowledge-explorer__error" role="alert">
          {error}
        </p>
      ) : null}
      {state === 'ready' && entries.length === 0 ? (
        <p>当前条件下没有可浏览条目。</p>
      ) : null}
      {entries.length > 0 ? (
        <ul>
          {entries.map((entry) => (
            <li key={`${entry.knowledgeId}:${entry.contentVersion}`}>
              <button
                type="button"
                aria-pressed={selectedKnowledgeId === entry.knowledgeId}
                onClick={() => onSelect(entry.knowledgeId)}
              >
                <span>{entry.title}</span>
                <small>
                  {entry.dimension} / {entry.category} ·{' '}
                  {reviewStatusLabels[entry.reviewStatus]} · v
                  {entry.contentVersion}
                </small>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {hasNextPage ? (
        <button
          className="knowledge-explorer__load-more"
          type="button"
          disabled={state === 'loading'}
          onClick={onLoadMore}
        >
          继续读取
        </button>
      ) : null}
    </section>
  )
}
