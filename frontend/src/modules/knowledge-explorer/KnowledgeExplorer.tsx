import { useEffect, useMemo, useRef, useState } from 'react'

import { buildKnowledgeDirectory, type KnowledgeDirectoryDimension } from './directoryTree'
import { KnowledgeLibraryView } from './KnowledgeLibraryView'
import {
  readCurrentKnowledgeRelease,
  readKnowledgeDirectory,
  searchKnowledgeEntries,
} from './knowledgeApi'
import type { KnowledgeEntrySummary } from './types'
import type { KnowledgeUrlState } from './urlState'
import { readKnowledgeListScroll } from './listContext'

type ReleaseState = 'loading' | 'ready' | 'unavailable'
type ResultState = 'loading' | 'ready' | 'empty' | 'error'
const resultPageSize = 20

export interface KnowledgeExplorerPageProps {
  state: KnowledgeUrlState
  onStateChange: (state: KnowledgeUrlState) => void
  onReleaseResolved: (releaseId: string) => void
  onOpenEntry: (knowledgeId: string) => void
  onLocateEntry?: (entry: KnowledgeEntrySummary) => void
  onOpenGraph?: () => void
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : '知识服务暂时不可用'
}

export function KnowledgeExplorerPage({
  state,
  onStateChange,
  onReleaseResolved,
  onOpenEntry,
  onLocateEntry,
  onOpenGraph,
}: KnowledgeExplorerPageProps) {
  const [queryInput, setQueryInput] = useState(state.query ?? '')
  const [loadedReleaseId, setLoadedReleaseId] = useState<string>()
  const [releaseState, setReleaseState] = useState<ReleaseState>('loading')
  const [releaseError, setReleaseError] = useState('')
  const [directory, setDirectory] = useState<readonly KnowledgeDirectoryDimension[]>([])
  const [results, setResults] = useState<readonly KnowledgeEntrySummary[]>([])
  const [resultState, setResultState] = useState<ResultState>('loading')
  const [resultError, setResultError] = useState('')
  const [nextCursor, setNextCursor] = useState<string>()
  const [resultTotal, setResultTotal] = useState(0)
  const [loadingMore, setLoadingMore] = useState(false)
  const [retryKey, setRetryKey] = useState(0)
  const [restoredContext, setRestoredContext] = useState(false)
  const restorePageTargets = useRef(new Map<string, number>())
  const resultSignature = [loadedReleaseId, state.query, state.dimensionId, state.categoryId].join('|')
  if (!restorePageTargets.current.has(resultSignature)) {
    restorePageTargets.current.set(resultSignature, state.loadedPages ?? 1)
  }
  const pagesToRestore = restorePageTargets.current.get(resultSignature) ?? 1
  const shouldShowEntries = Boolean(state.query || state.categoryId)

  useEffect(() => {
    setQueryInput(state.query ?? '')
  }, [state.query])

  useEffect(() => {
    let cancelled = false

    async function loadDirectory() {
      setReleaseState('loading')
      setReleaseError('')
      setLoadedReleaseId(undefined)
      setDirectory([])
      try {
        if (!state.releaseId) {
          const currentRelease = await readCurrentKnowledgeRelease()
          if (!cancelled) onReleaseResolved(currentRelease.knowledgeReleaseId)
          return
        }
        const facets = await readKnowledgeDirectory(state.releaseId)
        if (cancelled) return
        setLoadedReleaseId(state.releaseId)
        setDirectory(buildKnowledgeDirectory(facets))
        setReleaseState('ready')
      } catch (error) {
        if (cancelled) return
        setReleaseError(errorMessage(error))
        setReleaseState('unavailable')
      }
    }

    void loadDirectory()
    return () => { cancelled = true }
  }, [onReleaseResolved, retryKey, state.releaseId])

  useEffect(() => {
    let cancelled = false
    if (!loadedReleaseId || releaseState !== 'ready') return undefined
    if (!shouldShowEntries) {
      setResults([])
      setResultTotal(0)
      setNextCursor(undefined)
      setResultState('ready')
      return undefined
    }
    async function loadResults() {
      setResultState('loading')
      setResultError('')
      setResults([])
      setNextCursor(undefined)
      try {
        let cursor: string | undefined
        let entries: KnowledgeEntrySummary[] = []
        let totalCount = 0
        for (let pageNumber = 0; pageNumber < pagesToRestore; pageNumber += 1) {
          const page = await searchKnowledgeEntries({
            releaseId: loadedReleaseId,
            query: state.query,
            dimensionId: state.dimensionId,
            categoryId: state.categoryId,
            cursor,
            limit: resultPageSize,
          })
          entries = [...entries, ...page.entries]
          totalCount = page.totalCount
          cursor = page.nextCursor
          if (!cursor) break
        }
        if (cancelled) return
        setResults(entries)
        setResultTotal(totalCount)
        setNextCursor(cursor)
        setResultState(entries.length > 0 ? 'ready' : 'empty')
      } catch (error) {
        if (cancelled) return
        setResultError(errorMessage(error))
        setResultState('error')
      }
    }

    void loadResults()
    return () => { cancelled = true }
  }, [
    loadedReleaseId,
    pagesToRestore,
    releaseState,
    retryKey,
    state.categoryId,
    state.dimensionId,
    state.query,
    shouldShowEntries,
  ])

  useEffect(() => {
    if (resultState !== 'ready' || restoredContext || typeof window.scrollTo !== 'function') return
    const scrollY = readKnowledgeListScroll(state)
    if (scrollY === undefined) return
    setRestoredContext(true)
    requestAnimationFrame(() => window.scrollTo({ top: scrollY, behavior: 'auto' }))
  }, [restoredContext, resultState, state])

  const selectedDimension = useMemo(
    () => directory.find((item) => item.nodeId === state.dimensionId),
    [directory, state.dimensionId],
  )
  const selectedCategory = useMemo(() => {
    function find(
      categories: readonly { nodeId: string; title: string; children: readonly unknown[] }[],
      parentTitle?: string,
    ): string | undefined {
      for (const category of categories) {
        if (category.nodeId === state.categoryId) {
          return /^T\d+\s/.test(category.title) && parentTitle ? parentTitle : category.title
        }
        const nested = find(category.children as readonly typeof category[], category.title)
        if (nested) return nested
      }
      return undefined
    }
    return selectedDimension ? find(selectedDimension.categories) : undefined
  }, [selectedDimension, state.categoryId])
  const catalogTotal = useMemo(
    () => directory.reduce((total, dimension) => total + dimension.entryCount, 0),
    [directory],
  )

  function updateState(nextState: KnowledgeUrlState) {
    onStateChange({ ...nextState, loadedPages: undefined })
  }

  async function loadMore() {
    if (!loadedReleaseId || !nextCursor) return
    setLoadingMore(true)
    setResultError('')
    try {
      const page = await searchKnowledgeEntries({
        releaseId: loadedReleaseId,
        query: state.query,
        dimensionId: state.dimensionId,
        categoryId: state.categoryId,
        cursor: nextCursor,
        limit: resultPageSize,
      })
      setResults((current) => [...current, ...page.entries])
      setResultTotal(page.totalCount)
      setNextCursor(page.nextCursor)
      const loadedPages = (state.loadedPages ?? 1) + 1
      restorePageTargets.current.set(resultSignature, loadedPages)
      onStateChange({ ...state, loadedPages })
    } catch (error) {
      setResultError(errorMessage(error))
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <KnowledgeLibraryView
      state={state}
      queryInput={queryInput}
      releaseState={releaseState}
      releaseError={releaseError}
      resultState={resultState}
      resultError={resultError}
      directory={directory}
      selectedDimension={selectedDimension}
      selectedCategoryTitle={selectedCategory}
      catalogTotal={catalogTotal}
      results={results}
      resultTotal={resultTotal}
      hasNextPage={Boolean(nextCursor)}
      loadingMore={loadingMore}
      onQueryInputChange={setQueryInput}
      onSearch={() => updateState({ ...state, query: queryInput.trim() || undefined })}
      onStateChange={onStateChange}
      onOpenEntry={onOpenEntry}
      onLocateEntry={onLocateEntry}
      onOpenGraph={onOpenGraph}
      onLoadMore={() => void loadMore()}
      onRetry={() => setRetryKey((value) => value + 1)}
    />
  )
}
