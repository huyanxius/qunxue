import {
  ArrowLeftIcon,
  CircleNotchIcon,
  IdentificationCardIcon,
  ListBulletsIcon,
  MagnifyingGlassIcon,
  WarningCircleIcon,
  XIcon,
} from '@phosphor-icons/react'
import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'

import {
  formatMaterialLocator,
  formatMaterialSize,
  materialKindLabel,
  materialMediaLabel,
  materialStatusLabel,
  type ResearchMaterial,
  type ResearchMaterialSegment,
} from './researchMaterialsModel'
import type { AnalysisAnnotation, AnalysisCode } from './researchAnalysisModel'

/**
 * 中央栏被 Agent 栏挤到这个宽度以下时，208px 的章节栏会吃掉三分之一，正文一行只剩十几个
 * 字。低于阈值目录改成浮层，并且初次进入时不展开——先让人看见文档，要目录再叫它出来。
 */
const OUTLINE_COLUMN_MIN_WIDTH = 720

type ReaderHeading = {
  readonly segment: ResearchMaterialSegment
  readonly label: string
}

type MaterialReaderViewProps = {
  readonly material: ResearchMaterial
  readonly segments: readonly ResearchMaterialSegment[]
  readonly totalSegmentCount: number
  readonly headings: readonly ReaderHeading[]
  readonly selectedSegmentId: string | null
  readonly detailLoading: boolean
  readonly note: { readonly tone: 'plain' | 'error'; readonly text: string } | null
  readonly outlineOpen: boolean
  readonly searchOpen: boolean
  readonly query: string
  readonly matchCount: number
  readonly page: number
  readonly pageCount: number
  readonly annotations?: readonly AnalysisAnnotation[]
  readonly codes?: readonly AnalysisCode[]
  readonly workspaceChrome?: boolean
  readonly registerSegment: (segmentId: string, element: HTMLElement | null) => void
  readonly onBack: () => void
  readonly onToggleOutline: () => void
  readonly onToggleSearch: () => void
  readonly onQueryChange: (query: string) => void
  readonly onOpenArchive: () => void
  readonly onSelectSegment: (segment: ResearchMaterialSegment) => void
  readonly onTextSelection: (segment: ResearchMaterialSegment, container: HTMLElement, range: Range) => void
  readonly onPageChange: (page: number) => void
}

/**
 * 阅读台：一份材料打开后的样子。左侧章节、中间原文、顶部一条固定的文档栏。
 *
 * 三类动作在文档栏里是分开的：返回材料库是导航，靠最左；目录和查找是阅读工具，成组放右；
 * 档案是这份材料的元信息，隔一道分隔线再放。它们视觉重量一样但归属不同，不分组的话按下去
 * 之前没人知道会发生什么。
 */
export function MaterialReaderView({
  material,
  segments,
  totalSegmentCount,
  headings,
  selectedSegmentId,
  detailLoading,
  note,
  outlineOpen,
  searchOpen,
  query,
  matchCount,
  page,
  pageCount,
  annotations = [],
  codes = [],
  workspaceChrome = false,
  registerSegment,
  onBack,
  onToggleOutline,
  onToggleSearch,
  onQueryChange,
  onOpenArchive,
  onSelectSegment,
  onTextSelection,
  onPageChange,
}: MaterialReaderViewProps) {
  const frameRef = useRef<HTMLElement | null>(null)
  const [narrow, setNarrow] = useState(false)
  const [codingView, setCodingView] = useState(annotations.length > 0)
  const [activeCodeIds, setActiveCodeIds] = useState<string[]>([])
  const [selectedAnnotationId, setSelectedAnnotationId] = useState<string | null>(null)
  const [codeFilterOpen, setCodeFilterOpen] = useState(false)
  const narrowMeasured = useRef(false)

  const annotationsBySegment = useMemo(() => {
    const index = new Map<string, AnalysisAnnotation[]>()
    annotations.forEach((annotation) => {
      const current = index.get(annotation.segment_id) ?? []
      current.push(annotation)
      index.set(annotation.segment_id, current)
    })
    return index
  }, [annotations])
  const visibleCodes = useMemo(() => (
    codes.filter((code) => annotations.some((annotation) => code.annotation_ids.includes(annotation.annotation_id)))
  ), [annotations, codes])
  const selectedAnnotation = selectedAnnotationId
    ? annotations.find((annotation) => annotation.annotation_id === selectedAnnotationId) ?? null
    : null

  useEffect(() => {
    if (annotations.length && !codingView) setCodingView(true)
    if (!annotations.some((annotation) => annotation.annotation_id === selectedAnnotationId)) setSelectedAnnotationId(null)
  }, [annotations, codingView, selectedAnnotationId])

  useEffect(() => {
    const frame = frameRef.current
    if (!frame || typeof ResizeObserver !== 'function') return
    const observer = new ResizeObserver(([entry]) => {
      const isNarrow = entry.contentRect.width > 0 && entry.contentRect.width < OUTLINE_COLUMN_MIN_WIDTH
      setNarrow(isNarrow)
      // 只在第一次量出来时替用户收一次目录；之后他自己开了就一直开着。
      if (!narrowMeasured.current && entry.contentRect.width > 0) {
        narrowMeasured.current = true
        if (isNarrow && outlineOpen) onToggleOutline()
      }
    })
    observer.observe(frame)
    return () => observer.disconnect()
  }, [onToggleOutline, outlineOpen])

  const identity = [
    material.materialKind ? materialKindLabel(material.materialKind) : materialMediaLabel(material.mediaType, material.filename),
    formatMaterialSize(material.sizeBytes),
    material.segmentCount ? `${material.segmentCount} 个可定位片段` : materialStatusLabel(material.status),
  ].filter(Boolean).join(' · ')

  /**
   * 拖选文字时浏览器也会补一个 click。没有这道判断，划完一句原文的瞬间就会被当成
   * 「点了这一段」，把刚划出来的选区顶掉——标记根本来不及做。
   */
  function locateFromPointer(segment: ResearchMaterialSegment) {
    const selection = window.getSelection()
    if (selection && !selection.isCollapsed) return
    onSelectSegment(segment)
  }

  function captureFromParagraph(segment: ResearchMaterialSegment, event: ReactMouseEvent<HTMLElement>) {
    const selection = window.getSelection()
    if (!selection || selection.rangeCount !== 1 || selection.isCollapsed) return
    onTextSelection(segment, event.currentTarget, selection.getRangeAt(0))
  }

  function segmentAnnotations(segment: ResearchMaterialSegment) {
    const items = annotationsBySegment.get(segment.segmentId) ?? []
    return items.filter((annotation) => {
      if (!activeCodeIds.length) return true
      return codes.some((code) => activeCodeIds.includes(code.code_id) && code.annotation_ids.includes(annotation.annotation_id))
    })
  }

  function renderCodedText(segment: ResearchMaterialSegment, items: readonly AnalysisAnnotation[]) {
    const text = segment.text || '此片段没有可显示的正文。'
    if (!codingView || !items.length) return text
    const target = items.find((item) => item.quote && text.includes(item.quote))
    if (!target?.quote) return <mark className="qx-coded-text is-whole">{text}</mark>
    const start = text.indexOf(target.quote)
    return <>{text.slice(0, start)}<mark className="qx-coded-text">{target.quote}</mark>{text.slice(start + target.quote.length)}</>
  }

  function codeLabelsFor(annotation: AnalysisAnnotation) {
    const labels = codes.filter((code) => code.annotation_ids.includes(annotation.annotation_id)).map((code) => ({
      id: code.code_id,
      label: code.label,
      status: code.status,
    }))
    return labels.length ? labels : [{ id: `annotation:${annotation.annotation_id}`, label: '待命名标记', status: 'candidate' as const }]
  }

  return (
    <section className={`qx-reader${narrow ? ' is-narrow' : ''}${workspaceChrome ? ' is-workspace-chrome' : ''}`} aria-label="材料阅读台" ref={frameRef}>
      <header className={`qx-reader__bar${workspaceChrome ? ' is-workspace-chrome' : ''}`}>
        {!workspaceChrome ? <>
          <button type="button" className="qx-reader__back" onClick={onBack}>
            <ArrowLeftIcon size={16} aria-hidden="true" />
            材料库
          </button>
          <div className="qx-reader__identity">
            <h2>{material.filename}</h2>
            <p>{identity}</p>
          </div>
        </> : null}
        <div className="qx-reader__tools">
          <button
            type="button"
            className="qx-icon-button"
            aria-pressed={outlineOpen}
            aria-controls="research-materials-outline"
            aria-label={outlineOpen ? '收起章节目录' : '展开章节目录'}
            title={outlineOpen ? '收起章节目录' : '展开章节目录'}
            onClick={onToggleOutline}
          >
            <ListBulletsIcon size={16} aria-hidden="true" />
          </button>
          <button
            type="button"
            className="qx-icon-button"
            aria-pressed={searchOpen}
            aria-controls="research-materials-reader-search"
            aria-label="在材料中查找"
            title="在材料中查找"
            onClick={onToggleSearch}
          >
            <MagnifyingGlassIcon size={16} aria-hidden="true" />
          </button>
          {annotations.length ? (
            <>
              <button
                type="button"
                className={`qx-reader__coding-toggle${codingView ? ' is-active' : ''}`}
                aria-pressed={codingView}
                onClick={() => setCodingView((open) => !open)}
              >
                {codingView ? '编码视图' : '原文视图'}
              </button>
              <button
                type="button"
                className={`qx-reader__coding-filter${codeFilterOpen ? ' is-active' : ''}`}
                aria-expanded={codeFilterOpen}
                onClick={() => setCodeFilterOpen((open) => !open)}
              >
                代码筛选{activeCodeIds.length ? ` · ${activeCodeIds.length}` : ''}
              </button>
            </>
          ) : null}
          <span className="qx-reader__tool-rule" aria-hidden="true" />
          <button
            type="button"
            className="qx-icon-button"
            aria-label="材料档案"
            title="材料档案"
            onClick={onOpenArchive}
          >
            <IdentificationCardIcon size={16} aria-hidden="true" />
          </button>
        </div>
      </header>

      {searchOpen ? (
        <div className="qx-reader__search" id="research-materials-reader-search">
          <label className="qx-reader__search-field">
            <MagnifyingGlassIcon size={15} aria-hidden="true" />
            <span className="sr-only">在材料中查找</span>
            <input
              type="search"
              role="searchbox"
              aria-label="在材料中查找"
              value={query}
              placeholder="查找原文或定位"
              autoFocus
              onChange={(event) => onQueryChange(event.target.value)}
            />
            {query ? (
              <button type="button" aria-label="清除材料查找" onClick={() => onQueryChange('')}>
                <XIcon size={13} aria-hidden="true" />
              </button>
            ) : null}
          </label>
          <span className="qx-reader__search-count">
            {query.trim() ? `${matchCount} 处命中` : `${totalSegmentCount} 段原文`}
          </span>
        </div>
      ) : null}

      {codeFilterOpen && visibleCodes.length ? (
        <div className="qx-reader__code-filter" role="group" aria-label="编码筛选">
          <span>显示编码</span>
          <button type="button" className={!activeCodeIds.length ? 'is-selected' : undefined} onClick={() => setActiveCodeIds([])}>全部</button>
          {visibleCodes.map((code) => (
            <button
              type="button"
              key={code.code_id}
              className={activeCodeIds.includes(code.code_id) ? 'is-selected' : undefined}
              onClick={() => setActiveCodeIds((current) => current.includes(code.code_id) ? current.filter((id) => id !== code.code_id) : [...current, code.code_id])}
            >
              <i aria-hidden="true" />{code.label}
            </button>
          ))}
        </div>
      ) : null}

      <div className={`qx-reader__body${outlineOpen ? ' is-outline-open' : ''}`}>
        <nav id="research-materials-outline" className="qx-reader__outline" aria-label="章节导航" aria-hidden={!outlineOpen}>
          <span className="qx-reader__outline-title">章节</span>
          {headings.length ? headings.map(({ segment, label }) => (
            <button
              type="button"
              key={segment.segmentId}
              className={segment.segmentId === selectedSegmentId ? 'is-current' : undefined}
              title={label}
              tabIndex={outlineOpen ? undefined : -1}
              onClick={() => {
                onSelectSegment(segment)
                // 浮层里的目录选完就该让路，不然跳过去的那一段正被它盖着。
                if (narrow) onToggleOutline()
              }}
            >
              {label}
            </button>
          )) : <small>解析出章节后会显示在这里。</small>}
        </nav>

        {narrow && outlineOpen ? (
          <button type="button" className="qx-reader__outline-scrim" aria-label="收起章节目录" onClick={onToggleOutline} />
        ) : null}

        <div className={`qx-reader__scroll${selectedAnnotation ? ' has-inspector' : ''}`} role="region" aria-label="文档阅读器">
          {detailLoading ? (
            <p className="qx-message" role="status"><CircleNotchIcon className="is-spinning" size={16} aria-hidden="true" />正在读取原文结构</p>
          ) : null}
          {note ? (
            <p className={`qx-message${note.tone === 'error' ? ' is-error' : ''}`} role={note.tone === 'error' ? 'alert' : undefined}>
              {note.tone === 'error' ? <WarningCircleIcon size={15} aria-hidden="true" /> : null}
              {note.text}
            </p>
          ) : null}

          <article className="qx-reader__doc">
            {segments.map((segment) => {
              const selected = segment.segmentId === selectedSegmentId
              const locator = formatMaterialLocator(segment.locator)
              const heading = segment.kind === 'heading'
              const codedAnnotations = segmentAnnotations(segment)
              return (
                <div
                  className={`qx-segment${selected ? ' is-selected' : ''}${heading ? ' is-heading' : ''}${codedAnnotations.length && codingView ? ' is-coded' : ''}`}
                  key={segment.segmentId}
                  data-segment-id={segment.segmentId}
                  aria-current={selected ? 'location' : undefined}
                  ref={(element) => registerSegment(segment.segmentId, element)}
                  onClick={() => locateFromPointer(segment)}
                >
                  {/*
                    定位符是引用用的坐标，不是正文的一部分。默认只在悬停、聚焦或选中时露出来，
                    常驻显示会让整篇原文看着像数据库导出。它同时是键盘用户定位这一段的入口——
                    正文本身要留给自由划选，不能再包一层按钮。
                  */}
                  <button
                    type="button"
                    className="qx-segment__anchor"
                    aria-label={`定位到${locator}`}
                    title={locator}
                    onClick={(event) => { event.stopPropagation(); onSelectSegment(segment) }}
                  >
                    {locator}
                  </button>
                  {heading ? (
                    <h3 onMouseUp={(event) => captureFromParagraph(segment, event)}>{renderCodedText(segment, codedAnnotations)}</h3>
                  ) : (
                    <p onMouseUp={(event) => captureFromParagraph(segment, event)}>{renderCodedText(segment, codedAnnotations)}</p>
                  )}
                  {codingView && codedAnnotations.length ? (
                    <aside className="qx-coding-rail" aria-label="此段编码">
                      {codedAnnotations.flatMap((annotation) => codeLabelsFor(annotation).map((code) => (
                        <button
                          type="button"
                          key={`${annotation.annotation_id}:${code.id}`}
                          className={code.status === 'candidate' ? 'is-candidate' : undefined}
                          onClick={(event) => { event.stopPropagation(); setSelectedAnnotationId(annotation.annotation_id) }}
                          title={`${code.label} · ${code.status === 'confirmed' ? '已确认' : '候选'}`}
                        >
                          <span aria-hidden="true" />{code.label}
                        </button>
                      )))}
                    </aside>
                  ) : null}
                </div>
              )
            })}
            {!segments.length && !detailLoading ? (
              <p className="qx-reader__no-results">{query.trim() ? '没有匹配的原文。换个词试试。' : '暂时没有可展示的片段。'}</p>
            ) : null}
          </article>

          {pageCount > 1 ? (
            <footer className="qx-reader__pagination" aria-label="文档分页">
              <button type="button" aria-label="上一页" disabled={page === 0} onClick={() => onPageChange(Math.max(0, page - 1))}>上一页</button>
              <span>第 {page + 1} / {pageCount} 页</span>
              <button type="button" aria-label="下一页" disabled={page >= pageCount - 1} onClick={() => onPageChange(Math.min(pageCount - 1, page + 1))}>下一页</button>
            </footer>
          ) : null}
        </div>
        {selectedAnnotation ? (
          <aside className="qx-reader__inspector" aria-label="编码证据检查器">
            <header>
              <span>编码证据</span>
              <button type="button" aria-label="关闭编码证据" onClick={() => setSelectedAnnotationId(null)}><XIcon size={15} aria-hidden="true" /></button>
            </header>
            <blockquote>{selectedAnnotation.quote || '整段标记'}</blockquote>
            <div className="qx-reader__inspector-codes">
              {codeLabelsFor(selectedAnnotation).map((code) => <span key={code.id} className={code.status === 'candidate' ? 'is-candidate' : undefined}>{code.label}</span>)}
            </div>
            <dl>
              <div><dt>状态</dt><dd>{selectedAnnotation.annotation_kind === 'researcher_reflection' ? '研究者反思' : '描述性标记'}</dd></div>
              <div><dt>位置</dt><dd>{formatMaterialLocator({ page: selectedAnnotation.locator.page, headingPath: selectedAnnotation.locator.section_path, paragraph: selectedAnnotation.locator.paragraph, lineStart: selectedAnnotation.locator.line_start, lineEnd: selectedAnnotation.locator.line_end, charStart: selectedAnnotation.locator.char_start, charEnd: selectedAnnotation.locator.char_end })}</dd></div>
            </dl>
            {selectedAnnotation.note ? <p className="qx-reader__inspector-note">{selectedAnnotation.note}</p> : null}
            {selectedAnnotation.reflection ? <p className="qx-reader__inspector-reflection"><span>研究者反思</span>{selectedAnnotation.reflection}</p> : null}
            <small>{selectedAnnotation.source_available ? '来源可追溯' : `来源不可用：${selectedAnnotation.unavailable_reason || '未说明'}`}</small>
          </aside>
        ) : null}
      </div>
    </section>
  )
}

export type { ReaderHeading }
