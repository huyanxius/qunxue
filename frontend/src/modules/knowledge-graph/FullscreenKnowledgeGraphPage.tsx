import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ArrowLeftIcon, ArrowUpRightIcon, MagnifyingGlassIcon, XIcon } from '@phosphor-icons/react'
import { ExplorationCanvas } from './ExplorationCanvas'
import { mergeDirectoryPath, mergeGraphEntries, mergeReviewedRelations, mergeStructuralConnections, mergeRelationCandidates } from './knowledgeGraphAdapter'
import { readCurrentKnowledgeGraphRelease, readKnowledgeGraphFocusEntry, readStructuralConnectionPage, readIncidentRelationPage, readIncidentCandidatePage, searchKnowledgeGraphEntries } from './knowledgeGraphApi'
import type { KnowledgeGraphEdge, KnowledgeGraphFocusEntry, KnowledgeGraphProjection } from './types'
import './FullscreenKnowledgeGraph.css'

const dimensions = [['D1', '本体论'], ['D2', '实践论'], ['D3', '方法论'], ['D4', '价值论'], ['D5', '认识论'], ['D6', '学派传统'], ['D7', '学科史']] as const
export interface FullscreenKnowledgeGraphState {
  readonly releaseId?: string
  readonly query?: string
  readonly centerId?: string
  readonly pendingEnabled?: boolean
}
interface Props {
  readonly state: FullscreenKnowledgeGraphState
  readonly onStateChange: (changes: Partial<FullscreenKnowledgeGraphState>) => void
  readonly renderEntryLink: (knowledgeId: string, label: ReactNode) => ReactNode
}
type Cursors = Record<string, string | null>
type ExplorationSnapshot = { graph: KnowledgeGraphProjection; cursors: Cursors }
const sessions = new Map<string, ExplorationSnapshot & { selectedId?: string; history: ExplorationSnapshot[] }>()
const initial = (releaseId: string): KnowledgeGraphProjection => ({ releaseId,
  nodes: dimensions.map(([id, label]) => ({ id, label, nodeType: 'dimension' })), edges: [] })
const empty = (releaseId: string): KnowledgeGraphProjection => ({ releaseId, nodes: [], edges: [] })
const errorText = (error: unknown) => error instanceof Error ? error.message : '加载失败，请重试。'
const shortTitle = (title: string) => title.replace(/（[^）]*）|\([^)]*\)/g, '').replace(/^(?:[IVXLCDM]+\.|\d+\.|[A-Z]\d+)\s*/, '').trim()
function excerpt(content?: string) {
  return content?.split('\n').filter((line) => line.trim() && !/^(?:\s*[#>|]|\s*<!--)/.test(line))
    .slice(0, 2).join(' ').replace(/\*\*/g, '').slice(0, 360)
}
function unique(projection: KnowledgeGraphProjection) {
  const seen = new Set<string>()
  return { ...projection, edges: projection.edges.filter((edge) => {
    const key = edge.layer === 'structure' ? `${edge.source}|${edge.target}|${edge.relationType}` : edge.id
    if (seen.has(key)) return false
    seen.add(key); return true
  }) }
}
function withoutCandidates(projection: KnowledgeGraphProjection, keep: readonly string[] = []) {
  const edges = projection.edges.filter((edge) => edge.layer !== 'candidate')
  const candidateIds = new Set(projection.edges.filter((edge) => edge.layer === 'candidate').flatMap((edge) => [edge.source, edge.target]))
  const retained = new Set([...keep, ...edges.flatMap((edge) => [edge.source, edge.target])])
  return { ...projection, edges, nodes: projection.nodes.filter((node) => !candidateIds.has(node.id) || retained.has(node.id)) }
}

export function FullscreenKnowledgeGraphPage({ state, onStateChange, renderEntryLink }: Props) {
  const releaseId = state.releaseId ?? ''
  const [projection, setProjection] = useState(initial(releaseId))
  const [selectedId, setSelectedId] = useState<string | undefined>(state.centerId)
  const [detail, setDetail] = useState<KnowledgeGraphFocusEntry>()
  const [selectedEdgeId, setSelectedEdgeId] = useState<string>()
  const [queryInput, setQueryInput] = useState(state.query ?? '')
  const [results, setResults] = useState<readonly KnowledgeGraphFocusEntry[]>([])
  const [resultsOpen, setResultsOpen] = useState(false)
  const submittedSearch = useRef(false)
  const [searchCursor, setSearchCursor] = useState<string>()
  const [searching, setSearching] = useState(false)
  const [busy, setBusy] = useState(false)
  const [viewRevision, setViewRevision] = useState(0)
  const [reload, setReload] = useState(0)
  const [reading, setReading] = useState(false)
  const [candidateCursor, setCandidateCursor] = useState<string>()
  const [candidateBusy, setCandidateBusy] = useState(false)
  const candidateGeneration = useRef(0)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [cursors, setCursors] = useState<Cursors>({})
  const [history, setHistory] = useState<{ graph: KnowledgeGraphProjection; cursors: Cursors }[]>([])
  const sessionKey = `${releaseId}:${state.centerId ?? 'overview'}`
  const snapshotRef = useRef({ graph: projection, cursors, selectedId, history })
  snapshotRef.current = { graph: projection, cursors, selectedId, history }
  const ready = useRef(false)
  const generation = useRef(0)
  const searchGeneration = useRef(0)
  const cache = useRef(new Map<string, Promise<KnowledgeGraphFocusEntry>>())
  const callbacks = useRef(onStateChange)
  callbacks.current = onStateChange
  const selected = projection.nodes.find((node) => node.id === selectedId)
  const edge = projection.edges.find((item) => item.id === selectedEdgeId)
  const isEntry = selected && (selected.nodeType ?? 'entry') === 'entry'
  const currentDetail = detail?.knowledgeId === selectedId ? detail : undefined

  function readEntry(id: string) {
    const key = `${releaseId}:${id}`
    let result = cache.current.get(key)
    if (!result) {
      result = readKnowledgeGraphFocusEntry({ releaseId, knowledgeId: id })
      cache.current.set(key, result)
      void result.catch(() => cache.current.delete(key))
    }
    return result
  }
  async function hydrate(graph: KnowledgeGraphProjection) {
    const ids = graph.nodes.filter((node) => node.label === node.id && (node.nodeType ?? 'entry') === 'entry').map((node) => node.id)
    return mergeGraphEntries(graph, await Promise.all(ids.map(readEntry)))
  }
  async function network(id: string, base: KnowledgeGraphProjection, cursor?: string) {
    const focus = await readEntry(id)
    const relations = await readIncidentRelationPage({ releaseId, knowledgeId: id, cursor })
    let graph = mergeReviewedRelations(mergeGraphEntries(base, [focus]), relations.relations)
    if (!cursor) {
      graph = mergeDirectoryPath(graph, focus)
      const parent = focus.directoryPath.at(-1)?.nodeId
      if (parent) {
        const siblings = await readStructuralConnectionPage({ releaseId, sourceNodeId: parent })
        graph = mergeStructuralConnections(graph, siblings.connections)
        return { graph: unique(await hydrate(graph)), next: relations.nextCursor ?? null,
          directory: { [parent]: siblings.nextCursor ?? null } }
      }
    }
    return { graph: unique(await hydrate(graph)), next: relations.nextCursor ?? null, directory: {} }
  }

  useEffect(() => {
    if (releaseId) return
    let cancelled = false
    void readCurrentKnowledgeGraphRelease().then((id) => {
      if (!cancelled) callbacks.current({ releaseId: id })
    }).catch((error) => { if (!cancelled) setError(errorText(error)) })
    return () => { cancelled = true }
  }, [releaseId])

  useEffect(() => () => {
    if (!releaseId || !ready.current) return
    sessions.set(sessionKey, snapshotRef.current)
    if (sessions.size > 8) sessions.delete(sessions.keys().next().value!)
  }, [sessionKey, releaseId])

  useEffect(() => {
    const request = ++generation.current
    ready.current = false
    setHistory([]); setCursors({}); setDetail(undefined); setSelectedEdgeId(undefined); setNotice(''); setError('')
    setSelectedId(state.centerId)
    setProjection(initial(releaseId))
    if (!releaseId) return
    const saved = sessions.get(sessionKey)
    if (saved && !reload && (!state.centerId || saved.graph.nodes.some((node) => node.id === state.centerId))) {
      snapshotRef.current = { ...saved, selectedId: saved.selectedId }
      ready.current = true
      setProjection(saved.graph); setCursors(saved.cursors); setHistory(saved.history)
      setSelectedId(saved.selectedId); setBusy(false); setViewRevision((old) => old + 1)
      return
    }
    setBusy(true)
    const job = state.centerId ? network(state.centerId, empty(releaseId)) :
      readStructuralConnectionPage({ releaseId, sourceNodeId: 'D1' }).then((page) => ({
        graph: unique(mergeStructuralConnections(initial(releaseId), page.connections)), next: null,
        directory: { D1: page.nextCursor ?? null },
      }))
    void job.then((next) => {
      if (request !== generation.current) return
      snapshotRef.current = { graph: next.graph,
        cursors: { ...next.directory, ...(state.centerId ? { [`relation:${state.centerId}`]: next.next } : {}) },
        selectedId: state.centerId, history: [] }
      ready.current = true
      setProjection(next.graph)
      setViewRevision((old) => old + 1)
      setResultsOpen(false)
      setCursors({ ...next.directory, ...(state.centerId ? { [`relation:${state.centerId}`]: next.next } : {}) })
    }).catch((error) => { if (request === generation.current) setError(errorText(error)) })
      .finally(() => { if (request === generation.current) setBusy(false) })
    return () => { generation.current++ }
    // A new center deliberately resets the network; selection never does.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [releaseId, state.centerId, reload])

  useEffect(() => {
    let cancelled = false
    setDetail(undefined)
    if (!selectedId || !isEntry) { setReading(false); return }
    setReading(true)
    void readEntry(selectedId).then((entry) => { if (!cancelled) setDetail(entry) })
      .catch((error) => { if (!cancelled) setError(errorText(error)) })
      .finally(() => { if (!cancelled) setReading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [releaseId, selectedId, isEntry])

  async function search(query: string, cursor?: string, open = true) {
    const request = ++searchGeneration.current
    if (!query.trim() || !releaseId) { setResultsOpen(false); return }
    setSearching(true); setResultsOpen(open); setError('')
    if (!cursor) setResults([])
    try {
      const page = await searchKnowledgeGraphEntries({ releaseId, query, cursor })
      if (request !== searchGeneration.current) return
      setResults((old) => cursor ? [...old, ...page.entries] : page.entries)
      setSearchCursor(page.nextCursor)
    } catch (error) { if (request === searchGeneration.current) setError(errorText(error)) }
    finally { if (request === searchGeneration.current) setSearching(false) }
  }
  useEffect(() => {
    setQueryInput(state.query ?? '')
    void search(state.query ?? '', undefined, submittedSearch.current || !state.centerId)
    submittedSearch.current = false
    return () => { searchGeneration.current++ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [releaseId, state.query])

  async function expand() {
    if (!selected || busy) return
    const request = generation.current
    setBusy(true); setError(''); setNotice('')
    const snapshot = { graph: projection, cursors }
    try {
      let graph: KnowledgeGraphProjection
      let nextCursors: Cursors
      if (isEntry) {
        const next = await network(selected.id, projection, cursors[`relation:${selected.id}`] ?? undefined)
        graph = next.graph
        nextCursors = { ...cursors, ...next.directory, [`relation:${selected.id}`]: next.next }
      } else {
        const page = await readStructuralConnectionPage({ releaseId, sourceNodeId: selected.id, cursor: cursors[selected.id] ?? undefined })
        graph = unique(mergeStructuralConnections(projection, page.connections))
        nextCursors = { ...cursors, [selected.id]: page.nextCursor ?? null }
      }
      if (request !== generation.current) return
      setHistory((old) => [...old, snapshot]); setProjection(graph); setCursors(nextCursors)
      setNotice(graph.nodes.length === projection.nodes.length ? '已显示当前可用的连接。' : `已展开 ${graph.nodes.length - projection.nodes.length} 个节点`)
    } catch (error) { if (request === generation.current) setError(errorText(error)) }
    finally { if (request === generation.current) setBusy(false) }
  }

  async function loadCandidates(cursor?: string) {
    if (!selectedId || !isEntry || !state.pendingEnabled) return
    const request = ++candidateGeneration.current
    const networkGeneration = generation.current
    setCandidateBusy(true)
    try {
      const page = await readIncidentCandidatePage({ releaseId, knowledgeId: selectedId, cursor })
      const ids = [...new Set(page.candidates.flatMap((item) => [item.source_knowledge_id, item.target_knowledge_id]))]
      const entries = await Promise.all(ids.map(readEntry))
      if (request !== candidateGeneration.current || networkGeneration !== generation.current) return
      setProjection((graph) => mergeRelationCandidates(mergeGraphEntries(cursor ? graph : withoutCandidates(graph, [selectedId, state.centerId ?? '']), entries), page.candidates,
        new Map(entries.map((entry) => [entry.knowledgeId, entry.title]))))
      setCandidateCursor(page.nextCursor)
      setNotice(page.totalCount === 0 ? '当前概念没有候选关系。' : '虚线表示尚未确认的候选关系。')
    } catch (error) { if (request === candidateGeneration.current) setError(errorText(error)) }
    finally { if (request === candidateGeneration.current) setCandidateBusy(false) }
  }
  useEffect(() => {
    candidateGeneration.current++
    setCandidateCursor(undefined); setCandidateBusy(false)
    setProjection((graph) => withoutCandidates(graph, [selectedId ?? '', state.centerId ?? '']))
    void loadCandidates()
    return () => { candidateGeneration.current++ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [releaseId, selectedId, isEntry, state.pendingEnabled])

  function select(id: string) { setSelectedId(id); setSelectedEdgeId(undefined); setResultsOpen(false); setNotice('') }
  function reset() { sessions.delete(`${releaseId}:overview`); if (!state.centerId) setReload((old) => old + 1); callbacks.current({ centerId: undefined, query: undefined, pendingEnabled: undefined }); setSelectedId(undefined) }
  const related = projection.edges.filter((item) => item.source === selectedId || item.target === selectedId)
  const neighbors = [...new Set(related.map((item) => item.source === selectedId ? item.target : item.source))]
  const relationCount = projection.edges.filter((item) => item.layer === 'reviewed').length
  const structureCount = projection.edges.filter((item) => item.layer === 'structure').length
  const candidateCount = projection.edges.filter((item) => item.layer === 'candidate').length
  const expansionKey = selected ? isEntry ? `relation:${selected.id}` : selected.id : ''
  return <section className="knowledge-graph-page" aria-label="全屏知识图谱工作台">
    <header className="graph-header">
      <div className="graph-header__identity"><button onClick={reset} aria-label="返回图谱总览"><ArrowLeftIcon /></button><h1>知识图谱</h1></div>
      <form className="graph-search" onSubmit={(event) => { event.preventDefault(); submittedSearch.current = true; const query = queryInput.trim();
        if (query === state.query) void search(query); else callbacks.current({ query: query || undefined }) }}>
        <MagnifyingGlassIcon aria-hidden="true" /><input aria-label="搜索理论、概念或方法" type="search" value={queryInput}
          onChange={(event) => setQueryInput(event.target.value)} onFocus={() => { if (results.length) setResultsOpen(true) }} placeholder="搜索理论、概念或方法" />
        <button type="submit" disabled={searching || !queryInput.trim()} aria-label="搜索">↵</button>
        {resultsOpen && <section className="graph-search__results" aria-label="条目搜索结果">
          <header><span>{searching ? '正在搜索…' : `找到 ${results.length}${searchCursor ? '+' : ''} 个条目`}</span><button type="button" aria-label="关闭搜索结果" onClick={() => setResultsOpen(false)}><XIcon /></button></header>
          {!searching && !results.length && <p>没有匹配条目，试试更短的概念名称。</p>}
          {results.map((entry) => <button type="button" key={entry.knowledgeId} onClick={() => {
            setResultsOpen(false); searchGeneration.current++; callbacks.current({ centerId: entry.knowledgeId }); select(entry.knowledgeId)
          }}><strong>{entry.title}</strong><span>{entry.directoryPath.slice(0, 3).map((item) => shortTitle(item.title)).join(' / ')}</span></button>)}
          {searchCursor && <button type="button" disabled={searching} onClick={() => void search(state.query ?? '', searchCursor)}>加载更多结果</button>}
        </section>}
      </form>
    </header>
    <nav className="graph-dimensions" aria-label="知识维度">{dimensions.map(([id, label]) => <button key={id}
      aria-pressed={selectedId === id} onClick={() => { if (!projection.nodes.some((node) => node.id === id)) setProjection((old) => ({ ...old, nodes: [...old.nodes, { id, label, nodeType: 'dimension' }] })); select(id) }}>{label}</button>)}
      {history.length > 0 && <button className="graph-undo" disabled={busy} onClick={() => {
        const previous = history.at(-1)!
        setProjection(previous.graph); setCursors(previous.cursors); setHistory((old) => old.slice(0, -1)); setNotice('已撤回上次展开。')
        if (!previous.graph.nodes.some((node) => node.id === selectedId)) setSelectedId(state.centerId)
      }}>撤回上次展开</button>}
    </nav>
    <div className={`graph-body${selected || edge ? ' graph-body--inspecting' : ''}`}>
      <div className="graph-stage"><ExplorationCanvas sessionKey={sessionKey} resetKey={viewRevision} projection={projection} selectedId={selectedId} centerId={state.centerId} onSelect={select} onEdge={setSelectedEdgeId} />
        {!selected && !edge && <div className="graph-welcome"><span>从一个概念开始</span><p>搜索感兴趣的概念，或选择一个维度展开目录。</p></div>}
        <div className="graph-feedback" aria-live="polite">{busy ? '正在加载连接…' : notice}</div>
      </div>
      {(selected || edge) && <aside className="graph-inspector" aria-label="节点详情">
        <div className="graph-inspector__top"><span>{edge ? '连接依据' : isEntry ? '知识条目' : '目录导航'}</span><button aria-label="关闭详情" onClick={() => { setSelectedId(undefined); setSelectedEdgeId(undefined) }}><XIcon /></button></div>
        {edge ? <EdgeEvidence edge={edge} projection={projection} sources={currentDetail?.sources} renderEntryLink={renderEntryLink} /> : selected && <>
          <h2>{shortTitle(selected.label)}</h2>
          {currentDetail?.directoryPath.length ? <p className="graph-breadcrumb">{currentDetail.directoryPath.map((item) => shortTitle(item.title)).join(' / ')}</p> : null}
          {reading && <p role="status">正在读取条目…</p>}
          {currentDetail && <><p className="graph-excerpt">{excerpt(currentDetail.content) || '打开完整条目，查看原文和文献依据。'}</p>{renderEntryLink(selected.id, <>阅读全文与来源 <ArrowUpRightIcon /></>)}</>}
          {!isEntry && <p className="graph-excerpt">展开此目录，查看其中的知识条目。目录包含表示分类，不表示概念之间的学术关系。</p>}
          <div className="graph-actions"><button disabled={busy || cursors[expansionKey] === null} onClick={() => void expand()}>{isEntry ? cursors[expansionKey] ? '继续展开关联' : '展开关联' : cursors[expansionKey] ? '继续展开目录' : '展开目录'}</button>
            {isEntry && <button disabled={busy || state.centerId === selected.id} onClick={() => callbacks.current({ centerId: selected.id })}>以此为中心</button>}</div>
          {isEntry && <label className="graph-candidate-toggle"><input type="checkbox" checked={state.pendingEnabled ?? false} onChange={(event) => callbacks.current({ pendingEnabled: event.target.checked })} />查看当前概念的候选关系</label>}
          {state.pendingEnabled && <p className="graph-note">候选关系尚未确认，不计入正式知识关系。</p>}
          {candidateBusy && <p role="status">正在读取候选关系…</p>}
          {state.pendingEnabled && candidateCursor && <button disabled={candidateBusy} onClick={() => void loadCandidates(candidateCursor)}>加载更多候选关系</button>}
          <section className="graph-neighbors"><h3>相邻节点 <span>{neighbors.length}</span></h3>
            {isEntry && related.every((item) => item.layer === 'structure') && <p className="graph-note">已显示的连接均为目录结构。{cursors[expansionKey] === null ? '当前条目没有正式知识关系。' : '可展开关联查询知识关系。'}</p>}
            {neighbors.map((id) => { const node = projection.nodes.find((item) => item.id === id); const connection = related.find((item) => item.source === id || item.target === id)!; return <div className="graph-neighbor" key={id}><button onClick={() => select(id)}>{shortTitle(node?.label ?? id)}</button><button className="graph-neighbor__relation" onClick={() => setSelectedEdgeId(connection.id)}>{connection.layer === 'structure' ? '目录连接' : connection.layer === 'candidate' ? '候选关系' : connection.relationType} ↗</button></div> })}
          </section>
          {currentDetail?.sources?.length ? <section className="graph-sources"><h3>条目来源</h3>{currentDetail.sources.map((source) => <p key={source.sourceId}><strong>{source.title}</strong><span>{source.locator}</span><small>{source.status === 'verified' ? '已核验' : source.status === 'system_summary' ? '系统整理' : '待核验'}</small></p>)}</section> : null}
        </>}
      </aside>}
    </div>
    {error && <div className="graph-error" role="alert">{error}<button onClick={() => { setError(''); setReload((old) => old + 1) }}>重试</button></div>}
    <footer className="graph-footer"><div aria-label="网络统计"><span>{projection.nodes.length} 个节点</span><span><i />知识关系 {relationCount}</span><span><i className="is-directory" />目录连接 {structureCount}</span>{candidateCount > 0 && <span><i className="is-candidate" />候选关系 {candidateCount}</span>}</div><span>单击查看 · 拖动调整 · 滚轮缩放</span></footer>
  </section>
}
function EdgeEvidence({ edge, projection, sources, renderEntryLink }: {
  edge: KnowledgeGraphEdge; projection: KnowledgeGraphProjection
  sources: KnowledgeGraphFocusEntry['sources']; renderEntryLink: Props['renderEntryLink']
}) {
  const title = (id: string) => shortTitle(projection.nodes.find((node) => node.id === id)?.label ?? id)
  return <section className="graph-evidence"><h2>{title(edge.source)}</h2><p className="graph-evidence__relation">{edge.layer === 'structure' ? '目录包含' : edge.relationType} →</p><h2>{title(edge.target)}</h2>
    {edge.layer === 'structure' ? <p>这是知识库目录的层级连接，不是正式学术关系。</p> : <>
      <p>{edge.layer === 'candidate' ? '候选关系 · 尚未确认' : '正式知识关系'}</p><p>{edge.description || edge.triggerReason}</p>
      {edge.evidenceExcerpt && <blockquote>{edge.evidenceExcerpt}</blockquote>}{edge.evidenceLocator && <p>{edge.evidenceLocator}</p>}
      {edge.evidenceSourceIds?.map((id) => <p key={id}>{sources?.find((source) => source.sourceId === id)?.title ?? '来源见对应条目'}</p>)}
      {renderEntryLink(edge.source, <>查看起点条目与来源 <ArrowUpRightIcon /></>)}
      {renderEntryLink(edge.target, <>查看终点条目与来源 <ArrowUpRightIcon /></>)}
    </>}
  </section>
}
