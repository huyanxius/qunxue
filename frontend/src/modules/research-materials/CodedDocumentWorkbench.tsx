import {
  ArrowLeftIcon,
  ArrowSquareOutIcon,
  CaretDownIcon,
  CaretRightIcon,
  CheckIcon,
  CircleNotchIcon,
  CopyIcon,
  DownloadSimpleIcon,
  DotsThreeIcon,
  EyeIcon,
  EyeSlashIcon,
  FileTextIcon,
  HighlighterIcon,
  IdentificationCardIcon,
  InfoIcon,
  ListBulletsIcon,
  MagnifyingGlassIcon,
  NoteIcon,
  PlusIcon,
  QuotesIcon,
  SidebarSimpleIcon,
  TagIcon,
  WarningCircleIcon,
  XCircleIcon,
  XIcon,
} from '@phosphor-icons/react'
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from 'react'

import {
  formatMaterialLocator,
  formatMaterialSize,
  materialKindLabel,
  materialMediaLabel,
  materialStatusLabel,
  type ResearchMaterial,
  type ResearchMaterialSegment,
} from './researchMaterialsModel'
import type {
  AnalysisAnnotation,
  AnalysisCode,
  AnalysisMemo,
  AnalysisRecordStatus,
  CodebookEntry,
  CreateAnalysisCodeInput,
  CreateAnalysisMemoInput,
} from './researchAnalysisModel'
import { buildCodedTextRuns, codeColor, type CodedAnnotation } from './codedDocumentModel'

const OUTLINE_COLUMN_MIN_WIDTH = 860

export type ReaderHeading = {
  readonly segment: ResearchMaterialSegment
  readonly label: string
}

export type MaterialReaderViewProps = {
  readonly material: ResearchMaterial
  readonly segments: readonly ResearchMaterialSegment[]
  /** Full material stream; `segments` may be a paged slice for the reader. */
  readonly allSegments?: readonly ResearchMaterialSegment[]
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
  readonly memos?: readonly AnalysisMemo[]
  readonly codebook?: readonly CodebookEntry[]
  readonly agentPanel?: ReactNode
  readonly analysisPanel?: ReactNode
  readonly workspaceNavigation?: ReactNode
  readonly codingAction?: ReactNode
  readonly workspaceChrome?: boolean
  readonly registerSegment: (segmentId: string, element: HTMLElement | null) => void
  readonly onBack: () => void
  readonly onToggleOutline: () => void
  readonly onToggleSearch: () => void
  readonly onQueryChange: (query: string) => void
  readonly onOpenArchive: () => void
  readonly onSelectSegment: (segment: ResearchMaterialSegment) => void
  readonly onLocateSegment?: (segment: ResearchMaterialSegment) => void
  readonly onTextSelection: (segment: ResearchMaterialSegment, container: HTMLElement, range: Range) => void
  readonly onPageChange: (page: number) => void
  readonly onCreateCode?: (input: CreateAnalysisCodeInput) => Promise<void>
  readonly onDecideCode?: (codeId: string, decision: Extract<AnalysisRecordStatus, 'confirmed' | 'rejected'>, reason: string) => Promise<void>
  readonly onCreateMemo?: (input: CreateAnalysisMemoInput) => Promise<void>
  readonly onDecideMemo?: (memoId: string, decision: Extract<AnalysisRecordStatus, 'confirmed' | 'rejected'>, reason: string) => Promise<void>
}

type ReaderInspectorMode = 'empty' | 'evidence' | 'code' | 'retrieved'
type ContextMenuState = { readonly x: number; readonly y: number; readonly segmentId: string; readonly annotationId: string | null }
type RetrievalRow = {
  readonly annotation: AnalysisAnnotation
  readonly segment: ResearchMaterialSegment
  readonly labels: string[]
}

const statusLabel: Record<AnalysisRecordStatus, string> = {
  candidate: '候选',
  confirmed: '已确认',
  rejected: '已拒绝',
}

const memoKindLabel: Record<AnalysisMemo['memo_kind'], string> = {
  descriptive: '描述性',
  reflexive: '反思性',
  analytic: '分析性',
  methodological: '方法性',
}

function annotationLocator(annotation: AnalysisAnnotation): string {
  return formatMaterialLocator({
    page: annotation.locator.page,
    headingPath: annotation.locator.section_path,
    paragraph: annotation.locator.paragraph,
    lineStart: annotation.locator.line_start,
    lineEnd: annotation.locator.line_end,
    charStart: annotation.locator.char_start,
    charEnd: annotation.locator.char_end,
  })
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character] ?? character)
}

function downloadFile(filename: string, content: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

function csvCell(value: string): string {
  return `"${value.replace(/"/g, '""')}"`
}

function lineLabel(segment: ResearchMaterialSegment, index: number): string {
  if (segment.locator.lineStart !== null) {
    return segment.locator.lineEnd && segment.locator.lineEnd !== segment.locator.lineStart
      ? `${segment.locator.lineStart}–${segment.locator.lineEnd}`
      : String(segment.locator.lineStart)
  }
  if (segment.locator.paragraph !== null) return `¶${segment.locator.paragraph}`
  return String(index + 1)
}

function isCurrentAnnotation(annotation: AnalysisAnnotation, selectedId: string | null, hoveredId: string | null): boolean {
  return annotation.annotation_id === selectedId || annotation.annotation_id === hoveredId
}

/**
 * The document browser is intentionally a single interaction surface. The left tree
 * changes what is visible, the centre keeps the source intact, and the right inspector
 * explains the selected evidence. None of the controls are decorative: each state is
 * represented in the URL-independent local view and, where applicable, persisted by the
 * parent through the analysis API callbacks.
 */
export function CodedDocumentWorkbench({
  material,
  segments,
  allSegments = segments,
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
  memos = [],
  codebook = [],
  workspaceChrome = false,
  agentPanel,
  analysisPanel,
  workspaceNavigation,
  codingAction,
  registerSegment,
  onBack,
  onToggleOutline,
  onToggleSearch,
  onQueryChange,
  onOpenArchive,
  onSelectSegment,
  onLocateSegment,
  onTextSelection,
  onPageChange,
  onCreateCode,
  onDecideCode,
  onCreateMemo,
  onDecideMemo,
}: MaterialReaderViewProps) {
  const [panel, setPanel] = useState<'evidence' | 'analysis' | 'agent'>('evidence')
  const frameRef = useRef<HTMLElement | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const [narrow, setNarrow] = useState(false)
  const [viewMode, setViewMode] = useState<'source' | 'coding'>(annotations.length ? 'coding' : 'source')
  const [sidebarTab, setSidebarTab] = useState<'chapters' | 'codes'>('chapters')
  const [inspectorMode, setInspectorMode] = useState<ReaderInspectorMode>('empty')
  const [activeCodeIds, setActiveCodeIds] = useState<string[]>([])
  const [selectedAnnotationId, setSelectedAnnotationId] = useState<string | null>(null)
  const [selectedCodeId, setSelectedCodeId] = useState<string | null>(null)
  const [hoveredAnnotationId, setHoveredAnnotationId] = useState<string | null>(null)
  const [codeFilterOpen, setCodeFilterOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [showCodeNames, setShowCodeNames] = useState(true)
  const [showHighlights, setShowHighlights] = useState(true)
  const [colorPickerOpen, setColorPickerOpen] = useState(false)
  const [zoom, setZoom] = useState<90 | 100 | 110 | 125>(100)
  const [customCodeColors, setCustomCodeColors] = useState<Record<string, string>>({})
  const [retrievalLayout, setRetrievalLayout] = useState<'list' | 'table'>('list')
  const [retrievalSort, setRetrievalSort] = useState<'document' | 'code'>('document')
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null)
  const [codeComposerOpen, setCodeComposerOpen] = useState(false)
  const [memoComposerOpen, setMemoComposerOpen] = useState(false)
  const [newCodeLabel, setNewCodeLabel] = useState('')
  const [newCodeDefinition, setNewCodeDefinition] = useState('')
  const [newCodeRationale, setNewCodeRationale] = useState('')
  const [newMemoTitle, setNewMemoTitle] = useState('')
  const [newMemoContent, setNewMemoContent] = useState('')
  const [newMemoKind, setNewMemoKind] = useState<AnalysisMemo['memo_kind']>('analytic')
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [localError, setLocalError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const narrowMeasured = useRef(false)
  const pendingScrollSegmentId = useRef<string | null>(null)

  const codePalette = ['#3f6f8f', '#8e5a78', '#5f7d4b', '#a27635', '#725d8f', '#4b817c', '#9a5c48']

  const annotationsBySegment = useMemo(() => {
    const index = new Map<string, AnalysisAnnotation[]>()
    annotations.forEach((annotation) => {
      const current = index.get(annotation.segment_id) ?? []
      current.push(annotation)
      index.set(annotation.segment_id, current)
    })
    return index
  }, [annotations])

  const codeByAnnotation = useMemo(() => {
    const index = new Map<string, AnalysisCode[]>()
    codes.forEach((code) => code.annotation_ids.forEach((annotationId) => {
      const current = index.get(annotationId) ?? []
      current.push(code)
      index.set(annotationId, current)
    }))
    return index
  }, [codes])

  const visibleCodes = useMemo(() => (
    codes.filter((code) => annotations.some((annotation) => code.annotation_ids.includes(annotation.annotation_id)))
  ), [annotations, codes])

  const selectedAnnotation = selectedAnnotationId
    ? annotations.find((annotation) => annotation.annotation_id === selectedAnnotationId) ?? null
    : null
  const selectedCode = selectedCodeId
    ? codes.find((code) => code.code_id === selectedCodeId) ?? null
    : null
  const selectedCodebook = selectedCodeId
    ? codebook.find((entry) => entry.code_id === selectedCodeId) ?? null
    : null

  const codeParentById = useMemo(() => new Map(codebook.map((entry) => [entry.code_id, entry.parent_code_id])), [codebook])

  useEffect(() => {
    if (selectedAnnotationId || selectedCodeId) setPanel('evidence')
  }, [selectedAnnotationId, selectedCodeId])

  const selectedMemos = useMemo(() => {
    if (!selectedAnnotation) return []
    return memos.filter((memo) => memo.annotation_ids.includes(selectedAnnotation.annotation_id))
  }, [memos, selectedAnnotation])

  const retrievalRows = useMemo<RetrievalRow[]>(() => {
    const segmentMap = new Map(allSegments.map((segment) => [segment.segmentId, segment]))
    const rows = annotations
      .map((annotation) => {
        const segment = segmentMap.get(annotation.segment_id)
        if (!segment) return null
        const linkedCodes = codeByAnnotation.get(annotation.annotation_id) ?? []
        if (activeCodeIds.length && !linkedCodes.some((code) => activeCodeIds.includes(code.code_id))) return null
        return { annotation, segment, labels: linkedCodes.map((code) => code.label) }
      })
      .filter((row): row is RetrievalRow => Boolean(row))
    return rows.sort((left, right) => retrievalSort === 'code'
      ? left.labels.join(' / ').localeCompare(right.labels.join(' / '))
      : left.segment.segmentId.localeCompare(right.segment.segmentId))
  }, [activeCodeIds, allSegments, annotations, codeByAnnotation, retrievalSort])

  useEffect(() => {
    if (annotations.length && viewMode === 'source') setViewMode('coding')
    if (!annotations.some((annotation) => annotation.annotation_id === selectedAnnotationId)) {
      setSelectedAnnotationId(null)
      if (inspectorMode === 'evidence') setInspectorMode('empty')
    }
    if (!codes.some((code) => code.code_id === selectedCodeId)) setSelectedCodeId(null)
  }, [annotations, codes, inspectorMode, selectedAnnotationId, selectedCodeId, viewMode])

  useEffect(() => {
    const frame = frameRef.current
    if (!frame || typeof ResizeObserver !== 'function') return
    const observer = new ResizeObserver(([entry]) => {
      const isNarrow = entry.contentRect.width > 0 && entry.contentRect.width < OUTLINE_COLUMN_MIN_WIDTH
      setNarrow(isNarrow)
      if (!narrowMeasured.current && entry.contentRect.width > 0) {
        narrowMeasured.current = true
        if (isNarrow && outlineOpen) onToggleOutline()
      }
    })
    observer.observe(frame)
    return () => observer.disconnect()
  }, [onToggleOutline, outlineOpen])

  useEffect(() => {
    const targetId = pendingScrollSegmentId.current
    if (!targetId || !segments.some((segment) => segment.segmentId === targetId)) return
    const element = document.querySelector<HTMLElement>(`[data-segment-id="${targetId.replace(/["\\]/g, '\\$&')}"]`)
    if (!element) return
    element.scrollIntoView({ behavior: 'smooth', block: 'center' })
    pendingScrollSegmentId.current = null
  }, [page, segments, selectedSegmentId])

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        if (contextMenu) setContextMenu(null)
        else if (exportOpen) setExportOpen(false)
        else if (codeFilterOpen) setCodeFilterOpen(false)
        else if (codeComposerOpen) setCodeComposerOpen(false)
        else if (memoComposerOpen) setMemoComposerOpen(false)
        else if (inspectorMode !== 'empty') {
          setInspectorMode('empty')
          setSelectedAnnotationId(null)
          setSelectedCodeId(null)
        }
        return
      }
      if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLocaleLowerCase() === 'f') {
        event.preventDefault()
        onToggleSearch()
      }
      if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLocaleLowerCase() === 'r') {
        event.preventDefault()
        setInspectorMode('retrieved')
        setSelectedAnnotationId(null)
        setSelectedCodeId(null)
      }
      if ((event.metaKey || event.ctrlKey) && !event.shiftKey && /^[1-9]$/.test(event.key)) {
        const code = visibleCodes[Number(event.key) - 1]
        if (!code) return
        event.preventDefault()
        setActiveCodeIds([code.code_id])
        setSidebarTab('codes')
      }
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [codeComposerOpen, codeFilterOpen, contextMenu, exportOpen, inspectorMode, memoComposerOpen, onToggleSearch, visibleCodes])

  const identity = [
    material.materialKind ? materialKindLabel(material.materialKind) : materialMediaLabel(material.mediaType, material.filename),
    formatMaterialSize(material.sizeBytes),
    material.segmentCount ? `${material.segmentCount} 个可定位片段` : materialStatusLabel(material.status),
  ].filter(Boolean).join(' · ')

  function codeLabelsFor(annotation: AnalysisAnnotation): AnalysisCode[] {
    return codeByAnnotation.get(annotation.annotation_id) ?? []
  }

  function effectiveCodeColor(code: AnalysisCode, index: number): string {
    return customCodeColors[code.code_id] ?? codeColor(index)
  }

  function codeDepth(codeId: string): number {
    let depth = 0
    let parent = codeParentById.get(codeId) ?? null
    const seen = new Set<string>()
    while (parent && !seen.has(parent) && depth < 8) {
      seen.add(parent)
      depth += 1
      parent = codeParentById.get(parent) ?? null
    }
    return depth
  }

  function segmentAnnotations(segment: ResearchMaterialSegment): AnalysisAnnotation[] {
    const items = annotationsBySegment.get(segment.segmentId) ?? []
    if (!activeCodeIds.length) return items
    return items.filter((annotation) => (codeByAnnotation.get(annotation.annotation_id) ?? [])
      .some((code) => activeCodeIds.includes(code.code_id)))
  }

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

  function selectAnnotation(annotation: AnalysisAnnotation, segment?: ResearchMaterialSegment) {
    setSelectedAnnotationId(annotation.annotation_id)
    setSelectedCodeId(codeLabelsFor(annotation)[0]?.code_id ?? null)
    setInspectorMode('evidence')
    if (segment) (onLocateSegment ?? onSelectSegment)(segment)
  }

  function jumpToRetrieved(row: RetrievalRow) {
    setInspectorMode('evidence')
    pendingScrollSegmentId.current = row.segment.segmentId
    selectAnnotation(row.annotation, row.segment)
  }

  function renderCodedText(segment: ResearchMaterialSegment, items: readonly AnalysisAnnotation[]): ReactNode {
    const text = segment.text || '此片段没有可显示的正文。'
    if (viewMode === 'source' || !items.length) return text
    const codedItems: CodedAnnotation[] = items.map((annotation) => {
      const labels = codeLabelsFor(annotation)
      return {
        annotation,
        label: labels.map((code) => code.label).join(' / ') || '待命名标记',
        status: labels.some((code) => code.status === 'candidate') ? 'candidate' : labels[0]?.status ?? 'candidate',
      }
    })
    const runs = buildCodedTextRuns(text, codedItems)
    return runs.map((run, index) => {
      if (!run.annotationIds.length) return <span key={`plain-${index}`}>{run.text}</span>
      const primary = run.annotationIds[0]
      const labels = run.annotationIds.flatMap((id) => codeLabelsFor(annotations.find((item) => item.annotation_id === id)!).map((code) => code.label))
      const selected = run.annotationIds.some((id) => isCurrentAnnotation(annotations.find((item) => item.annotation_id === id)!, selectedAnnotationId, hoveredAnnotationId))
      const statusClass = run.statuses.includes('candidate') ? 'is-candidate' : run.statuses.includes('rejected') ? 'is-rejected' : 'is-confirmed'
      return (
        <mark
          key={`coded-${index}`}
          className={`qx-coded-text ${showHighlights ? '' : 'is-muted'} ${statusClass}${run.annotationIds.length > 1 ? ' is-overlap' : ''}${selected ? ' is-current' : ''}`}
          data-annotation-ids={run.annotationIds.join(' ')}
          title={labels.join(' · ') || '待命名标记'}
          onMouseEnter={() => setHoveredAnnotationId(primary)}
          onMouseLeave={() => setHoveredAnnotationId(null)}
          onClick={(event) => {
            event.stopPropagation()
            const target = annotations.find((item) => item.annotation_id === primary)
            if (target) selectAnnotation(target, segment)
          }}
        >
          {run.text}
        </mark>
      )
    })
  }

  function openContextMenu(event: ReactMouseEvent, segmentId: string, annotationId: string | null = null) {
    event.preventDefault()
    setContextMenu({ x: event.clientX, y: event.clientY, segmentId, annotationId })
  }

  async function copyLocator(annotation: AnalysisAnnotation | null, segment: ResearchMaterialSegment | null) {
    const value = annotation ? annotationLocator(annotation) : segment ? formatMaterialLocator(segment.locator) : ''
    if (!value) return
    try {
      await navigator.clipboard?.writeText(value)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    } catch {
      setLocalError('浏览器未允许复制定位信息。')
    }
    setContextMenu(null)
  }

  async function submitCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!onCreateCode || !selectedAnnotation || !newCodeLabel.trim() || busyAction) return
    setBusyAction('create-code')
    setLocalError(null)
    try {
      await onCreateCode({
        label: newCodeLabel.trim(),
        definition: newCodeDefinition.trim(),
        rationale: newCodeRationale.trim(),
        annotation_ids: [selectedAnnotation.annotation_id],
      })
      setNewCodeLabel('')
      setNewCodeDefinition('')
      setNewCodeRationale('')
      setCodeComposerOpen(false)
    } catch (cause: unknown) {
      setLocalError(cause instanceof Error ? cause.message : '编码未保存。')
    } finally {
      setBusyAction(null)
    }
  }

  async function createInVivoCode() {
    if (!onCreateCode || !selectedAnnotation || busyAction) return
    const label = (selectedAnnotation.quote || '整段标记').trim().slice(0, 80)
    if (!label) return
    setBusyAction('create-in-vivo')
    setLocalError(null)
    try {
      await onCreateCode({
        label,
        definition: '使用原文中的受访者用词作为代码。',
        rationale: '原词编码保留材料中的概念表达，供后续代码比较。',
        annotation_ids: [selectedAnnotation.annotation_id],
      })
    } catch (cause: unknown) {
      setLocalError(cause instanceof Error ? cause.message : '原词编码未保存。')
    } finally {
      setBusyAction(null)
    }
  }

  async function submitMemo(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!onCreateMemo || !newMemoTitle.trim() || !newMemoContent.trim() || busyAction) return
    setBusyAction('create-memo')
    setLocalError(null)
    try {
      await onCreateMemo({
        title: newMemoTitle.trim(),
        content: newMemoContent.trim(),
        memo_kind: newMemoKind,
        annotation_ids: selectedAnnotation ? [selectedAnnotation.annotation_id] : [],
        code_ids: selectedCodeId ? [selectedCodeId] : [],
      })
      setNewMemoTitle('')
      setNewMemoContent('')
      setMemoComposerOpen(false)
    } catch (cause: unknown) {
      setLocalError(cause instanceof Error ? cause.message : '备忘未保存。')
    } finally {
      setBusyAction(null)
    }
  }

  async function decideCode(code: AnalysisCode, decision: Extract<AnalysisRecordStatus, 'confirmed' | 'rejected'>) {
    if (!onDecideCode || busyAction) return
    setBusyAction(`decide-code:${code.code_id}`)
    setLocalError(null)
    try {
      await onDecideCode(code.code_id, decision, decision === 'confirmed' ? '研究者已在原文中核对' : '研究者暂不采用此候选')
    } catch (cause: unknown) {
      setLocalError(cause instanceof Error ? cause.message : '编码判断未保存。')
    } finally {
      setBusyAction(null)
    }
  }

  async function decideMemo(memo: AnalysisMemo, decision: Extract<AnalysisRecordStatus, 'confirmed' | 'rejected'>) {
    if (!onDecideMemo || busyAction) return
    setBusyAction(`decide-memo:${memo.memo_id}`)
    setLocalError(null)
    try {
      await onDecideMemo(memo.memo_id, decision, decision === 'confirmed' ? '研究者已确认' : '研究者暂不采用此备忘')
    } catch (cause: unknown) {
      setLocalError(cause instanceof Error ? cause.message : '备忘判断未保存。')
    } finally {
      setBusyAction(null)
    }
  }

  function exportHtml() {
    const rows = segments.map((segment, index) => {
      const items = segmentAnnotations(segment)
      const text = escapeHtml(segment.text || '')
      const labels = items.flatMap((annotation) => codeLabelsFor(annotation).map((code) => code.label))
      return `<article><aside>${escapeHtml(lineLabel(segment, index))}</aside><div><p>${text}</p><small>${escapeHtml(labels.join(' · '))}</small></div></article>`
    }).join('')
    const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>${escapeHtml(material.filename)} · 编码文档</title><style>body{font-family:system-ui,sans-serif;max-width:960px;margin:40px auto;color:#171716}h1{font-size:22px}article{display:grid;grid-template-columns:64px 1fr;gap:18px;padding:12px 0;border-bottom:1px solid #ddd}aside{color:#647587;font-size:12px}p{font-family:Georgia,serif;font-size:17px;line-height:1.8;margin:0}small{color:#6d5a38;font-size:12px}</style></head><body><h1>${escapeHtml(material.filename)}</h1>${rows}</body></html>`
    downloadFile(`${material.filename.replace(/\.[^.]+$/, '')}-编码.html`, html, 'text/html;charset=utf-8')
    setExportOpen(false)
  }

  function exportCsv() {
    const rows = [['材料', '定位', '原文', '编码', '编码状态', '片段备注']]
    retrievalRows.forEach(({ annotation, labels }) => {
      const linked = codeLabelsFor(annotation)
      rows.push([
        material.filename,
        annotationLocator(annotation),
        annotation.quote ?? '',
        labels.join(' · '),
        linked.map((code) => `${code.label}（${statusLabel[code.status]}）`).join(' · '),
        annotation.note,
      ])
    })
    downloadFile(`${material.filename.replace(/\.[^.]+$/, '')}-编码片段.csv`, rows.map((row) => row.map(csvCell).join(',')).join('\n'), 'text/csv;charset=utf-8')
    setExportOpen(false)
  }

  function printDocument() {
    setExportOpen(false)
    window.setTimeout(() => window.print(), 0)
  }

  return (
    <section className={`qx-reader${narrow ? ' is-narrow' : ''}${workspaceChrome ? ' is-workspace-chrome' : ''}`} data-zoom={zoom} aria-label="材料阅读台" ref={frameRef}>
      <header className={`qx-reader__bar${workspaceChrome ? ' is-workspace-chrome' : ''}`}>
        {!workspaceChrome ? (
          <>
            <button type="button" className="qx-reader__back" onClick={onBack} title="返回材料库">
              <ArrowLeftIcon size={16} aria-hidden="true" />
              材料库
            </button>
            <div className="qx-reader__identity">
              <div className="qx-reader__identity-line"><FileTextIcon size={17} aria-hidden="true" /><h2>{material.filename}</h2></div>
              <p>{identity}</p>
            </div>
          </>
        ) : null}
        {workspaceNavigation}
        <div className="qx-reader__tools">
          <div className="qx-reader__tool-group" aria-label="阅读工具">
            <button type="button" className="qx-icon-button" aria-pressed={outlineOpen} aria-controls="research-materials-outline" aria-label={outlineOpen ? '收起侧栏' : '展开侧栏'} title={outlineOpen ? '收起侧栏' : '展开侧栏'} onClick={onToggleOutline}><SidebarSimpleIcon size={17} aria-hidden="true" /></button>
            <button type="button" className="qx-icon-button" aria-pressed={searchOpen} aria-controls="research-materials-reader-search" aria-label="在材料中查找" title="查找（⌘⇧F）" onClick={onToggleSearch}><MagnifyingGlassIcon size={17} aria-hidden="true" /></button>
          </div>
          <span className="qx-reader__tool-rule" aria-hidden="true" />
          <div className="qx-reader__view-switch" role="group" aria-label="文档视图">
            <button type="button" aria-pressed={viewMode === 'source'} onClick={() => setViewMode('source')}>原文视图</button>
            <button type="button" aria-pressed={viewMode === 'coding'} onClick={() => setViewMode('coding')}>编码视图<span>{annotations.length}</span></button>
          </div>
            <button type="button" className="qx-reader__tool-button" aria-expanded={codeFilterOpen} onClick={() => setCodeFilterOpen((open) => !open)}><TagIcon size={15} aria-hidden="true" />筛选{activeCodeIds.length ? ` ${activeCodeIds.length}` : ''}</button>
          <button type="button" className={`qx-reader__tool-button${inspectorMode === 'retrieved' ? ' is-active' : ''}`} aria-pressed={inspectorMode === 'retrieved'} title="检索编码片段（⌘⇧R）" onClick={() => { setPanel('evidence'); setInspectorMode('retrieved'); setSelectedAnnotationId(null); setSelectedCodeId(null) }}><ListBulletsIcon size={15} aria-hidden="true" />检索<span>{retrievalRows.length}</span></button>
          <div className="qx-reader__export-wrap">
            <button type="button" className="qx-reader__tool-button" aria-expanded={exportOpen} onClick={() => setExportOpen((open) => !open)}><DownloadSimpleIcon size={15} aria-hidden="true" />导出</button>
            {exportOpen ? (
              <div className="qx-reader__menu qx-reader__export-menu" role="menu" aria-label="导出材料">
                <button type="button" role="menuitem" onClick={exportHtml}><FileTextIcon size={15} aria-hidden="true" />编码文档 HTML</button>
                <button type="button" role="menuitem" onClick={exportCsv}><DownloadSimpleIcon size={15} aria-hidden="true" />编码片段 CSV</button>
                <button type="button" role="menuitem" onClick={printDocument}><FileTextIcon size={15} aria-hidden="true" />打印 / 保存 PDF</button>
              </div>
            ) : null}
          </div>
          <span className="qx-reader__tool-rule" aria-hidden="true" />
          <button type="button" className="qx-icon-button" aria-label="材料档案" title="材料档案" onClick={onOpenArchive}><IdentificationCardIcon size={17} aria-hidden="true" /></button>
        </div>
      </header>

      <div className="qx-reader__coding-toolbar" aria-label="编码工具">
        <button type="button" className="qx-reader__document-path" onClick={onBack} title="切换材料"><span className="qx-reader__path-dot" aria-hidden="true" />{material.filename}<CaretDownIcon size={13} aria-hidden="true" /></button>
        <div className="qx-reader__coding-actions">
          {codingAction}
          <button type="button" className="qx-reader__coding-action" disabled={!selectedAnnotation || !onCreateCode} title={selectedAnnotation ? '为当前片段新建编码' : '先点击一条编码片段'} onClick={() => setCodeComposerOpen(true)}><PlusIcon size={15} aria-hidden="true" />新建编码</button>
          <button type="button" className="qx-reader__coding-action" disabled={!selectedAnnotation || !onCreateCode || Boolean(busyAction)} title={selectedAnnotation ? '使用原文中的词语建立代码' : '先点击一条编码片段'} onClick={() => void createInVivoCode()}><QuotesIcon size={15} aria-hidden="true" />原词编码</button>
          <button type="button" className="qx-reader__coding-action" disabled={!selectedAnnotation || !onCreateMemo} title={selectedAnnotation ? '为当前片段写分析备忘' : '先点击一条编码片段'} onClick={() => setMemoComposerOpen(true)}><NoteIcon size={15} aria-hidden="true" />备忘</button>
          <div className="qx-reader__color-wrap">
            <button type="button" className={`qx-reader__coding-action${colorPickerOpen ? ' is-active' : ''}`} disabled={!selectedCode} aria-expanded={colorPickerOpen} title={selectedCode ? '设置当前代码颜色（仅当前视图）' : '先在代码系统中选择代码'} onClick={() => setColorPickerOpen((open) => !open)}><span className="qx-reader__color-dot" style={{ '--code-color': selectedCode ? effectiveCodeColor(selectedCode, Math.max(0, visibleCodes.findIndex((item) => item.code_id === selectedCode.code_id))) : '#9aa19d' } as CSSProperties} aria-hidden="true" />颜色</button>
            {colorPickerOpen && selectedCode ? <div className="qx-reader__color-menu" role="menu" aria-label="设置代码颜色">{codePalette.map((color) => <button type="button" role="menuitem" key={color} aria-label={`设置颜色 ${color}`} className={effectiveCodeColor(selectedCode, 0) === color ? 'is-selected' : undefined} onClick={() => { setCustomCodeColors((current) => ({ ...current, [selectedCode.code_id]: color })); setColorPickerOpen(false) }}><i style={{ '--code-color': color } as CSSProperties} aria-hidden="true" /></button>)}</div> : null}
          </div>
          <button type="button" className={`qx-reader__coding-action${showHighlights ? ' is-active' : ''}`} aria-pressed={showHighlights} onClick={() => setShowHighlights((show) => !show)} title={showHighlights ? '隐藏正文高亮，保留编码条' : '显示正文高亮'}><HighlighterIcon size={15} aria-hidden="true" />高亮</button>
          <button type="button" className={`qx-reader__coding-action${showCodeNames ? ' is-active' : ''}`} aria-pressed={showCodeNames} onClick={() => setShowCodeNames((show) => !show)} title={showCodeNames ? '隐藏编码名称' : '显示编码名称'}>{showCodeNames ? <EyeIcon size={15} aria-hidden="true" /> : <EyeSlashIcon size={15} aria-hidden="true" />}代码名</button>
          <label className="qx-reader__zoom"><span>缩放</span><select aria-label="阅读缩放" value={zoom} onChange={(event) => setZoom(Number(event.target.value) as typeof zoom)}><option value={90}>90%</option><option value={100}>100%</option><option value={110}>110%</option><option value={125}>125%</option></select></label>
        </div>
        <span className="qx-reader__coding-hint"><InfoIcon size={14} aria-hidden="true" />拖选正文可建立片段标记</span>
      </div>

      {searchOpen ? (
        <div className="qx-reader__search" id="research-materials-reader-search">
          <label className="qx-reader__search-field"><MagnifyingGlassIcon size={15} aria-hidden="true" /><span className="sr-only">在材料中查找</span><input type="search" role="searchbox" aria-label="在材料中查找" value={query} placeholder="查找原文、页码或定位" autoFocus onChange={(event) => onQueryChange(event.target.value)} />{query ? <button type="button" aria-label="清除材料查找" onClick={() => onQueryChange('')}><XIcon size={13} aria-hidden="true" /></button> : null}</label>
          <span className="qx-reader__search-count">{query.trim() ? `${matchCount} 处命中` : `${totalSegmentCount} 段原文`}</span>
        </div>
      ) : null}

      {codeFilterOpen ? (
        <div className="qx-reader__code-filter" role="group" aria-label="编码筛选">
          <span>显示编码</span>
          <button type="button" className={!activeCodeIds.length ? 'is-selected' : undefined} onClick={() => setActiveCodeIds([])}>全部</button>
          {visibleCodes.length ? visibleCodes.map((code, index) => (
            <button type="button" key={code.code_id} className={activeCodeIds.includes(code.code_id) ? 'is-selected' : undefined} onClick={() => setActiveCodeIds((current) => current.includes(code.code_id) ? current.filter((id) => id !== code.code_id) : [...current, code.code_id])}><i style={{ '--code-color': effectiveCodeColor(code, index) } as CSSProperties} aria-hidden="true" />{code.label}<small>{code.annotation_ids.length}</small></button>
          )) : <em>当前材料还没有编码</em>}
        </div>
      ) : null}

      <div className={`qx-reader__body${outlineOpen ? ' is-outline-open' : ''}${inspectorMode !== 'empty' || panel !== 'evidence' ? ' has-inspector' : ''}`}>
        <aside id="research-materials-outline" className="qx-reader__sidebar" aria-label="材料导航" aria-hidden={!outlineOpen}>
          <div className="qx-reader__sidebar-tabs" role="tablist" aria-label="材料导航视图">
            <button type="button" role="tab" aria-selected={sidebarTab === 'chapters'} onClick={() => setSidebarTab('chapters')}><ListBulletsIcon size={14} aria-hidden="true" />章节</button>
            <button type="button" role="tab" aria-selected={sidebarTab === 'codes'} onClick={() => setSidebarTab('codes')}><TagIcon size={14} aria-hidden="true" />代码<span>{codes.length}</span></button>
          </div>
          {sidebarTab === 'chapters' ? (
            <nav className="qx-reader__chapter-tree" aria-label="章节导航">
              {headings.length ? headings.map(({ segment, label }) => (
                <button type="button" key={segment.segmentId} className={segment.segmentId === selectedSegmentId ? 'is-current' : undefined} title={label} tabIndex={outlineOpen ? undefined : -1} onClick={() => { onSelectSegment(segment); if (narrow) onToggleOutline() }}><span className="qx-tree-caret"><CaretRightIcon size={12} aria-hidden="true" /></span>{label}</button>
              )) : <small>解析出章节后会显示在这里。</small>}
            </nav>
          ) : (
            <div className="qx-reader__code-tree" role="tree" aria-label="代码系统">
              <div className="qx-reader__code-tree-head"><span>代码系统</span><button type="button" onClick={() => setActiveCodeIds([])} disabled={!activeCodeIds.length}>清除激活</button></div>
              {codes.length ? codes.map((code, index) => {
                const active = activeCodeIds.includes(code.code_id)
                const selected = selectedCodeId === code.code_id
                const inferredDepth = Math.max(0, code.label.split(/\s*(?:>|::|\/|›)\s*/).length - 1)
                const depth = Math.max(codeDepth(code.code_id), inferredDepth)
                return (
                  <div className={`qx-code-node${active ? ' is-active' : ''}${selected ? ' is-selected' : ''}`} key={code.code_id} role="treeitem" aria-selected={selected} style={{ '--code-depth': depth } as CSSProperties}>
                    <button type="button" className="qx-code-node__activate" aria-label={`${active ? '停用' : '激活'}代码 ${code.label}`} aria-pressed={active} onClick={() => setActiveCodeIds((current) => active ? current.filter((id) => id !== code.code_id) : [...current, code.code_id])}><span className="qx-code-node__swatch" style={{ '--code-color': effectiveCodeColor(code, index) } as CSSProperties} aria-hidden="true" /></button>
                    <button type="button" className="qx-code-node__label" onClick={() => { setSelectedCodeId(code.code_id); setInspectorMode('code') }}><span>{depth ? <CaretRightIcon size={11} aria-hidden="true" /> : null}{code.label}</span><small>{code.annotation_ids.length}</small></button>
                  </div>
                )
              }) : <p className="qx-reader__sidebar-empty">完成第一条片段标记后，代码会出现在这里。</p>}
            </div>
          )}
          <div className="qx-reader__sidebar-foot"><span>{annotations.length} 条片段标记</span><span>{codes.filter((code) => code.status === 'candidate').length} 条候选</span></div>
        </aside>

        {narrow && outlineOpen ? <button type="button" className="qx-reader__outline-scrim" aria-label="收起侧栏" onClick={onToggleOutline} /> : null}

        <main className="qx-reader__scroll" ref={scrollRef} role="region" aria-label="文档阅读器">
          {detailLoading ? <p className="qx-message" role="status"><CircleNotchIcon className="is-spinning" size={16} aria-hidden="true" />正在读取原文结构</p> : null}
          {note ? <p className={`qx-message${note.tone === 'error' ? ' is-error' : ''}`} role={note.tone === 'error' ? 'alert' : undefined}>{note.tone === 'error' ? <WarningCircleIcon size={15} aria-hidden="true" /> : null}{note.text}</p> : null}
          {localError ? <p className="qx-message is-error" role="alert"><WarningCircleIcon size={15} aria-hidden="true" />{localError}<button type="button" aria-label="关闭错误提示" onClick={() => setLocalError(null)}><XIcon size={13} aria-hidden="true" /></button></p> : null}
          <div className="qx-reader__ruler"><span>编码条</span><span>行</span><span>原文</span></div>
          <article className="qx-reader__doc">
            {segments.map((segment, index) => {
              const selected = segment.segmentId === selectedSegmentId
              const heading = segment.kind === 'heading'
              const codedAnnotations = segmentAnnotations(segment)
              const line = lineLabel(segment, index)
              return (
                <div className={`qx-segment${selected ? ' is-selected' : ''}${heading ? ' is-heading' : ''}${codedAnnotations.length && viewMode === 'coding' ? ' is-coded' : ''}`} key={segment.segmentId} data-segment-id={segment.segmentId} aria-current={selected ? 'location' : undefined} ref={(element) => registerSegment(segment.segmentId, element)} onClick={() => locateFromPointer(segment)} onContextMenu={(event) => openContextMenu(event, segment.segmentId)}>
                  <aside className="qx-segment__rail" aria-label={codedAnnotations.length ? '此段编码条' : undefined}>
                    {viewMode === 'coding' ? codedAnnotations.flatMap((annotation) => {
                      const linked = codeLabelsFor(annotation)
                      const displayCodes = linked.length ? linked : [{ code_id: `annotation:${annotation.annotation_id}`, label: '待命名标记', status: 'candidate' as const, annotation_ids: [] } as AnalysisCode]
                      return displayCodes.map((code, codeIndex) => {
                        const codeIndexGlobal = Math.max(0, visibleCodes.findIndex((item) => item.code_id === code.code_id))
                        const current = isCurrentAnnotation(annotation, selectedAnnotationId, hoveredAnnotationId)
                        return <button type="button" key={`${annotation.annotation_id}:${code.code_id}`} className={`qx-stripe${code.status === 'candidate' ? ' is-candidate' : ''}${code.status === 'rejected' ? ' is-rejected' : ''}${current ? ' is-current' : ''}`} style={{ '--code-color': effectiveCodeColor(code, codeIndexGlobal >= 0 ? codeIndexGlobal : codeIndex) } as CSSProperties} aria-label={`${code.label} · ${statusLabel[code.status]}`} title={`${code.label} · ${statusLabel[code.status]} · ${annotationLocator(annotation)}`} onMouseEnter={() => setHoveredAnnotationId(annotation.annotation_id)} onMouseLeave={() => setHoveredAnnotationId(null)} onClick={(event) => { event.stopPropagation(); selectAnnotation(annotation, segment) }} onDoubleClick={(event) => { event.stopPropagation(); selectAnnotation(annotation, segment); if (onCreateMemo) setMemoComposerOpen(true) }} onContextMenu={(event) => openContextMenu(event, segment.segmentId, annotation.annotation_id)}><span className="qx-stripe__bar" aria-hidden="true" />{showCodeNames ? <span className="qx-stripe__label">{code.label}</span> : null}</button>
                      })
                    }) : null}
                    {codedAnnotations.some((annotation) => memos.some((memo) => memo.annotation_ids.includes(annotation.annotation_id))) ? <button type="button" className="qx-segment__memo-marker" aria-label="查看此段备忘" title="此段有备忘" onClick={(event) => { event.stopPropagation(); selectAnnotation(codedAnnotations[0], segment); setInspectorMode('evidence') }}><NoteIcon size={14} aria-hidden="true" /></button> : null}
                  </aside>
                  <button type="button" className="qx-segment__line" aria-label={`定位到${formatMaterialLocator(segment.locator)}`} title={formatMaterialLocator(segment.locator)} onClick={(event) => { event.stopPropagation(); onSelectSegment(segment) }}>{line}</button>
                  <div className="qx-segment__text">
                    {heading ? <h3 onMouseUp={(event) => captureFromParagraph(segment, event)}>{renderCodedText(segment, codedAnnotations)}</h3> : <p onMouseUp={(event) => captureFromParagraph(segment, event)}>{renderCodedText(segment, codedAnnotations)}</p>}
                    <span className="qx-segment__source-label">{formatMaterialLocator(segment.locator)}</span>
                  </div>
                </div>
              )
            })}
            {!segments.length && !detailLoading ? <p className="qx-reader__no-results">{query.trim() ? '没有匹配的原文。换个词试试。' : '暂时没有可展示的片段。'}</p> : null}
          </article>
          {pageCount > 1 ? <footer className="qx-reader__pagination" aria-label="文档分页"><button type="button" aria-label="上一页" disabled={page === 0} onClick={() => onPageChange(Math.max(0, page - 1))}>上一页</button><span>第 {page + 1} / {pageCount} 页</span><button type="button" aria-label="下一页" disabled={page >= pageCount - 1} onClick={() => onPageChange(Math.min(pageCount - 1, page + 1))}>下一页</button></footer> : null}
        </main>

        <aside className={`qx-reader__inspector${agentPanel ? ' is-integrated' : ''}`} aria-label={agentPanel ? '编码协作侧栏' : inspectorMode === 'retrieved' ? '检索编码片段' : '编码证据检查器'}>
          {agentPanel || analysisPanel ? <div className="qx-reader__panel-tabs" role="tablist" aria-label="编码协作工具">
            {(['evidence', 'analysis', 'agent'] as const).filter((id) => id === 'evidence' || (id === 'analysis' ? analysisPanel : agentPanel)).map((id) => <button key={id} type="button" role="tab" id={`coding-tab-${id}`} aria-controls={`coding-panel-${id}`} aria-selected={panel === id} onClick={() => setPanel(id)}>{id === 'evidence' ? '证据' : id === 'analysis' ? '分析' : 'Agent'}</button>)}
          </div> : null}
          <div role="tabpanel" id="coding-panel-evidence" aria-labelledby={agentPanel || analysisPanel ? "coding-tab-evidence" : undefined} className="qx-reader__panel-content" hidden={panel !== 'evidence'} aria-label={inspectorMode === 'retrieved' ? '检索编码片段' : '编码证据检查器'}>
          {inspectorMode === 'retrieved' ? (
            <div className="qx-retrieved">
              <header className="qx-inspector__head"><div><span className="qx-eyebrow">RETRIEVED SEGMENTS</span><strong>检索编码片段</strong><small>{retrievalRows.length} 条结果 · 点击来源回到原文</small></div><button type="button" className="qx-icon-button" aria-label="关闭检索结果" onClick={() => setInspectorMode('empty')}><XIcon size={16} aria-hidden="true" /></button></header>
              <div className="qx-retrieved__controls"><label><span className="sr-only">结果排序</span><select value={retrievalSort} onChange={(event) => setRetrievalSort(event.target.value as typeof retrievalSort)}><option value="document">按材料顺序</option><option value="code">按代码</option></select></label><div role="group" aria-label="结果视图"><button type="button" aria-pressed={retrievalLayout === 'list'} onClick={() => setRetrievalLayout('list')}><ListBulletsIcon size={14} aria-hidden="true" /></button><button type="button" aria-pressed={retrievalLayout === 'table'} onClick={() => setRetrievalLayout('table')}><DotsThreeIcon size={14} aria-hidden="true" /></button></div></div>
              {retrievalRows.length ? <div className={`qx-retrieved__list${retrievalLayout === 'table' ? ' is-table' : ''}`}>{retrievalRows.map((row) => <article key={row.annotation.annotation_id}><button type="button" className="qx-retrieved__source" onClick={() => jumpToRetrieved(row)}><span>{annotationLocator(row.annotation)}</span><ArrowSquareOutIcon size={14} aria-hidden="true" /></button><blockquote>{row.annotation.quote || row.segment.text}</blockquote><div className="qx-retrieved__codes">{row.labels.length ? row.labels.map((label) => <span key={label}>{label}</span>) : <span className="is-muted">待命名标记</span>}</div><small>{row.annotation.note || '没有片段备注'}</small></article>)}</div> : <p className="qx-reader__sidebar-empty">当前筛选没有可检索的编码片段。</p>}
            </div>
          ) : inspectorMode === 'code' && selectedCode ? (
            <div className="qx-code-inspector"><header className="qx-inspector__head"><div><span className="qx-eyebrow">CODE SYSTEM</span><strong>{selectedCode.label}</strong><small>{selectedCode.annotation_ids.length} 条片段 · {statusLabel[selectedCode.status]}</small></div><button type="button" className="qx-icon-button" aria-label="关闭代码详情" onClick={() => setInspectorMode('empty')}><XIcon size={16} aria-hidden="true" /></button></header><section className="qx-inspector__section"><h3>代码定义</h3><p>{selectedCode.definition || '尚未填写代码定义。'}</p><dl><div><dt>来源</dt><dd>{selectedCode.source === 'agent' ? 'Agent 候选' : '研究者建立'}</dd></div><div><dt>理由</dt><dd>{selectedCode.rationale || '未记录'}</dd></div></dl></section>{selectedCodebook ? <section className="qx-inspector__section"><h3>纳入 / 排除规则</h3><div className="qx-rule-list"><strong>纳入</strong>{selectedCodebook.inclusion_rules.length ? <ul>{selectedCodebook.inclusion_rules.map((rule) => <li key={rule}>{rule}</li>)}</ul> : <span>未设置</span>}<strong>排除</strong>{selectedCodebook.exclusion_rules.length ? <ul>{selectedCodebook.exclusion_rules.map((rule) => <li key={rule}>{rule}</li>)}</ul> : <span>未设置</span>}</div></section> : null}<section className="qx-inspector__section"><h3>相关片段</h3><div className="qx-code-inspector__links">{annotations.filter((annotation) => selectedCode.annotation_ids.includes(annotation.annotation_id)).map((annotation) => <button type="button" key={annotation.annotation_id} onClick={() => { const segment = allSegments.find((item) => item.segmentId === annotation.segment_id); selectAnnotation(annotation, segment) }}>{annotation.quote || '整段标记'}<small>{annotationLocator(annotation)}</small></button>)}</div></section>{selectedCode.status === 'candidate' && onDecideCode ? <footer className="qx-inspector__actions"><button type="button" disabled={Boolean(busyAction)} onClick={() => void decideCode(selectedCode, 'rejected')}><XCircleIcon size={15} aria-hidden="true" />拒绝候选</button><button type="button" className="is-primary" disabled={Boolean(busyAction)} onClick={() => void decideCode(selectedCode, 'confirmed')}><CheckIcon size={15} aria-hidden="true" />确认编码</button></footer> : null}</div>
          ) : selectedAnnotation ? (
            <div className="qx-evidence-inspector">
              <header className="qx-inspector__head">
                <div>
                  <span className="qx-eyebrow">EVIDENCE INSPECTOR</span>
                  <strong>编码证据</strong>
                  <small>{annotationLocator(selectedAnnotation)}</small>
                </div>
                <button type="button" className="qx-icon-button" aria-label="关闭编码证据" onClick={() => { setInspectorMode('empty'); setSelectedAnnotationId(null) }}><XIcon size={16} aria-hidden="true" /></button>
              </header>
              <section className="qx-inspector__quote">
                <blockquote>{selectedAnnotation.quote || '整段标记'}</blockquote>
                <button type="button" onClick={() => void copyLocator(selectedAnnotation, null)}><CopyIcon size={14} aria-hidden="true" />{copied ? '已复制定位' : '复制定位'}</button>
              </section>
              <section className="qx-inspector__section">
                <h3>代码与状态</h3>
                <div className="qx-reader__inspector-codes">
                  {codeLabelsFor(selectedAnnotation).length ? codeLabelsFor(selectedAnnotation).map((code) => (
                    <button type="button" key={code.code_id} className={`${code.status === 'candidate' ? 'is-candidate' : ''}${selectedCodeId === code.code_id ? ' is-selected' : ''}`} onClick={() => { setSelectedCodeId(code.code_id); setInspectorMode('code') }}>
                      <i style={{ '--code-color': effectiveCodeColor(code, Math.max(0, visibleCodes.findIndex((item) => item.code_id === code.code_id))) } as CSSProperties} aria-hidden="true" />
                      {code.label}<small>{statusLabel[code.status]}</small>
                    </button>
                  )) : <span className="is-empty">待命名标记</span>}
                </div>
              </section>
              <section className="qx-inspector__section">
                <h3>代码定义 / 理由</h3>
                {codeLabelsFor(selectedAnnotation).length ? codeLabelsFor(selectedAnnotation).map((code) => (
                  <div className="qx-inspector__code-detail" key={code.code_id}><strong>{code.label}</strong><p>{code.definition || '尚未填写定义。'}</p><small>{code.rationale || '未记录理由。'}</small></div>
                )) : <p className="qx-inspector__muted">尚未关联代码。</p>}
              </section>
              <section className="qx-inspector__section">
                <h3>研究者备注</h3>
                <p>{selectedAnnotation.note || '没有片段备注。'}</p>
                {selectedAnnotation.reflection ? <div className="qx-inspector__reflection"><span>研究者反思</span>{selectedAnnotation.reflection}</div> : null}
              </section>
              <section className="qx-inspector__section">
                <h3>备忘</h3>
                {selectedMemos.length ? selectedMemos.map((memo) => (
                  <article className="qx-memo-card" key={memo.memo_id}>
                    <header><span>{memoKindLabel[memo.memo_kind]}</span><small>{statusLabel[memo.status]}</small></header>
                    <strong>{memo.title}</strong>
                    <p>{memo.content}</p>
                    {memo.status === 'candidate' && onDecideMemo ? <footer><button type="button" disabled={Boolean(busyAction)} onClick={() => void decideMemo(memo, 'rejected')}>暂不采用</button><button type="button" disabled={Boolean(busyAction)} onClick={() => void decideMemo(memo, 'confirmed')}>确认备忘</button></footer> : null}
                  </article>
                )) : <p className="qx-inspector__muted">还没有挂接到此片段的备忘。</p>}
              </section>
              <section className="qx-inspector__section">
                <h3>来源定位</h3>
                <dl className="qx-inspector__locator">
                  <div><dt>材料</dt><dd>{material.filename}</dd></div>
                  <div><dt>位置</dt><dd>{annotationLocator(selectedAnnotation)}</dd></div>
                  <div><dt>来源</dt><dd>{selectedAnnotation.source_available ? '可追溯' : `不可用：${selectedAnnotation.unavailable_reason || '未说明'}`}</dd></div>
                </dl>
              </section>
              <footer className="qx-inspector__actions">
                <button type="button" disabled={!onCreateCode} onClick={() => setCodeComposerOpen(true)}><PlusIcon size={15} aria-hidden="true" />建立编码</button>
                <button type="button" disabled={!onCreateMemo} onClick={() => setMemoComposerOpen(true)}><NoteIcon size={15} aria-hidden="true" />写备忘</button>
              </footer>
            </div>
          ) : (
            <div className="qx-inspector__empty"><InfoIcon size={24} aria-hidden="true" /><strong>选择一条编码证据</strong><p>点击正文中的编码条或高亮文字，这里会显示代码定义、研究者备注、备忘和来源定位。</p><span>Esc 关闭面板 · ⌘⇧R 打开检索结果</span></div>
          )}
          </div>
          {analysisPanel ? <div role="tabpanel" id="coding-panel-analysis" aria-labelledby="coding-tab-analysis" className="qx-reader__panel-content" hidden={panel !== 'analysis'}>{analysisPanel}</div> : null}
          {agentPanel ? <div role="tabpanel" id="coding-panel-agent" aria-labelledby="coding-tab-agent" className="qx-reader__panel-content qx-reader__agent-panel" hidden={panel !== 'agent'}>{agentPanel}</div> : null}
        </aside>
      </div>

      {codeComposerOpen && selectedAnnotation ? <div className="qx-reader__composer" role="dialog" aria-label="新建编码"><header><strong>为片段建立编码</strong><button type="button" className="qx-icon-button" aria-label="关闭新建编码" onClick={() => setCodeComposerOpen(false)}><XIcon size={16} aria-hidden="true" /></button></header><blockquote>{selectedAnnotation.quote || '整段标记'}</blockquote><form onSubmit={(event) => void submitCode(event)}><label>代码名称<input value={newCodeLabel} onChange={(event) => setNewCodeLabel(event.target.value)} autoFocus placeholder="例如：照护责任重组" /></label><label>代码定义<textarea value={newCodeDefinition} onChange={(event) => setNewCodeDefinition(event.target.value)} placeholder="什么情况下纳入这个代码？" rows={3} /></label><label>建立理由<textarea value={newCodeRationale} onChange={(event) => setNewCodeRationale(event.target.value)} placeholder="为什么这段证据支持这个代码？" rows={2} /></label><footer><button type="button" onClick={() => setCodeComposerOpen(false)}>取消</button><button type="submit" className="is-primary" disabled={!newCodeLabel.trim() || Boolean(busyAction)}>{busyAction === 'create-code' ? '保存中…' : '保存编码'}</button></footer></form></div> : null}
      {memoComposerOpen ? <div className="qx-reader__composer" role="dialog" aria-label="写分析备忘"><header><strong>{selectedAnnotation ? '为片段写分析备忘' : '写分析备忘'}</strong><button type="button" className="qx-icon-button" aria-label="关闭写备忘" onClick={() => setMemoComposerOpen(false)}><XIcon size={16} aria-hidden="true" /></button></header>{selectedAnnotation ? <blockquote>{selectedAnnotation.quote || '整段标记'}</blockquote> : null}<form onSubmit={(event) => void submitMemo(event)}><label>标题<input value={newMemoTitle} onChange={(event) => setNewMemoTitle(event.target.value)} autoFocus placeholder="例如：竞争解释" /></label><label>类型<select value={newMemoKind} onChange={(event) => setNewMemoKind(event.target.value as AnalysisMemo['memo_kind'])}>{Object.entries(memoKindLabel).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label>内容<textarea value={newMemoContent} onChange={(event) => setNewMemoContent(event.target.value)} placeholder="记录你的分析、反思或方法判断" rows={6} /></label><footer><button type="button" onClick={() => setMemoComposerOpen(false)}>取消</button><button type="submit" className="is-primary" disabled={!newMemoTitle.trim() || !newMemoContent.trim() || Boolean(busyAction)}>{busyAction === 'create-memo' ? '保存中…' : '保存备忘'}</button></footer></form></div> : null}

      {contextMenu ? <div className="qx-reader__context-menu qx-reader__menu" role="menu" style={{ left: contextMenu.x, top: contextMenu.y }}><button type="button" role="menuitem" onClick={() => { const annotation = contextMenu.annotationId ? annotations.find((item) => item.annotation_id === contextMenu.annotationId) : null; const segment = segments.find((item) => item.segmentId === contextMenu.segmentId); if (annotation) selectAnnotation(annotation, segment); setContextMenu(null) }}><InfoIcon size={15} aria-hidden="true" />查看证据</button><button type="button" role="menuitem" disabled={!contextMenu.annotationId || !onCreateCode} onClick={() => { const annotation = annotations.find((item) => item.annotation_id === contextMenu.annotationId); if (annotation) { selectAnnotation(annotation, segments.find((item) => item.segmentId === annotation.segment_id)); setCodeComposerOpen(true) } setContextMenu(null) }}><PlusIcon size={15} aria-hidden="true" />建立编码</button><button type="button" role="menuitem" onClick={() => void copyLocator(contextMenu.annotationId ? annotations.find((item) => item.annotation_id === contextMenu.annotationId) ?? null : null, segments.find((item) => item.segmentId === contextMenu.segmentId) ?? null)}><CopyIcon size={15} aria-hidden="true" />复制定位</button></div> : null}
    </section>
  )
}
