import { copyCourseText } from './copyCourseText'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { CopyIcon, InfoIcon, ListBulletsIcon, MagnifyingGlassIcon, SidebarSimpleIcon, XIcon } from '@phosphor-icons/react'
import type { SharedSource } from '../../modules/shared-knowledge'
import { DocumentWorkspace, DocumentWorkspaceToolbar, DocumentOutline, DocumentSearch, DocumentSourceView, DocumentSourceSegment, formatMaterialLocator, formatMaterialSize, type ResearchMaterialSegment } from '../../modules/research-materials'
import '../../modules/research-materials/research-materials.css'

const PAGE_SIZE = 24

/** Course reading shares the source layout; knowledge and learning replace the coding tools. */
export function ReadOnlyMaterialReader({ source, selectedSegmentId, onBack, navigation, agentPanel }: {
  source: SharedSource; selectedSegmentId?: string | null; navigation?: ReactNode; onBack: () => void; agentPanel?: ReactNode
}) {
  const segments = useMemo<ResearchMaterialSegment[]>(() => source.segments.map((item) => ({ segmentId: item.id, materialId: source.document.id, parseId: item.parseId, ordinal: item.ordinal, kind: item.kind, text: item.text, locator: item.location })), [source.segments, source.document.id])
  const headings = useMemo(() => {
    const pages = new Set<number>()
    return segments.filter((item) => {
      if (item.kind === 'heading') return true
      if (item.locator.page !== null && !pages.has(item.locator.page)) { pages.add(item.locator.page); return true }
      return false
    }).map((segment) => ({ segment, label: segment.locator.headingPath.at(-1) ?? formatMaterialLocator(segment.locator) }))
  }, [segments])
  const [query, setQuery] = useState('')
  const [outlineOpen, setOutlineOpen] = useState(() => headings.length > 0)
  const [searchOpen, setSearchOpen] = useState(false)
  const [selected, setSelected] = useState(selectedSegmentId ?? null)
  const [page, setPage] = useState(() => Math.floor(Math.max(0, segments.findIndex((s) => s.segmentId === selectedSegmentId)) / PAGE_SIZE))
  const [panel, setPanel] = useState<'source' | 'knowledge' | 'agent'>('source')
  const [panelOpen, setPanelOpen] = useState(true)
  const [zoom, setZoom] = useState(100)
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState(false)
  const nodes = useRef(new Map<string, HTMLElement>())
  const scrollRef = useRef<HTMLElement>(null)
  const pendingScroll = useRef<string | null>(selectedSegmentId ?? null)
  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase()
    return needle ? segments.filter((item) => `${item.text} ${formatMaterialLocator(item.locator)}`.toLocaleLowerCase().includes(needle)) : segments
  }, [segments, query])
  const pageCount = Math.max(1, Math.ceil(visible.length / PAGE_SIZE))
  const activePage = Math.min(page, pageCount - 1)
  const paged = visible.slice(activePage * PAGE_SIZE, (activePage + 1) * PAGE_SIZE)
  const selectedSource = segments.find((item) => item.segmentId === selected)
  function select(segment: ResearchMaterialSegment) {
    setQuery(''); setSelected(segment.segmentId); setCopied(false)
    setPage(Math.floor(segments.findIndex((item) => item.segmentId === segment.segmentId) / PAGE_SIZE))
    pendingScroll.current = segment.segmentId
  }
  useEffect(() => {
    if (!selectedSegmentId) return
    const segment = segments.find((item) => item.segmentId === selectedSegmentId)
    if (segment) { setSelected(segment.segmentId); setPanel('source'); setPanelOpen(true); setQuery(''); setPage(Math.floor(segments.indexOf(segment) / PAGE_SIZE)); pendingScroll.current = segment.segmentId }
  }, [selectedSegmentId, segments])
  useEffect(() => {
    const node = pendingScroll.current ? nodes.current.get(pendingScroll.current) : null
    if (node) { node.scrollIntoView?.({ block: 'center' }); pendingScroll.current = null }
  }, [activePage, selected, query])
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLowerCase() === 'f') { event.preventDefault(); setSearchOpen((value) => !value) }
      if (event.key === 'Escape') { setSearchOpen(false); setQuery('') }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  function changePage(next: number) { setPage(next); scrollRef.current?.scrollTo?.({ top: 0 }) }
  const warnings = source.document.warnings.join(' ')
  return <DocumentWorkspace zoom={zoom} className="is-course-reading">
    <DocumentWorkspaceToolbar>
      {navigation ?? <button className="qx-reader__back" onClick={onBack}>返回课程</button>}
      <div className="qx-reader__tools"><div className="qx-reader__tool-group" aria-label="阅读工具">
        <button type="button" className="qx-icon-button" aria-label={outlineOpen ? '收起章节' : '展开章节'} aria-pressed={outlineOpen} aria-controls="research-materials-outline" onClick={() => setOutlineOpen(!outlineOpen)}><SidebarSimpleIcon size={17} /></button>
        <button type="button" className="qx-icon-button" aria-label="在材料中查找" title="查找（⌘⇧F）" aria-pressed={searchOpen} onClick={() => setSearchOpen(!searchOpen)}><MagnifyingGlassIcon size={17} /></button>
        <button type="button" className="qx-icon-button" aria-label={panelOpen ? '收起学习侧栏' : '展开学习侧栏'} aria-pressed={panelOpen} onClick={() => setPanelOpen(!panelOpen)}><InfoIcon size={17} /></button>
      </div></div>
    </DocumentWorkspaceToolbar>
    <div className="qx-reader__coding-toolbar course-reading-tools">
      <span className="course-reading-tools__meta">{formatMaterialSize(source.document.sizeBytes)} · {segments.length} 段原文</span>
      <span className="course-reading-tools__reference">课程参考资料</span>
      <label className="qx-reader__zoom"><span>缩放</span><select aria-label="阅读缩放" value={zoom} onChange={(e) => setZoom(Number(e.target.value))}>{[90, 100, 110, 125].map((value) => <option value={value} key={value}>{value}%</option>)}</select></label>
    </div>
    {searchOpen ? <DocumentSearch query={query} count={visible.length} total={segments.length} onChange={(value) => { setQuery(value); setPage(0) }} /> : null}
    <div className={`qx-reader__body${outlineOpen ? ' is-outline-open' : ''}${panelOpen ? ' has-inspector' : ' is-course-panel-closed'}`}>
      <aside id="research-materials-outline" className="qx-reader__sidebar" aria-label="材料导航" aria-hidden={!outlineOpen}>
        <div className="qx-reader__sidebar-tabs"><span><ListBulletsIcon size={14} /> 章节</span></div>
        <DocumentOutline headings={headings} selectedId={selected} open={outlineOpen} onSelect={select} />
      </aside>
      <DocumentSourceView scrollRef={scrollRef} railLabel="" empty={!paged.length} query={query} page={activePage} pageCount={pageCount} onPageChange={changePage} note={warnings ? { tone: 'plain', text: warnings } : null}>
        {paged.map((segment) => <DocumentSourceSegment key={segment.segmentId} segment={segment} selected={selected === segment.segmentId} line={segment.locator.lineStart !== null ? String(segment.locator.lineStart) : `¶${segment.locator.paragraph ?? segment.ordinal + 1}`} register={(id, node) => { if (node) nodes.current.set(id, node); else nodes.current.delete(id) }} onSelect={() => { select(segment); setPanel('source') }}>{segment.text}</DocumentSourceSegment>)}
      </DocumentSourceView>
      <aside className="qx-reader__inspector is-integrated" aria-label="课程学习侧栏" hidden={!panelOpen}>
        <div className="qx-reader__panel-tabs" role="tablist" aria-label="课程学习工具">
          {([{ id: 'source', title: '原文依据' }, { id: 'knowledge', title: '知识点' }, ...(agentPanel ? [{ id: 'agent', title: 'Agent' }] : [])] as const).map(({ id, title }) => <button type="button" key={id} role="tab" id={`course-tab-${id}`} aria-controls={`course-panel-${id}`} aria-selected={panel === id} onClick={() => setPanel(id as typeof panel)}>{title}</button>)}
          <button type="button" className="course-reading-panel-close" aria-label="关闭学习侧栏" onClick={() => setPanelOpen(false)}><XIcon size={15} /></button>
        </div>
        <div role="tabpanel" id="course-panel-source" aria-labelledby="course-tab-source" className="qx-reader__panel-content" hidden={panel !== 'source'}>
          {selectedSource ? <div className="qx-evidence-inspector"><header className="qx-inspector__head"><div><strong>原文依据</strong><small>{formatMaterialLocator(selectedSource.locator)}</small></div></header><section className="qx-inspector__quote"><blockquote>{selectedSource.text}</blockquote><button type="button" onClick={() => { setCopyError(false); void copyCourseText(`${source.document.filename}\n${formatMaterialLocator(selectedSource.locator)}\n${selectedSource.text}`).then(() => setCopied(true)).catch(() => setCopyError(true)) }}><CopyIcon size={14} />{copied ? '已复制' : '复制原文与定位'}</button>{copyError ? <p role="alert">复制失败，请手动选择原文复制。</p> : null}</section><section className="qx-inspector__section"><h3>来源文件</h3><p>{source.document.filename}</p><p>{source.knowledgeBaseName}</p></section></div> : <div className="course-reading-panel-empty"><InfoIcon size={23} /><strong>选择一段原文</strong><p>点击正文或行号，查看原文内容与来源定位。</p></div>}
        </div>
        <div role="tabpanel" id="course-panel-knowledge" aria-labelledby="course-tab-knowledge" className="qx-reader__panel-content course-reading-knowledge" hidden={panel !== 'knowledge'}>
          {source.document.knowledge ? <><p>{source.document.knowledge.summary}</p>{source.document.knowledge.topics.map((topic) => <article key={topic.title}><button type="button" onClick={() => { const segment = segments.find((item) => item.segmentId === topic.segmentIds[0]); if (segment) select(segment) }}>{topic.title}</button><p>{topic.summary}</p>{topic.segmentIds.length > 1 ? <div>{topic.segmentIds.map((id, index) => <button key={id} type="button" onClick={() => { const segment = segments.find((item) => item.segmentId === id); if (segment) select(segment) }}>原文 {index + 1}</button>)}</div> : null}</article>)}</> : <p>{source.document.knowledgeStatus === 'failed' ? '知识整理暂未完成，请到课程详情重试。' : '正在整理课程知识点，完成后会显示在这里。'}</p>}
        </div>
        {agentPanel ? <div role="tabpanel" id="course-panel-agent" aria-labelledby="course-tab-agent" className="qx-reader__panel-content qx-reader__agent-panel" hidden={panel !== 'agent'}>{agentPanel}</div> : null}
      </aside>
    </div>
  </DocumentWorkspace>
}
