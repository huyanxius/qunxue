import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { MagnifyingGlassIcon } from '@phosphor-icons/react'

import './FullscreenKnowledgeGraph.css'
import { ObsidianKnowledgeGraph } from './ObsidianKnowledgeGraph'
import {
  mergeDirectoryPath,
  mergeGraphEntries,
  mergeRelationCandidates,
  mergeReviewedRelations,
  mergeStructuralConnections,
} from './knowledgeGraphAdapter'
import {
  readCurrentKnowledgeGraphRelease,
  readIncidentCandidatePage,
  readIncidentRelationPage,
  readKnowledgeGraphFocusEntry,
  readStructuralConnectionPage,
  searchKnowledgeGraphEntries,
} from './knowledgeGraphApi'
import type {
  KnowledgeGraphEdge,
  KnowledgeGraphFocusEntry,
  KnowledgeGraphProjection,
} from './types'

const dimensions = [
  ['D1', '本体论'],
  ['D2', '实践论'],
  ['D3', '方法论'],
  ['D4', '价值论'],
  ['D5', '认识论'],
  ['D6', '学派传统'],
  ['D7', '学科史'],
] as const

type PageCursor = string | undefined
type StructureLayer = 'children' | 'siblings'

export interface FullscreenKnowledgeGraphState {
  readonly releaseId?: string
  readonly query?: string
  readonly centerId?: string
  readonly pendingEnabled?: boolean
}

interface FullscreenKnowledgeGraphPageProps {
  readonly state: FullscreenKnowledgeGraphState
  readonly onStateChange: (changes: Partial<FullscreenKnowledgeGraphState>) => void
  readonly entryHref: (knowledgeId: string) => string
}

function initialProjection(releaseId: string): KnowledgeGraphProjection {
  return {
    releaseId,
    nodes: dimensions.map(([id, label]) => ({ id, label, nodeType: 'dimension' })),
    edges: [],
  }
}

function focusProjection(
  releaseId: string,
  focus: KnowledgeGraphFocusEntry,
): KnowledgeGraphProjection {
  return mergeGraphEntries({ releaseId, nodes: [], edges: [] }, [focus])
}

function message(error: unknown) {
  return error instanceof Error ? error.message : '知识图谱暂时不可用'
}

function removeCandidateLayer(
  projection: KnowledgeGraphProjection,
  focusNodeId?: string,
) {
  const candidateEdges = projection.edges.filter((edge) => edge.layer === 'candidate')
  if (candidateEdges.length === 0) return projection
  const candidateNodeIds = new Set(candidateEdges.flatMap((edge) => [edge.source, edge.target]))
  const edges = projection.edges.filter((edge) => edge.layer !== 'candidate')
  const retainedNodeIds = new Set(edges.flatMap((edge) => [edge.source, edge.target]))
  if (focusNodeId) retainedNodeIds.add(focusNodeId)
  return {
    ...projection,
    nodes: projection.nodes.filter(
      (node) => !candidateNodeIds.has(node.id) || retainedNodeIds.has(node.id),
    ),
    edges,
  }
}

function endpointIds(input: readonly { source_knowledge_id: string; target_knowledge_id: string }[]) {
  return [...new Set(input.flatMap((item) => [
    item.source_knowledge_id,
    item.target_knowledge_id,
  ]))]
}

async function hydrateEntries(input: {
  releaseId: string
  projection: KnowledgeGraphProjection
  knowledgeIds: readonly string[]
}) {
  const knownTitles = new Set(
    input.projection.nodes
      .filter((node) => node.label !== node.id)
      .map((node) => node.id),
  )
  return Promise.all(
    input.knowledgeIds
      .filter((knowledgeId) => !knownTitles.has(knowledgeId))
      .map((knowledgeId) => readKnowledgeGraphFocusEntry({
        releaseId: input.releaseId,
        knowledgeId,
      })),
  )
}

function endpointTitles(
  projection: KnowledgeGraphProjection,
  entries: readonly KnowledgeGraphFocusEntry[],
) {
  return new Map([
    ...projection.nodes.map((node) => [node.id, node.label] as const),
    ...entries.map((entry) => [entry.knowledgeId, entry.title] as const),
  ])
}

export function FullscreenKnowledgeGraphPage({
  state,
  onStateChange,
  entryHref,
}: FullscreenKnowledgeGraphPageProps) {
  const activeReleaseId = state.releaseId ?? ''
  const centerId = state.centerId?.trim() ?? ''
  const query = state.query?.trim() ?? ''
  const pendingEnabled = state.pendingEnabled ?? false
  const [queryInput, setQueryInput] = useState(query)
  const [searchResults, setSearchResults] = useState<readonly KnowledgeGraphFocusEntry[]>([])
  const [searchCursor, setSearchCursor] = useState<PageCursor>()
  const [searching, setSearching] = useState(false)
  const [searchComplete, setSearchComplete] = useState(false)
  const [searchResultsOpen, setSearchResultsOpen] = useState(false)
  const [focus, setFocus] = useState<KnowledgeGraphFocusEntry>()
  const [projection, setProjection] = useState(() => initialProjection(activeReleaseId || 'current'))
  const projectionRef = useRef(projection)
  projectionRef.current = projection
  const [structureCursors, setStructureCursors] = useState<Record<StructureLayer, PageCursor>>({
    children: undefined,
    siblings: undefined,
  })
  const [relationCursor, setRelationCursor] = useState<PageCursor>()
  const [candidateCursor, setCandidateCursor] = useState<PageCursor>()
  const [directoryCursor, setDirectoryCursor] = useState<{
    nodeId: string
    cursor: string
  }>()
  const [relationTotal, setRelationTotal] = useState<number>()
  const [candidateTotal, setCandidateTotal] = useState(0)
  const [selectedEdgeId, setSelectedEdgeId] = useState<string>()
  const [loadingCenter, setLoadingCenter] = useState(false)
  const [error, setError] = useState('')
  const centerRequest = useRef(0)
  const searchRequest = useRef(0)
  const activeCenter = useRef(centerId)
  activeCenter.current = centerId

  useEffect(() => setQueryInput(query), [query])

  useEffect(() => {
    if (state.releaseId) return
    let cancelled = false
    void readCurrentKnowledgeGraphRelease()
      .then((nextReleaseId) => {
        if (!cancelled) onStateChange({ releaseId: nextReleaseId })
      })
      .catch((nextError) => {
        if (!cancelled) setError(message(nextError))
      })
    return () => {
      cancelled = true
    }
  }, [onStateChange, state.releaseId])

  const runSearch = useCallback(async (searchQuery: string, cursor?: string) => {
    if (!activeReleaseId || !searchQuery) return
    const request = ++searchRequest.current
    setSearching(true)
    setError('')
    try {
      const page = await searchKnowledgeGraphEntries({
        releaseId: activeReleaseId,
        query: searchQuery,
        cursor,
      })
      if (request !== searchRequest.current) return
      setSearchResults((current) => cursor ? [...current, ...page.entries] : page.entries)
      setSearchCursor(page.nextCursor)
      setSearchComplete(true)
      setSearchResultsOpen(true)
    } catch (nextError) {
      if (request === searchRequest.current) setError(message(nextError))
    } finally {
      if (request === searchRequest.current) setSearching(false)
    }
  }, [activeReleaseId])

  useEffect(() => {
    if (query && activeReleaseId) void runSearch(query)
    if (!query) {
      setSearchResults([])
      setSearchCursor(undefined)
      setSearchComplete(false)
      setSearchResultsOpen(false)
    }
  }, [activeReleaseId, query, runSearch])

  useEffect(() => {
    if (!activeReleaseId) return
    if (!centerId) {
      centerRequest.current += 1
      setFocus(undefined)
      setProjection(initialProjection(activeReleaseId))
      setRelationTotal(undefined)
      setCandidateTotal(0)
      return
    }
    const request = ++centerRequest.current
    setLoadingCenter(true)
    setError('')
    setSelectedEdgeId(undefined)

    async function loadCenter() {
      try {
        const nextFocus = await readKnowledgeGraphFocusEntry({
          releaseId: activeReleaseId,
          knowledgeId: centerId,
        })
        let nextProjection = mergeDirectoryPath(
          focusProjection(activeReleaseId, nextFocus),
          nextFocus,
        )

        const parentNodeId = nextFocus.directoryPath.at(-1)?.nodeId
        const [children, siblings, relations] = await Promise.all([
          readStructuralConnectionPage({
            releaseId: activeReleaseId,
            sourceNodeId: nextFocus.knowledgeId,
          }),
          parentNodeId ? readStructuralConnectionPage({
            releaseId: activeReleaseId,
            sourceNodeId: parentNodeId,
          }) : Promise.resolve({ connections: [] as const, nextCursor: undefined }),
          readIncidentRelationPage({
            releaseId: activeReleaseId,
            knowledgeId: nextFocus.knowledgeId,
          }),
        ])
        nextProjection = mergeStructuralConnections(nextProjection, children.connections)
        nextProjection = mergeStructuralConnections(
          nextProjection,
          siblings.connections.filter(
            (connection) => connection.target_node_id !== nextFocus.knowledgeId,
          ),
        )
        nextProjection = mergeReviewedRelations(nextProjection, relations.relations)
        const relatedEntries = await hydrateEntries({
          releaseId: activeReleaseId,
          projection: nextProjection,
          knowledgeIds: endpointIds(relations.relations),
        })
        nextProjection = mergeGraphEntries(nextProjection, relatedEntries)

        if (request !== centerRequest.current) return
        setProjection(nextProjection)
        setFocus(nextFocus)
        setSearchResultsOpen(false)
        setStructureCursors({
          children: children.nextCursor,
          siblings: siblings.nextCursor,
        })
        setRelationCursor(relations.nextCursor)
        setRelationTotal(relations.totalCount)
        setCandidateCursor(undefined)
        setCandidateTotal(0)
        setDirectoryCursor(undefined)
      } catch (nextError) {
        if (request === centerRequest.current) setError(message(nextError))
      } finally {
        if (request === centerRequest.current) setLoadingCenter(false)
      }
    }

    void loadCenter()
  }, [activeReleaseId, centerId])

  useEffect(() => {
    if (!pendingEnabled) {
      setProjection((current) => removeCandidateLayer(current, focus?.knowledgeId))
      setCandidateCursor(undefined)
      setCandidateTotal(0)
      return
    }
    if (!activeReleaseId || !focus) return
    const requestCenterId = focus.knowledgeId
    setError('')
    void readIncidentCandidatePage({
      releaseId: activeReleaseId,
      knowledgeId: requestCenterId,
    }).then(async (page) => {
      const entries = await hydrateEntries({
        releaseId: activeReleaseId,
        projection: projectionRef.current,
        knowledgeIds: endpointIds(page.candidates),
      })
      if (activeCenter.current !== requestCenterId) return
      setProjection((current) => mergeRelationCandidates(
        mergeGraphEntries(current, entries),
        page.candidates,
        endpointTitles(current, entries),
      ))
      setCandidateCursor(page.nextCursor)
      setCandidateTotal(page.totalCount)
    }).catch((nextError) => setError(message(nextError)))
  }, [activeReleaseId, focus, pendingEnabled])

  async function loadMoreStructure(layer: StructureLayer) {
    if (!focus) return
    const cursor = structureCursors[layer]
    if (!cursor) return
    const sourceNodeId = layer === 'children'
      ? focus.knowledgeId
      : focus.directoryPath.at(-1)?.nodeId
    if (!sourceNodeId) return
    const page = await readStructuralConnectionPage({
      releaseId: activeReleaseId,
      sourceNodeId,
      cursor,
    })
    if (activeCenter.current !== focus.knowledgeId) return
    setProjection((current) => mergeStructuralConnections(current, page.connections))
    setStructureCursors((current) => ({ ...current, [layer]: page.nextCursor }))
  }

  async function expandDirectory(nodeId: string, cursor?: string) {
    setError('')
    const requestCenterId = activeCenter.current
    try {
      const page = await readStructuralConnectionPage({
        releaseId: activeReleaseId,
        sourceNodeId: nodeId,
        ...(cursor ? { cursor } : {}),
      })
      if (activeCenter.current !== requestCenterId) return
      setProjection((current) => mergeStructuralConnections(current, page.connections))
      setDirectoryCursor(page.nextCursor
        ? { nodeId, cursor: page.nextCursor }
        : undefined)
    } catch (nextError) {
      setError(message(nextError))
    }
  }

  async function loadMoreRelations() {
    if (!focus || !relationCursor) return
    const requestCenterId = focus.knowledgeId
    const page = await readIncidentRelationPage({
      releaseId: activeReleaseId,
      knowledgeId: requestCenterId,
      cursor: relationCursor,
    })
    const entries = await hydrateEntries({
      releaseId: activeReleaseId,
      projection,
      knowledgeIds: endpointIds(page.relations),
    })
    if (activeCenter.current !== requestCenterId) return
    setProjection((current) => mergeGraphEntries(
      mergeReviewedRelations(current, page.relations),
      entries,
    ))
    setRelationCursor(page.nextCursor)
    setRelationTotal(page.totalCount)
  }

  async function loadMoreCandidates() {
    if (!focus || !candidateCursor) return
    const requestCenterId = focus.knowledgeId
    const page = await readIncidentCandidatePage({
      releaseId: activeReleaseId,
      knowledgeId: requestCenterId,
      cursor: candidateCursor,
    })
    const entries = await hydrateEntries({
      releaseId: activeReleaseId,
      projection,
      knowledgeIds: endpointIds(page.candidates),
    })
    if (activeCenter.current !== requestCenterId) return
    setProjection((current) => mergeRelationCandidates(
      mergeGraphEntries(current, entries),
      page.candidates,
      endpointTitles(current, entries),
    ))
    setCandidateCursor(page.nextCursor)
    setCandidateTotal(page.totalCount)
  }

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const nextQuery = queryInput.trim()
    if (!nextQuery) {
      onStateChange({ query: undefined })
      return
    }
    if (nextQuery === query) void runSearch(nextQuery)
    else onStateChange({ query: nextQuery })
  }

  function selectCenter(knowledgeId: string) {
    onStateChange({ centerId: knowledgeId })
  }

  const selectedEdge = useMemo(
    () => projection.edges.find((edge) => edge.id === selectedEdgeId),
    [projection.edges, selectedEdgeId],
  )
  const reviewedCount = projection.edges.filter((edge) => edge.layer === 'reviewed').length
  const pendingCount = projection.edges.filter((edge) => edge.layer === 'candidate').length

  return (
    <section className="knowledge-graph-page" aria-label="全屏知识图谱工作台">
      <div className="knowledge-graph-page__canvas">
        <ObsidianKnowledgeGraph
          projection={projection}
          focusNodeId={focus?.knowledgeId}
          onExpandNode={(nodeId) => void expandDirectory(nodeId)}
          onSelectKnowledge={selectCenter}
          onSelectEdge={setSelectedEdgeId}
        />
      </div>

      <aside className="knowledge-graph-page__sidebar" aria-label="知识图谱互动栏">
        <h1 className="knowledge-graph-page__title">知识图谱</h1>
        <form className="knowledge-graph-page__search" onSubmit={submitSearch}>
          <label className="knowledge-graph-page__visually-hidden" htmlFor="graph-entry-search">
            搜索真实条目
          </label>
          <div>
            <MagnifyingGlassIcon size={15} aria-hidden="true" />
            <input
              id="graph-entry-search"
              type="search"
              value={queryInput}
              onChange={(event) => setQueryInput(event.target.value)}
              placeholder="搜索理论、概念或方法"
            />
            <button
              type="submit"
              aria-label="搜索"
              disabled={!queryInput.trim() || searching}
            >
              →
            </button>
          </div>
        </form>
        {searchResultsOpen && searchResults.length > 0 ? (
          <section className="knowledge-graph-page__results" aria-label="条目搜索结果">
            <ul>
              {searchResults.map((entry) => (
                <li key={entry.knowledgeId}>
                  <button type="button" onClick={() => selectCenter(entry.knowledgeId)}>
                    <strong>{entry.title}</strong>
                    <span>{entry.directoryPath.map((node) => node.title).join(' / ')}</span>
                  </button>
                </li>
              ))}
            </ul>
            {searchCursor ? (
              <button type="button" onClick={() => void runSearch(query, searchCursor)}>
                加载更多搜索结果
              </button>
            ) : null}
          </section>
        ) : searchResultsOpen && searchComplete && !searching
          ? <p>没有找到匹配的真实条目。</p>
          : null}

        {error ? <p className="knowledge-graph-page__error" role="alert">{error}</p> : null}
        {loadingCenter ? <p role="status">正在构造局部网络……</p> : null}

        {focus ? (
          <section className="knowledge-graph-page__focus" aria-label="当前中心">
            <p>当前中心</p>
            <h2>{focus.title}</h2>
            <p>{focus.directoryPath.map((node) => node.title).join(' / ')}</p>
            <small>{focus.knowledgeId}</small>
            <a href={entryHref(focus.knowledgeId)}>
              查看完整条目
            </a>
          </section>
        ) : null}

        <section className="knowledge-graph-page__legend" aria-label="图例与图层">
          <header>
            <h2>关系</h2>
            <span>{projection.edges.length}</span>
          </header>
          <p><i className="legend-line legend-line--structure" />目录结构</p>
          <p><i className="legend-line legend-line--reviewed" />正式关系 <span>{reviewedCount}</span></p>
          <p><i className="legend-line legend-line--pending" />候选关系 <span>{pendingCount}</span></p>
          <button
            type="button"
            disabled={!focus}
            aria-pressed={pendingEnabled}
            onClick={() => onStateChange({
              pendingEnabled: pendingEnabled ? undefined : true,
            })}
          >
            {pendingEnabled ? '隐藏候选关系' : '显示候选关系'}
          </button>
          {pendingEnabled ? <p className="knowledge-graph-page__pending-note">候选关系不是正式知识，不会计入知识关系数量。</p> : null}
        </section>

        {focus || directoryCursor ? (
          <section className="knowledge-graph-page__pagination" aria-label="局部网络分页">
            {directoryCursor ? (
              <button
                type="button"
                onClick={() => void expandDirectory(directoryCursor.nodeId, directoryCursor.cursor)}
              >
                加载更多目录节点
              </button>
            ) : null}
            {structureCursors.children ? (
              <button type="button" onClick={() => void loadMoreStructure('children')}>
                加载更多直接子级
              </button>
            ) : null}
            {structureCursors.siblings ? (
              <button type="button" onClick={() => void loadMoreStructure('siblings')}>
                加载更多同父条目
              </button>
            ) : null}
            {relationCursor ? (
              <button type="button" onClick={() => void loadMoreRelations()}>
                加载更多正式关系
              </button>
            ) : relationTotal === 0 ? <p>当前中心没有知识关系。</p> : null}
            {pendingEnabled && candidateCursor ? (
              <button type="button" onClick={() => void loadMoreCandidates()}>
                加载更多候选关系
              </button>
            ) : null}
            {pendingEnabled && candidateTotal === 0 ? <p>当前中心没有候选关系。</p> : null}
          </section>
        ) : null}

        {selectedEdge ? <EdgeEvidence edge={selectedEdge} /> : null}
      </aside>
    </section>
  )
}

function EdgeEvidence({ edge }: { edge: KnowledgeGraphEdge }) {
  if (edge.layer === 'structure') {
    return (
      <section className="knowledge-graph-page__evidence" aria-label="知识结构说明">
        <p>structure · 知识库结构</p>
        <h2>结构连接</h2>
        <p>仅表达目录与层级结构，不是正式语义关系。</p>
        <small>{edge.relationType}</small>
      </section>
    )
  }
  if (edge.layer === 'candidate') {
    return (
      <section className="knowledge-graph-page__evidence" aria-label="候选关系证据">
        <p>candidate · 候选关系、非正式知识</p>
        <h2>{edge.relationType}</h2>
        <blockquote>{edge.evidenceExcerpt}</blockquote>
        <dl>
          <dt>证据位置</dt><dd>{edge.evidenceLocator}</dd>
          <dt>触发说明</dt><dd>{edge.triggerReason}</dd>
          <dt>规则分数</dt>
          <dd>{edge.score === 1
            ? '1.0：确定性规则命中，不是校准置信度。'
            : (edge.score ?? '未提供')}</dd>
        </dl>
      </section>
    )
  }
  return (
    <section className="knowledge-graph-page__evidence" aria-label="正式关系证据">
      <p>relation · 正式知识关系</p>
      <h2>{edge.relationType}</h2>
      <p>{edge.description}</p>
      <small>{edge.evidenceSourceIds?.join('、') || '未提供证据来源 ID'}</small>
    </section>
  )
}
