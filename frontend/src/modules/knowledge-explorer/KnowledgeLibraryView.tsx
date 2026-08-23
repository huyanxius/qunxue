import { type FormEvent } from 'react'
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  BooksIcon,
  MagnifyingGlassIcon,
  TreeStructureIcon,
} from '@phosphor-icons/react'

import { KnowledgeCatalog } from './KnowledgeCatalog'
import { KnowledgeEntryList } from './KnowledgeEntryList'
import { KnowledgeLibraryShader } from './KnowledgeLibraryShader'
import type { KnowledgeDirectoryDimension } from './directoryTree'
import type { KnowledgeEntrySummary } from './types'
import type { KnowledgeUrlState } from './urlState'
import { describeTaxonomyNode, dimensionTone } from './taxonomyPresentation'
import './knowledge-ui.css'
import './knowledge-library.css'

export type KnowledgeReleaseViewState = 'loading' | 'ready' | 'unavailable'
export type KnowledgeResultViewState = 'loading' | 'ready' | 'empty' | 'error'

interface KnowledgeLibraryViewProps {
  state: KnowledgeUrlState
  queryInput: string
  releaseState: KnowledgeReleaseViewState
  releaseError: string
  resultState: KnowledgeResultViewState
  resultError: string
  directory: readonly KnowledgeDirectoryDimension[]
  selectedDimension?: KnowledgeDirectoryDimension
  selectedCategoryTitle?: string
  catalogTotal: number
  results: readonly KnowledgeEntrySummary[]
  resultTotal: number
  hasNextPage: boolean
  loadingMore: boolean
  onQueryInputChange: (value: string) => void
  onSearch: () => void
  onStateChange: (state: KnowledgeUrlState) => void
  onOpenEntry: (knowledgeId: string) => void
  onLocateEntry?: (entry: KnowledgeEntrySummary) => void
  onOpenGraph?: () => void
  onLoadMore: () => void
  onRetry: () => void
}

function DimensionOverview({ dimension }: { dimension: KnowledgeDirectoryDimension }) {
  const tone = dimensionTone(dimension.nodeId)
  return (
    <section className="knowledge-collection" aria-labelledby="knowledge-collection-title" data-dimension-tone={tone}>
      <header className="knowledge-collection__hero">
        <span>{dimension.nodeId}</span>
        <h2 id="knowledge-collection-title">{dimension.title}</h2>
        <p>{dimension.entryCount} 条知识，按固定 taxonomy 归入 {dimension.categories.length} 个一级目录。</p>
      </header>
      <section className="knowledge-collection__index" aria-labelledby="knowledge-collection-index-title">
        <header>
          <h3 id="knowledge-collection-index-title">目录</h3>
          <span>{dimension.categories.length} 个分类</span>
        </header>
        <ol>
          {dimension.categories.map((category) => {
            const presentation = describeTaxonomyNode(category.title)
            return (
            <li key={category.nodeId} data-node-kind={presentation.kind}>
              <span className="knowledge-collection__node-badge">{presentation.badge ?? '·'}</span>
              <div>
                <strong>{presentation.label}</strong>
                <small>{category.entryCount} 条知识</small>
              </div>
              <ArrowRightIcon size={15} weight="regular" aria-hidden="true" />
            </li>
            )
          })}
        </ol>
      </section>
    </section>
  )
}

export function KnowledgeLibraryView({
  state,
  queryInput,
  releaseState,
  releaseError,
  resultState,
  resultError,
  directory,
  selectedDimension,
  selectedCategoryTitle,
  catalogTotal,
  results,
  resultTotal,
  hasNextPage,
  loadingMore,
  onQueryInputChange,
  onSearch,
  onStateChange,
  onOpenEntry,
  onLocateEntry,
  onOpenGraph,
  onLoadMore,
  onRetry,
}: KnowledgeLibraryViewProps) {
  const showEntries = Boolean(state.query || state.categoryId)
  const hasFilters = Boolean(state.query || state.dimensionId || state.categoryId)
  const activeDimension = selectedDimension ?? directory[0]

  function updateState(nextState: KnowledgeUrlState) {
    onStateChange({ ...nextState, loadedPages: undefined })
  }

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSearch()
  }

  return (
    <section
      className="knowledge-surface knowledge-library"
      data-release-state={releaseState}
      data-dimension-tone={activeDimension ? dimensionTone(activeDimension.nodeId) : undefined}
    >
      <KnowledgeLibraryShader />
      <aside className="knowledge-library__sidebar">
        <header className="knowledge-library__identity">
          <BooksIcon size={18} weight="regular" aria-hidden="true" />
          <h1>知识库</h1>
          {releaseState === 'ready' ? <small>{catalogTotal}</small> : null}
        </header>

        <form className="knowledge-library__search" aria-label="搜索知识库" onSubmit={submitSearch}>
          <MagnifyingGlassIcon size={15} weight="regular" aria-hidden="true" />
          <label htmlFor="knowledge-query" className="knowledge-ui__visually-hidden">
            搜索理论、概念或方法
          </label>
          <input
            id="knowledge-query"
            type="search"
            value={queryInput}
            onChange={(event) => onQueryInputChange(event.target.value)}
            placeholder="搜索知识库"
          />
          <button type="submit" aria-label="提交搜索" disabled={releaseState === 'loading'}>
            <ArrowRightIcon size={14} weight="bold" aria-hidden="true" />
          </button>
        </form>

        {releaseState === 'ready' ? (
          <KnowledgeCatalog
            directory={directory}
            selectedDimension={selectedDimension}
            selectedCategoryId={state.categoryId}
            onSelectDimension={(dimensionId) => updateState({ ...state, dimensionId, categoryId: undefined })}
            onSelectCategory={(dimensionId, categoryId) => updateState({ ...state, dimensionId, categoryId })}
          />
        ) : null}
      </aside>

      <main className="knowledge-library__main">
        <header className="knowledge-library__topbar">
          <p>
            <span>知识库</span>
            {activeDimension ? <><b>/</b>{activeDimension.title}</> : null}
            {selectedCategoryTitle ? <><b>/</b>{selectedCategoryTitle}</> : null}
          </p>
          <div className="knowledge-library__toolbar">
            <span>{catalogTotal} 条知识</span>
            {onOpenGraph ? (
              <button type="button" aria-label="打开知识图谱" onClick={onOpenGraph}>
                <TreeStructureIcon size={15} weight="regular" aria-hidden="true" />
                <span>打开知识图谱</span>
              </button>
            ) : null}
          </div>
        </header>

        <div className="knowledge-library__content">
          {hasFilters ? (
            <div className="knowledge-library__filters" aria-label="当前筛选条件">
              {state.query ? (
                <button type="button" data-filter-role="query" aria-label={`移除关键词 ${state.query}`} onClick={() => updateState({ ...state, query: undefined })}>
                  关键词 · {state.query}<b aria-hidden="true">×</b>
                </button>
              ) : null}
              {state.dimensionId ? (
                <button type="button" data-filter-role="dimension" aria-label={`移除维度 ${selectedDimension?.title ?? state.dimensionId}`} onClick={() => updateState({ ...state, dimensionId: undefined, categoryId: undefined })}>
                  维度 · {selectedDimension?.title ?? state.dimensionId}<b aria-hidden="true">×</b>
                </button>
              ) : null}
              {state.categoryId ? (
                <button type="button" data-filter-role="category" aria-label={`移除分类 ${selectedCategoryTitle ?? state.categoryId}`} onClick={() => updateState({ ...state, categoryId: undefined })}>
                  分类 · {selectedCategoryTitle ?? state.categoryId}<b aria-hidden="true">×</b>
                </button>
              ) : null}
              <button className="knowledge-library__clear" type="button" aria-label="清除全部条件" onClick={() => updateState({ releaseId: state.releaseId, returnTo: state.returnTo })}>
                清除全部
              </button>
            </div>
          ) : null}

          {releaseState === 'loading' ? (
            <div className="knowledge-ui__loading" role="status"><span />正在读取知识目录</div>
          ) : null}
          {releaseState === 'unavailable' ? (
            <div className="knowledge-ui__state" role="alert">
              <strong>知识目录暂时无法读取</strong><p>{releaseError}</p>
              <button type="button" onClick={onRetry}>重新读取</button>
            </div>
          ) : null}

          {releaseState === 'ready' && !showEntries && activeDimension ? (
            <DimensionOverview dimension={activeDimension} />
          ) : null}

          {releaseState === 'ready' && showEntries ? (
            <section className="knowledge-library__results-view" aria-label="知识条目结果">
              {state.categoryId && selectedDimension ? (
                <button
                  className="knowledge-library__results-back"
                  type="button"
                  aria-label={`返回 ${selectedDimension.title} 目录`}
                  onClick={() => updateState({ ...state, query: undefined, categoryId: undefined })}
                >
                  <ArrowLeftIcon size={14} weight="bold" aria-hidden="true" />
                  返回 {selectedDimension.title} 目录
                </button>
              ) : null}
              <KnowledgeEntryList
                entries={results}
                state={resultState}
                error={resultError}
                hasNextPage={hasNextPage}
                totalEntries={resultTotal}
                loadingMore={loadingMore}
                onSelect={onOpenEntry}
                onLocate={onLocateEntry}
                onLoadMore={onLoadMore}
                onRetry={onRetry}
              />
            </section>
          ) : null}
        </div>
      </main>
    </section>
  )
}
