import { CaretRightIcon, CircleNotchIcon, MagnifyingGlassIcon, WarningCircleIcon, XIcon } from '@phosphor-icons/react'
import type { ReactNode, Ref, MouseEventHandler } from 'react'
import { formatMaterialLocator, type ResearchMaterialSegment } from './researchMaterialsModel'

/** Shared reading surface. Coding and course controllers supply their own tools and evidence panels. */
export function DocumentWorkspace({ children, frameRef, narrow = false, workspace = true, zoom = 100, className = '' }: {
  children: ReactNode; frameRef?: Ref<HTMLElement>; narrow?: boolean; workspace?: boolean; zoom?: number; className?: string
}) {
  return <section className={`qx-reader${narrow ? ' is-narrow' : ''}${workspace ? ' is-workspace-chrome' : ''}${className ? ` ${className}` : ''}`} data-zoom={zoom} aria-label="材料阅读台" ref={frameRef}>{children}</section>
}

export function DocumentWorkspaceToolbar({ children, workspace = true }: { children: ReactNode; workspace?: boolean }) {
  return <header className={`qx-reader__bar${workspace ? ' is-workspace-chrome' : ''}`}>{children}</header>
}

export function DocumentSearch({ query, count, total, onChange }: { query: string; count: number; total: number; onChange: (value: string) => void }) {
  return <div className="qx-reader__search" id="research-materials-reader-search">
    <label className="qx-reader__search-field"><MagnifyingGlassIcon size={15} aria-hidden="true" /><span className="sr-only">在材料中查找</span><input type="search" role="searchbox" aria-label="在材料中查找" value={query} placeholder="查找原文、页码或定位" autoFocus onChange={(event) => onChange(event.target.value)} />{query ? <button type="button" aria-label="清除材料查找" onClick={() => onChange('')}><XIcon size={13} aria-hidden="true" /></button> : null}</label>
    <span className="qx-reader__search-count">{query.trim() ? `${count} 处命中` : `${total} 段原文`}</span>
  </div>
}

export function DocumentOutline({ headings, selectedId, open, onSelect }: {
  headings: readonly { segment: ResearchMaterialSegment; label: string }[]; selectedId: string | null; open: boolean; onSelect: (segment: ResearchMaterialSegment) => void
}) {
  return <nav className="qx-reader__chapter-tree" aria-label="章节导航">
    {headings.length ? headings.map(({ segment, label }) => <button type="button" key={segment.segmentId} className={segment.segmentId === selectedId ? 'is-current' : undefined} title={label} tabIndex={open ? undefined : -1} onClick={() => onSelect(segment)}><span className="qx-tree-caret"><CaretRightIcon size={12} aria-hidden="true" /></span>{label}</button>) : <small>此文件没有可识别的章节，可使用原文查找。</small>}
  </nav>
}

export function DocumentSourceView({ children, scrollRef, loading = false, note = null, error, empty = false, query = '', page = 0, pageCount = 1, onPageChange, railLabel = '编码条' }: {
  children: ReactNode; scrollRef?: Ref<HTMLElement>; loading?: boolean; note?: { tone: 'plain' | 'error'; text: string } | null; error?: ReactNode; empty?: boolean; query?: string; page?: number; pageCount?: number; onPageChange: (page: number) => void; railLabel?: string
}) {
  return <main className="qx-reader__scroll" ref={scrollRef} role="region" aria-label="文档阅读器">
    {loading ? <p className="qx-message" role="status"><CircleNotchIcon className="is-spinning" size={16} aria-hidden="true" />正在读取原文结构</p> : null}
    {note ? <p className={`qx-message${note.tone === 'error' ? ' is-error' : ''}`} role={note.tone === 'error' ? 'alert' : undefined}>{note.tone === 'error' ? <WarningCircleIcon size={15} aria-hidden="true" /> : null}{note.text}</p> : null}
    {error}
    <div className="qx-reader__ruler"><span>{railLabel}</span><span>行</span><span>原文</span></div>
    <article className="qx-reader__doc">{children}{empty && !loading ? <p className="qx-reader__no-results">{query.trim() ? '没有匹配的原文。换个词试试。' : '暂时没有可展示的片段。'}</p> : null}</article>
    {pageCount > 1 ? <footer className="qx-reader__pagination" aria-label="文档分页"><button type="button" aria-label="上一页" disabled={page === 0} onClick={() => onPageChange(Math.max(0, page - 1))}>上一页</button><span>第 {page + 1} / {pageCount} 页</span><button type="button" aria-label="下一页" disabled={page >= pageCount - 1} onClick={() => onPageChange(Math.min(pageCount - 1, page + 1))}>下一页</button></footer> : null}
  </main>
}

export function DocumentSourceSegment({ segment, selected, children, rail, railLabel, line, coded = false, register, onSelect, onPointer, onContextMenu, onTextSelection }: {
  segment: ResearchMaterialSegment; selected: boolean; children: ReactNode; rail?: ReactNode; railLabel?: string; line: string; coded?: boolean; register: (id: string, node: HTMLElement | null) => void; onSelect: () => void; onPointer?: () => void; onContextMenu?: MouseEventHandler<HTMLDivElement>; onTextSelection?: MouseEventHandler<HTMLElement>
}) {
  const heading = segment.kind === 'heading'
  return <div className={`qx-segment${selected ? ' is-selected' : ''}${heading ? ' is-heading' : ''}${coded ? ' is-coded' : ''}`} data-segment-id={segment.segmentId} aria-current={selected ? 'location' : undefined} ref={(node) => register(segment.segmentId, node)} onClick={onPointer ?? onSelect} onContextMenu={onContextMenu}>
    <aside className="qx-segment__rail" aria-label={railLabel}>{rail}</aside>
    <button type="button" className="qx-segment__line" aria-label={`定位到${formatMaterialLocator(segment.locator)}`} title={formatMaterialLocator(segment.locator)} onClick={(event) => { event.stopPropagation(); onSelect() }}>{line}</button>
    <div className="qx-segment__text">{heading ? <h3 onMouseUp={onTextSelection}>{children}</h3> : <p onMouseUp={onTextSelection}>{children}</p>}<span className="qx-segment__source-label">{formatMaterialLocator(segment.locator)}</span></div>
  </div>
}
