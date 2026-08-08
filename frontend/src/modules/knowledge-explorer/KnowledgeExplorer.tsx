import { type FormEvent, useEffect, useState } from 'react'

import './KnowledgeExplorer.css'
import { KnowledgeDirectory } from './KnowledgeDirectory'
import { buildKnowledgeDirectory, type KnowledgeDirectoryDimension } from './directoryTree'
import { KnowledgeEntryList } from './KnowledgeEntryList'
import {
  loadKnowledgeDirectory,
  readCurrentKnowledgeRelease,
  searchKnowledgeEntries,
} from './knowledgeApi'
import type { KnowledgeEntrySummary } from './types'
import type { KnowledgeUrlState } from './urlState'

type ReleaseState = 'loading' | 'ready' | 'degraded' | 'unavailable'
type ResultState = 'ready' | 'empty' | 'error'
const directoryPageSize = 100

export interface KnowledgeExplorerPageProps {
  state: KnowledgeUrlState
  onStateChange: (state: KnowledgeUrlState) => void
  onOpenEntry: (knowledgeId: string) => void
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : '知识服务暂时不可用'
}

function filteredEntries(
  entries: readonly KnowledgeEntrySummary[],
  state: KnowledgeUrlState,
) {
  return entries.filter((entry) =>
    (!state.dimensionId || entry.dimensionId === state.dimensionId) &&
    (!state.categoryId || entry.categoryId === state.categoryId),
  )
}

export function KnowledgeExplorerPage({
  state,
  onStateChange,
  onOpenEntry,
}: KnowledgeExplorerPageProps) {
  const [queryInput, setQueryInput] = useState(state.query ?? '')
  const [loadedReleaseId, setLoadedReleaseId] = useState<string>()
  const [releaseState, setReleaseState] = useState<ReleaseState>('loading')
  const [releaseError, setReleaseError] = useState('')
  const [directoryEntries, setDirectoryEntries] = useState<readonly KnowledgeEntrySummary[]>([])
  const [directory, setDirectory] = useState<readonly KnowledgeDirectoryDimension[]>([])
  const [results, setResults] = useState<readonly KnowledgeEntrySummary[]>([])
  const [resultState, setResultState] = useState<ResultState>('empty')
  const [resultError, setResultError] = useState('')
  const [nextCursor, setNextCursor] = useState<string>()
  const [directoryResultLimit, setDirectoryResultLimit] = useState(directoryPageSize)
  const [resultTotal, setResultTotal] = useState<number>()
  const [loadingMore, setLoadingMore] = useState(false)

  useEffect(() => {
    setQueryInput(state.query ?? '')
  }, [state.query])

  useEffect(() => {
    setDirectoryResultLimit(directoryPageSize)
  }, [state.categoryId, state.dimensionId, state.query])

  useEffect(() => {
    let cancelled = false

    async function loadDirectory() {
      setReleaseState('loading')
      setReleaseError('')
      setLoadedReleaseId(undefined)
      setDirectoryEntries([])
      setDirectory([])
      try {
        let releaseId = state.releaseId
        if (!releaseId) {
          const currentRelease = await readCurrentKnowledgeRelease()
          if (cancelled) return
          onStateChange({ ...state, releaseId: currentRelease.knowledgeReleaseId })
          return
        }

        const entries = await loadKnowledgeDirectory(releaseId)
        const nextDirectory = buildKnowledgeDirectory(entries)
        if (cancelled) return
        setLoadedReleaseId(releaseId)
        setDirectoryEntries(entries)
        setDirectory(nextDirectory)
        setReleaseState('ready')
      } catch (error) {
        if (cancelled) return
        setReleaseError(errorMessage(error))
        setReleaseState(state.releaseId ? 'degraded' : 'unavailable')
      }
    }

    void loadDirectory()
    return () => {
      cancelled = true
    }
  }, [state.releaseId])

  useEffect(() => {
    let cancelled = false
    if (!loadedReleaseId || releaseState !== 'ready') return undefined

    async function loadResults() {
      setResultError('')
      setNextCursor(undefined)
      setResultTotal(undefined)
      if (!state.query) {
        const allResults = filteredEntries(directoryEntries, state)
        const nextResults = allResults.slice(0, directoryResultLimit)
        if (cancelled) return
        setResults(nextResults)
        setResultTotal(allResults.length)
        setResultState(nextResults.length > 0 ? 'ready' : 'empty')
        return
      }

      try {
        const page = await searchKnowledgeEntries({
          releaseId: loadedReleaseId,
          query: state.query,
          dimensionId: state.dimensionId,
          categoryId: state.categoryId,
        })
        if (cancelled) return
        setResults(page.entries)
        setNextCursor(page.nextCursor)
        setResultState(page.entries.length > 0 ? 'ready' : 'empty')
      } catch (error) {
        if (cancelled) return
        setResults([])
        setResultError(errorMessage(error))
        setResultState('error')
      }
    }

    void loadResults()
    return () => {
      cancelled = true
    }
  }, [
    directoryEntries,
    directoryResultLimit,
    loadedReleaseId,
    releaseState,
    state.categoryId,
    state.dimensionId,
    state.query,
  ])

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    updateState({
      ...state,
      query: queryInput.trim() || undefined,
    })
  }

  function updateState(nextState: KnowledgeUrlState) {
    setDirectoryResultLimit(directoryPageSize)
    onStateChange(nextState)
  }

  async function loadMore() {
    if (!state.query) {
      setDirectoryResultLimit((limit) => limit + directoryPageSize)
      return
    }
    if (!loadedReleaseId || !nextCursor) return
    setLoadingMore(true)
    try {
      const page = await searchKnowledgeEntries({
        releaseId: loadedReleaseId,
        query: state.query,
        dimensionId: state.dimensionId,
        categoryId: state.categoryId,
        cursor: nextCursor,
      })
      setResults((current) => [...current, ...page.entries])
      setNextCursor(page.nextCursor)
    } catch (error) {
      setResultError(errorMessage(error))
      setResultState('error')
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <section className="knowledge-explorer" data-release-state={releaseState}>
      <header className="knowledge-explorer__header">
        <div>
          <p className="knowledge-explorer__eyebrow">KNOWLEDGE / PREVIEW</p>
          <h1>知识库</h1>
          <p>按当前发布浏览目录、来源、审核状态与已审核显式关系。</p>
        </div>
      </header>

      <form className="knowledge-explorer__search" aria-label="搜索知识库" onSubmit={submitSearch}>
        <label htmlFor="knowledge-query">关键词</label>
        <input
          id="knowledge-query"
          type="search"
          value={queryInput}
          onChange={(event) => setQueryInput(event.target.value)}
          placeholder="输入理论、概念或方法"
        />
        <button type="submit" disabled={releaseState === 'loading'}>搜索</button>
        {state.query ? (
          <button
            className="knowledge-explorer__plain-action"
            type="button"
            onClick={() => updateState({ ...state, query: undefined })}
          >
            清除
          </button>
        ) : null}
      </form>

      {loadedReleaseId ? (
        <p className="knowledge-explorer__release">
          当前发布 {loadedReleaseId}
        </p>
      ) : null}

      {releaseState === 'loading' ? <p role="status">正在读取当前发布与目录……</p> : null}
      {releaseState === 'unavailable' || releaseState === 'degraded' ? (
        <p className="knowledge-explorer__error" role="alert">{releaseError}</p>
      ) : null}

      {releaseState === 'ready' ? (
        <div className="knowledge-explorer__columns">
          <KnowledgeDirectory
            directory={directory}
            selectedDimensionId={state.dimensionId}
            selectedCategoryId={state.categoryId}
            onSelectDimension={(dimensionId) => updateState({
              ...state,
              dimensionId,
              categoryId: undefined,
            })}
            onSelectCategory={(dimensionId, categoryId) => updateState({
              ...state,
              dimensionId,
              categoryId,
            })}
          />
          <KnowledgeEntryList
            entries={results}
            state={resultState}
            error={resultError}
            hasNextPage={state.query
              ? Boolean(nextCursor)
              : (resultTotal ?? 0) > results.length}
            totalEntries={resultTotal}
            loadingMore={loadingMore}
            onSelect={onOpenEntry}
            onLoadMore={() => void loadMore()}
          />
        </div>
      ) : null}
    </section>
  )
}
