import {
  ArrowClockwiseIcon,
  CheckCircleIcon,
  CircleNotchIcon,
  FilePlusIcon,
  FileTextIcon,
  MagnifyingGlassIcon,
  TrashIcon,
  WarningCircleIcon,
  XIcon,
} from '@phosphor-icons/react'
import { useEffect, useRef, useState, type ChangeEvent, type MouseEvent } from 'react'

import type {
  ConfigureCodebookEntryInput,
  CreateAnalysisCodeInput,
  CreateAnalysisMemoLinkInput,
  CreateAnalysisMemoInput,
  CreateAnalysisThemeInput,
  CreateCaseComparisonInput,
  ResearchAnalysisSnapshot,
  SaveAnalysisCaseProfileInput,
  SaveCaseThemeMatrixCellInput,
  SetQualitativeMethodInput,
  TransitionCodebookEntryInput,
} from './researchAnalysisModel'
import {
  attachAnalysisMemo,
  configureCodebookEntry,
  confirmAnalysisTheme,
  createAnalysisAnnotation,
  createAnalysisCode,
  createAnalysisMemo,
  createAnalysisTheme,
  createCaseComparison,
  decideAnalysisCode,
  decideAnalysisMemo,
  decideCaseComparison,
  getAnalysisSnapshot,
  saveAnalysisCaseProfile,
  saveCaseThemeMatrixCell,
  setQualitativeMethod,
  transitionCodebookEntry,
} from './researchAnalysisApi'
import {
  ResearchAnalysisWorkspace,
} from './ResearchAnalysisWorkspace'
import { MediaTranscriptWorkspace } from './MediaTranscriptWorkspace'
import { ResearchCyclePanel } from './ResearchCyclePanel'
import { getResearchCycleSnapshot } from './researchAnalysisApi'
import type { ResearchCycleSnapshot } from './researchCycleModel'
import { ProfessionalMaterialArchivePanel } from './ProfessionalMaterialArchive'
import type { ResearchAnalysisDecision } from './ResearchAnalysisCandidateCard'
import {
  deleteResearchMaterial,
  getResearchMaterial,
  getResearchMaterialSegment,
  listResearchMaterials,
  reparseResearchMaterial,
  uploadResearchMaterial,
} from './researchMaterialsApi'
import {
  formatMaterialLocator,
  formatMaterialSize,
  isMediaResearchMaterial,
  isSupportedResearchMaterialFile,
  materialKindLabel,
  materialMediaLabel,
  materialStatusLabel,
  RESEARCH_MATERIAL_ACCEPT,
  type ResearchMaterial,
  type ResearchMaterialKind,
  type ResearchMaterialSegment,
} from './researchMaterialsModel'
import {
  selectionDraftFromDomRange,
  type ResearchMaterialSelectionDraft,
} from './researchMaterialSelection'
import './research-materials.css'

const MATERIAL_KINDS: readonly ResearchMaterialKind[] = [
  'paper',
  'interview_transcript',
  'observation_record',
  'field_note',
  'other',
]

const READER_PAGE_SIZE = 24

type ResearchMaterialsPanelProps = {
  readonly taskId: string
  readonly onClose?: () => void
  readonly presentation?: 'dialog' | 'workspace'
  readonly onMaterialDeleted?: (materialId: string) => void
  readonly initialMaterialId?: string | null
  readonly initialSegmentId?: string | null
  readonly initialParseId?: string | null
  readonly initialDetailMode?: 'source' | 'analysis'
  readonly analysisRefreshKey?: number
  readonly onWorkspaceLocationChange?: (location: {
    readonly mode: 'source' | 'analysis'
    readonly materialId: string | null
    readonly parseId: string | null
    readonly segmentId: string | null
  }) => void
}

function materialStatusIcon(status: ResearchMaterial['status']) {
  if (status === 'processing') return <CircleNotchIcon className="research-materials__status-icon is-processing" size={15} aria-hidden="true" />
  if (status === 'failed') return <WarningCircleIcon className="research-materials__status-icon is-failed" size={15} aria-hidden="true" />
  if (status === 'ready') return <CheckCircleIcon className="research-materials__status-icon is-ready" size={15} aria-hidden="true" />
  return <FileTextIcon className="research-materials__status-icon" size={15} aria-hidden="true" />
}

function formatUpdatedAt(value: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric' }).format(date)
}

function SegmentCard({
  segment,
  selected,
  onTextSelection,
}: {
  segment: ResearchMaterialSegment
  selected: boolean
  onTextSelection: (segment: ResearchMaterialSegment, container: HTMLParagraphElement, range: Range) => void
}) {
  function handleMouseUp(event: MouseEvent<HTMLParagraphElement>) {
    const selection = window.getSelection()
    if (!selection || selection.rangeCount !== 1 || selection.isCollapsed) return
    onTextSelection(segment, event.currentTarget, selection.getRangeAt(0))
  }

  return (
    <article className={`research-materials__segment${selected ? ' is-selected' : ''}${segment.kind === 'heading' ? ' is-heading' : ''}`} data-segment-id={segment.segmentId}>
      <div className="research-materials__segment-meta">
        <span>{formatMaterialLocator(segment.locator)}</span>
        <small>{segment.kind === 'heading' ? '标题' : '正文'}</small>
      </div>
      <p onMouseUp={handleMouseUp}>{segment.text || '此片段没有可显示的正文。'}</p>
    </article>
  )
}

export function ResearchMaterialsPanel({ taskId, onClose, presentation = 'dialog', onMaterialDeleted, initialMaterialId = null, initialSegmentId = null, initialParseId = null, initialDetailMode = 'source', analysisRefreshKey = 0, onWorkspaceLocationChange }: ResearchMaterialsPanelProps) {
  const [materials, setMaterials] = useState<ResearchMaterial[]>([])
  const [selectedMaterial, setSelectedMaterial] = useState<ResearchMaterial | null>(null)
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(initialSegmentId)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [busyMaterialId, setBusyMaterialId] = useState<string | null>(null)
  const [kind, setKind] = useState<ResearchMaterialKind>('paper')
  const [error, setError] = useState<string | null>(null)
  const [uploadNotice, setUploadNotice] = useState<string | null>(null)
  const [selectionDraft, setSelectionDraft] = useState<ResearchMaterialSelectionDraft | null>(null)
  const [selectionNotice, setSelectionNotice] = useState<string | null>(null)
  const [annotationKind, setAnnotationKind] = useState<'descriptive' | 'researcher_reflection'>('descriptive')
  const [annotationNote, setAnnotationNote] = useState('')
  const [annotationReflection, setAnnotationReflection] = useState('')
  const [annotationCaseLabel, setAnnotationCaseLabel] = useState('')
  const [annotationObservedAt, setAnnotationObservedAt] = useState('')
  const [detailMode, setDetailMode] = useState<'source' | 'analysis' | 'archive'>(initialDetailMode)
  const [readerPage, setReaderPage] = useState(0)
  const [readerQuery, setReaderQuery] = useState('')
  const [readerFilter, setReaderFilter] = useState<'all' | 'headings'>('all')
  const [mediaLocation, setMediaLocation] = useState<{ versionId: string | null; segmentId: string | null } | null>(null)
  const [analysisSnapshot, setAnalysisSnapshot] = useState<ResearchAnalysisSnapshot | null>(null)
  const [analysisLoading, setAnalysisLoading] = useState(true)
  const [analysisError, setAnalysisError] = useState<string | null>(null)
  const [analysisNotice, setAnalysisNotice] = useState<string | null>(null)
  const [researchCycle, setResearchCycle] = useState<ResearchCycleSnapshot | null>(null)
  const [cycleLoading, setCycleLoading] = useState(false)
  const [cycleError, setCycleError] = useState<string | null>(null)
  const [savingAnnotation, setSavingAnnotation] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const materialsLoadGeneration = useRef(0)
  const materialsLoadAbortController = useRef<AbortController | null>(null)
  const materialDetailGeneration = useRef(0)
  const materialDetailAbortController = useRef<AbortController | null>(null)
  const segmentGeneration = useRef(0)
  const segmentAbortController = useRef<AbortController | null>(null)
  const analysisAbortController = useRef<AbortController | null>(null)
  const cycleAbortController = useRef<AbortController | null>(null)
  const analysisLoadGeneration = useRef(0)
  const initialSelectionApplied = useRef(false)
  const segmentButtonRefs = useRef(new Map<string, HTMLButtonElement>())
  const scrolledCitationTarget = useRef<string | null>(null)

  async function loadMaterials(signal?: AbortSignal) {
    const requestGeneration = ++materialsLoadGeneration.current
    setLoading(true)
    setError(null)
    try {
      const result = await listResearchMaterials(taskId, signal)
      if (signal?.aborted || requestGeneration !== materialsLoadGeneration.current) return
      setMaterials(result.items.filter((item) => item.status !== 'deleted'))
    } catch (cause: unknown) {
      if (
        (cause as { name?: string } | null)?.name !== 'AbortError'
        && !signal?.aborted
        && requestGeneration === materialsLoadGeneration.current
      ) {
        setError(cause instanceof Error ? cause.message : '研究材料暂时无法加载。')
      }
    } finally {
      if (!signal?.aborted && requestGeneration === materialsLoadGeneration.current) setLoading(false)
    }
  }

  async function loadAnalysis(signal?: AbortSignal) {
    const requestGeneration = ++analysisLoadGeneration.current
    setAnalysisLoading(true)
    setAnalysisError(null)
    try {
      const result = await getAnalysisSnapshot(taskId, signal)
      if (signal?.aborted || requestGeneration !== analysisLoadGeneration.current) return
      setAnalysisSnapshot(result)
    } catch (cause: unknown) {
      if (
        (cause as { name?: string } | null)?.name !== 'AbortError'
        && !signal?.aborted
        && requestGeneration === analysisLoadGeneration.current
      ) setAnalysisError(cause instanceof Error ? cause.message : '质性分析记录暂时无法加载。')
    } finally {
      if (!signal?.aborted && requestGeneration === analysisLoadGeneration.current) setAnalysisLoading(false)
    }
  }

  useEffect(() => {
    const controller = new AbortController()
    materialsLoadAbortController.current?.abort()
    materialsLoadAbortController.current = controller
    void loadMaterials(controller.signal)
    return () => {
      controller.abort()
      if (materialsLoadAbortController.current === controller) materialsLoadAbortController.current = null
      materialsLoadGeneration.current += 1
    }
  }, [taskId])

  useEffect(() => {
    const controller = new AbortController()
    analysisAbortController.current?.abort()
    analysisAbortController.current = controller
    void loadAnalysis(controller.signal)
    return () => {
      controller.abort()
      if (analysisAbortController.current === controller) analysisAbortController.current = null
      analysisLoadGeneration.current += 1
    }
  }, [taskId, analysisRefreshKey])

  useEffect(() => {
    if (detailMode !== 'analysis') return
    const controller = new AbortController()
    cycleAbortController.current?.abort()
    cycleAbortController.current = controller
    setCycleLoading(true)
    setCycleError(null)
    void getResearchCycleSnapshot(taskId, controller.signal).then((snapshot) => {
      if (!controller.signal.aborted) setResearchCycle(snapshot)
    }).catch((cause: unknown) => {
      if ((cause as { name?: string } | null)?.name !== 'AbortError' && !controller.signal.aborted) {
        setCycleError(cause instanceof Error ? cause.message : '研究循环暂时无法加载。')
      }
    }).finally(() => {
      if (!controller.signal.aborted) setCycleLoading(false)
    })
    return () => {
      controller.abort()
      if (cycleAbortController.current === controller) cycleAbortController.current = null
    }
  }, [analysisSnapshot, detailMode, taskId])

  useEffect(() => {
    return () => {
      materialsLoadAbortController.current?.abort()
      materialDetailAbortController.current?.abort()
      segmentAbortController.current?.abort()
      analysisAbortController.current?.abort()
      cycleAbortController.current?.abort()
      materialsLoadGeneration.current += 1
      materialDetailGeneration.current += 1
      segmentGeneration.current += 1
      analysisLoadGeneration.current += 1
    }
  }, [])

  useEffect(() => {
    materialDetailAbortController.current?.abort()
    segmentAbortController.current?.abort()
    materialDetailGeneration.current += 1
    segmentGeneration.current += 1
    setSelectedMaterial(null)
    setSelectedSegmentId(null)
    setDetailMode(initialDetailMode)
    setReaderPage(0)
    setReaderQuery('')
    setReaderFilter('all')
    setMediaLocation(null)
    setAnalysisSnapshot(null)
    setResearchCycle(null)
    setCycleError(null)
    setAnalysisNotice(null)
    clearSelectionDraft()
  }, [initialDetailMode, taskId])

  useEffect(() => {
    initialSelectionApplied.current = false
    scrolledCitationTarget.current = null
  }, [taskId, initialMaterialId, initialSegmentId, initialParseId])

  useEffect(() => {
    if (!initialMaterialId || initialSelectionApplied.current || !materials.length) return
    const target = materials.find((item) => item.materialId === initialMaterialId)
    if (target) {
      initialSelectionApplied.current = true
      void selectMaterial(target, initialParseId, initialSegmentId)
    }
  }, [initialMaterialId, initialParseId, initialSegmentId, materials])

  useEffect(() => {
    // A material workbench opens on usable content; an empty detail pane makes
    // the library look broken when the research already has imported files.
    if (initialMaterialId || !materials.length || selectedMaterial || detailLoading) return
    void selectMaterial(materials[0])
  }, [detailLoading, initialMaterialId, materials, selectedMaterial])

  useEffect(() => {
    if (
      detailLoading
      || !initialMaterialId
      || !initialSegmentId
      || selectedMaterial?.materialId !== initialMaterialId
      || selectedSegmentId !== initialSegmentId
    ) return
    const targetKey = `${taskId}:${initialMaterialId}:${initialParseId ?? ''}:${initialSegmentId}`
    if (scrolledCitationTarget.current === targetKey) return
    const target = segmentButtonRefs.current.get(initialSegmentId)
    if (!target || typeof target.scrollIntoView !== 'function') return
    const reducedMotion = typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    target.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'center' })
    scrolledCitationTarget.current = targetKey
  }, [detailLoading, initialMaterialId, initialParseId, initialSegmentId, readerPage, selectedMaterial, selectedSegmentId, taskId])

  useEffect(() => {
    if (detailLoading || !initialSegmentId || selectedMaterial?.materialId !== initialMaterialId) return
    const targetIndex = (selectedMaterial.segments ?? []).findIndex((segment) => segment.segmentId === initialSegmentId)
    if (targetIndex >= 0) setReaderPage(Math.floor(targetIndex / READER_PAGE_SIZE))
  }, [detailLoading, initialMaterialId, initialSegmentId, selectedMaterial])

  useEffect(() => {
    if (!onWorkspaceLocationChange) return
    if (detailMode === 'archive') return
    if (initialMaterialId && !selectedMaterial) return
    const selectedSegment = selectedMaterial?.segments?.find((segment) => segment.segmentId === selectedSegmentId)
    const mediaSelected = selectedMaterial ? isMediaResearchMaterial(selectedMaterial) : false
    onWorkspaceLocationChange({
      mode: detailMode,
      materialId: selectedMaterial?.materialId ?? null,
      parseId: mediaSelected
        ? mediaLocation?.versionId ?? null
        : selectedSegment?.parseId
          ?? (selectedMaterial?.materialId === initialMaterialId ? initialParseId : null),
      segmentId: mediaSelected ? mediaLocation?.segmentId ?? null : selectedSegmentId,
    })
  }, [detailMode, initialMaterialId, initialParseId, mediaLocation, onWorkspaceLocationChange, selectedMaterial, selectedSegmentId])

  async function selectMaterial(material: ResearchMaterial, parseId: string | null = null, segmentId: string | null = null) {
    const requestGeneration = ++materialDetailGeneration.current
    materialDetailAbortController.current?.abort()
    const controller = new AbortController()
    materialDetailAbortController.current = controller
    segmentAbortController.current?.abort()
    segmentGeneration.current += 1
    if (
      selectionDraft
      && (selectionDraft.materialId !== material.materialId || (parseId && selectionDraft.parseId !== parseId))
    ) clearSelectionDraft()
    setSelectedMaterial(material)
    setMediaLocation(null)
    setSelectedSegmentId(segmentId)
    setReaderPage(segmentId && material.segments ? Math.floor(Math.max(0, material.segments.findIndex((item) => item.segmentId === segmentId)) / READER_PAGE_SIZE) : 0)
    setReaderQuery('')
    setReaderFilter('all')
    if (material.segments && !parseId) {
      setDetailLoading(false)
      if (materialDetailAbortController.current === controller) materialDetailAbortController.current = null
      return
    }
    setDetailLoading(true)
    setError(null)
    try {
      const detail = await getResearchMaterial(taskId, material.materialId, controller.signal, parseId)
      if (controller.signal.aborted || requestGeneration !== materialDetailGeneration.current) return
      setSelectedMaterial(detail)
      // Historical citation views must not replace the library's current
      // parse metadata with an older snapshot.
      if (!parseId) setMaterials((current) => current.map((item) => item.materialId === detail.materialId ? { ...item, ...detail } : item))
    } catch (cause: unknown) {
      if (
        (cause as { name?: string } | null)?.name !== 'AbortError'
        && !controller.signal.aborted
        && requestGeneration === materialDetailGeneration.current
      ) {
        setError(cause instanceof Error ? cause.message : '研究材料详情暂时无法加载。')
      }
    } finally {
      if (!controller.signal.aborted && requestGeneration === materialDetailGeneration.current) setDetailLoading(false)
      if (materialDetailAbortController.current === controller) materialDetailAbortController.current = null
    }
  }

  async function selectSegment(segment: ResearchMaterialSegment) {
    const requestGeneration = ++segmentGeneration.current
    segmentAbortController.current?.abort()
    setSelectedSegmentId(segment.segmentId)
    if (selectionDraft && selectionDraft.segmentId !== segment.segmentId) clearSelectionDraft()
    if (!selectedMaterial) return
    // A detail response may omit segment text for large documents. Fetching the
    // exact segment keeps the citation jump truthful instead of showing a
    // placeholder excerpt that looks like source content.
    if (segment.text) return
    const materialId = selectedMaterial.materialId
    const controller = new AbortController()
    segmentAbortController.current = controller
    try {
      const exact = await getResearchMaterialSegment(taskId, materialId, segment.segmentId, controller.signal, segment.parseId)
      if (controller.signal.aborted || requestGeneration !== segmentGeneration.current) return
      setSelectedMaterial((current) => current?.materialId === materialId ? {
        ...current,
        segments: current.segments?.map((item) => item.segmentId === exact.segmentId ? exact : item),
      } : current)
    } catch (cause: unknown) {
      if (
        (cause as { name?: string } | null)?.name !== 'AbortError'
        && !controller.signal.aborted
        && requestGeneration === segmentGeneration.current
      ) setError('原文片段暂时无法加载。')
    } finally {
      if (segmentAbortController.current === controller) segmentAbortController.current = null
    }
  }

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setError(null)
    setUploadNotice(null)
    if (!isSupportedResearchMaterialFile(file)) {
      setError('暂不支持图片或此文件格式。请上传文档或 MP3、M4A、WAV、MP4、WebM。')
      return
    }
    // A list response that started before the upload must not erase the
    // locally inserted material when it eventually resolves.
    materialsLoadAbortController.current?.abort()
    materialsLoadAbortController.current = null
    materialsLoadGeneration.current += 1
    setLoading(false)
    setUploading(true)
    try {
      const created = await uploadResearchMaterial(taskId, file, kind)
      setMaterials((current) => [created, ...current.filter((item) => item.materialId !== created.materialId)])
      // Upload responses may only carry the segment count. Reuse the same
      // detail-loading path as an explicit selection so a newly added source
      // immediately exposes its stable locators instead of an empty panel.
      await selectMaterial(created)
      setUploadNotice('材料已加入，解析完成后即可检索。')
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : '研究材料上传失败。')
    } finally {
      setUploading(false)
    }
  }

  async function retry(material: ResearchMaterial) {
    setBusyMaterialId(material.materialId)
    setError(null)
    if (selectionDraft?.materialId === material.materialId) clearSelectionDraft()
    try {
      const updated = await reparseResearchMaterial(taskId, material.materialId)
      setMaterials((current) => current.map((item) => item.materialId === updated.materialId ? { ...item, ...updated } : item))
      setSelectedMaterial((current) => current?.materialId === updated.materialId ? { ...current, ...updated } : current)
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : '研究材料重新解析失败。')
    } finally {
      setBusyMaterialId(null)
    }
  }

  async function remove(material: ResearchMaterial) {
    if (!globalThis.confirm(`确定删除“${material.filename}”？删除后，Agent 将不能再检索或引用它。`)) return
    setBusyMaterialId(material.materialId)
    setError(null)
    try {
      await deleteResearchMaterial(taskId, material.materialId)
      setMaterials((current) => current.filter((item) => item.materialId !== material.materialId))
      setSelectedMaterial((current) => current?.materialId === material.materialId ? null : current)
      if (selectionDraft?.materialId === material.materialId) clearSelectionDraft()
      onMaterialDeleted?.(material.materialId)
      setUploadNotice('材料已删除，后续检索不会再使用它。')
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : '研究材料删除失败。')
    } finally {
      setBusyMaterialId(null)
    }
  }

  async function saveAnnotation() {
    if (
      !selectionDraft
      || !annotationNote.trim()
      || (annotationKind === 'researcher_reflection' && !annotationReflection.trim())
      || savingAnnotation
    ) return
    setSavingAnnotation(true)
    setAnalysisError(null)
    setAnalysisNotice(null)
    try {
      const created = await createAnalysisAnnotation(taskId, {
        material_id: selectionDraft.materialId,
        parse_id: selectionDraft.parseId,
        segment_id: selectionDraft.segmentId,
        quote_start: selectionDraft.quoteStart,
        quote_end: selectionDraft.quoteEnd,
        annotation_kind: annotationKind,
        note: annotationNote.trim(),
        reflection: annotationReflection.trim() || null,
        case_label: annotationCaseLabel.trim() || null,
        observed_at: annotationObservedAt.trim() || null,
      })
      setAnalysisSnapshot((current) => current
        ? { ...current, annotations: [...current.annotations, created] }
        : { task_id: taskId, annotations: [created], codes: [], memos: [], comparisons: [] })
      clearSelectionDraft()
      setAnalysisNotice('片段标记已保存。')
    } catch (cause: unknown) {
      setAnalysisError(cause instanceof Error ? cause.message : '片段标记未保存。')
    } finally {
      setSavingAnnotation(false)
    }
  }

  async function saveCode(body: CreateAnalysisCodeInput) {
    const created = await createAnalysisCode(taskId, body)
    setAnalysisSnapshot((current) => current
      ? { ...current, codes: [...current.codes, created] }
      : { task_id: taskId, annotations: [], codes: [created], memos: [], comparisons: [] })
    setAnalysisNotice('编码已保存。')
  }

  async function saveMemo(body: CreateAnalysisMemoInput) {
    const created = await createAnalysisMemo(taskId, body)
    setAnalysisSnapshot((current) => current
      ? { ...current, memos: [...current.memos, created] }
      : { task_id: taskId, annotations: [], codes: [], memos: [created], comparisons: [] })
    setAnalysisNotice('分析备忘已保存。')
  }

  async function decideCode(codeId: string, decision: ResearchAnalysisDecision, reason: string, expectedVersion: number) {
    const updated = await decideAnalysisCode(taskId, codeId, {
      decision,
      reason,
      expected_version: expectedVersion,
    })
    setAnalysisSnapshot((current) => current
      ? { ...current, codes: current.codes.map((code) => code.code_id === updated.code_id ? updated : code) }
      : current)
    setAnalysisNotice(decision === 'confirmed' ? '候选编码已确认。' : '候选编码已拒绝。')
  }

  async function decideMemo(memoId: string, decision: ResearchAnalysisDecision, reason: string, expectedVersion: number) {
    const updated = await decideAnalysisMemo(taskId, memoId, {
      decision,
      reason,
      expected_version: expectedVersion,
    })
    setAnalysisSnapshot((current) => current
      ? { ...current, memos: current.memos.map((memo) => memo.memo_id === updated.memo_id ? updated : memo) }
      : current)
    setAnalysisNotice(decision === 'confirmed' ? '备忘草稿已确认。' : '备忘草稿已拒绝。')
  }

  async function saveComparison(body: CreateCaseComparisonInput) {
    const created = await createCaseComparison(taskId, body)
    setAnalysisSnapshot((current) => current
      ? { ...current, comparisons: [...current.comparisons, created] }
      : { task_id: taskId, annotations: [], codes: [], memos: [], comparisons: [created] })
    setAnalysisNotice('案例比较已保存。')
  }

  async function decideComparison(comparisonId: string, decision: ResearchAnalysisDecision, reason: string, expectedVersion: number) {
    const updated = await decideCaseComparison(taskId, comparisonId, {
      decision,
      reason,
      expected_version: expectedVersion,
    })
    setAnalysisSnapshot((current) => current
      ? { ...current, comparisons: current.comparisons.map((comparison) => comparison.comparison_id === updated.comparison_id ? updated : comparison) }
      : current)
    setAnalysisNotice(decision === 'confirmed' ? '案例比较已确认。' : '案例比较已拒绝。')
  }

  async function refreshWorkspaceAfter(operation: () => Promise<unknown>, notice: string) {
    setAnalysisError(null)
    setAnalysisNotice(null)
    await operation()
    await loadAnalysis()
    setAnalysisNotice(notice)
  }

  async function configureCodebook(codeId: string, body: ConfigureCodebookEntryInput) {
    await refreshWorkspaceAfter(
      () => configureCodebookEntry(taskId, codeId, body),
      '代码本边界已保存。',
    )
  }

  async function transitionCodebook(codeId: string, body: TransitionCodebookEntryInput) {
    await refreshWorkspaceAfter(
      () => transitionCodebookEntry(taskId, codeId, body),
      '代码本状态已更新。',
    )
  }

  async function saveTheme(body: CreateAnalysisThemeInput) {
    await refreshWorkspaceAfter(() => createAnalysisTheme(taskId, body), '分析主题已保存。')
  }

  async function confirmTheme(themeId: string, reason: string, expectedVersion: number) {
    await refreshWorkspaceAfter(
      () => confirmAnalysisTheme(taskId, themeId, reason, expectedVersion),
      '候选主题已确认。',
    )
  }

  async function attachMemo(body: CreateAnalysisMemoLinkInput) {
    await refreshWorkspaceAfter(() => attachAnalysisMemo(taskId, body), '备忘挂接已保存。')
  }

  async function saveCaseProfile(body: SaveAnalysisCaseProfileInput) {
    await refreshWorkspaceAfter(() => saveAnalysisCaseProfile(taskId, body), '个案档案已保存。')
  }

  async function saveMatrixCell(body: SaveCaseThemeMatrixCellInput) {
    await refreshWorkspaceAfter(() => saveCaseThemeMatrixCell(taskId, body), '比较矩阵单元已保存。')
  }

  async function saveQualitativeMethod(body: SetQualitativeMethodInput) {
    await refreshWorkspaceAfter(() => setQualitativeMethod(taskId, body), '方法取向已保存。')
  }

  const segments = selectedMaterial?.segments ?? []
  const normalizedReaderQuery = readerQuery.trim().toLocaleLowerCase()
  const readerSegments = segments.filter((segment) => {
    if (readerFilter === 'headings' && segment.kind !== 'heading' && !segment.locator.headingPath.length) return false
    if (!normalizedReaderQuery) return true
    return `${segment.text} ${formatMaterialLocator(segment.locator)}`.toLocaleLowerCase().includes(normalizedReaderQuery)
  })
  const readerPageCount = Math.max(1, Math.ceil(readerSegments.length / READER_PAGE_SIZE))
  const activeReaderPage = Math.min(readerPage, readerPageCount - 1)
  const pagedReaderSegments = readerSegments.slice(activeReaderPage * READER_PAGE_SIZE, (activeReaderPage + 1) * READER_PAGE_SIZE)
  const readerHeadings = segments.filter((segment, index, all) => {
    if (segment.kind !== 'heading' && !segment.locator.headingPath.length) return false
    const key = segment.kind === 'heading' ? segment.segmentId : segment.locator.headingPath.join(' / ')
    return all.findIndex((candidate) => {
      const candidateKey = candidate.kind === 'heading' ? candidate.segmentId : candidate.locator.headingPath.join(' / ')
      return candidateKey === key
    }) === index
  })

  function clearSelectionDraft() {
    setSelectionDraft(null)
    setSelectionNotice(null)
    setAnnotationKind('descriptive')
    setAnnotationNote('')
    setAnnotationReflection('')
    setAnnotationCaseLabel('')
    setAnnotationObservedAt('')
    window.getSelection()?.removeAllRanges()
  }

  function captureSelection(segment: ResearchMaterialSegment, container: HTMLParagraphElement, range: Range) {
    const draft = selectionDraftFromDomRange(segment, container, range)
    if (!draft) {
      setSelectionDraft(null)
      setAnnotationKind('descriptive')
      setAnnotationNote('')
      setAnnotationReflection('')
      setAnnotationCaseLabel('')
      setAnnotationObservedAt('')
      setSelectionNotice('一次只能选择一个原文片段。')
      window.getSelection()?.removeAllRanges()
      return
    }
    setSelectedSegmentId(segment.segmentId)
    setSelectionDraft(draft)
    setSelectionNotice(null)
    setAnnotationKind('descriptive')
    setAnnotationNote('')
    setAnnotationReflection('')
    setAnnotationCaseLabel('')
    setAnnotationObservedAt('')
  }

  const workspacePresentation = presentation === 'workspace'
  return (
    <div className={`research-materials__overlay${workspacePresentation ? ' research-materials__overlay--workspace' : ''}`} role={workspacePresentation ? undefined : 'presentation'}>
      <section className="research-materials" role={workspacePresentation ? 'region' : 'dialog'} aria-modal={workspacePresentation ? undefined : 'true'} aria-labelledby="research-materials-heading">
        <header className="research-materials__header">
          <div>
            <span className="research-materials__eyebrow">当前研究</span>
            <h2 id="research-materials-heading">研究材料</h2>
            <p>{materials.length ? `${materials.length} 份材料` : '把论文、访谈和田野记录放在同一处'}</p>
          </div>
          {onClose ? <button type="button" className="research-materials__close" aria-label="关闭研究材料" onClick={onClose}><XIcon size={18} /></button> : null}
        </header>

        <div className="research-materials__body">
          <section className="research-materials__library" aria-label="材料列表">
            <div className="research-materials__add-row">
              <div>
                <strong>加入材料</strong>
                <small>支持文档、MP3、M4A、WAV、MP4、WebM</small>
              </div>
              <div className="research-materials__add-actions">
                <label className="research-materials__kind-label" htmlFor="research-material-kind">类型</label>
                <select id="research-material-kind" value={kind} onChange={(event) => setKind(event.target.value as ResearchMaterialKind)} aria-label="材料类型">
                  {MATERIAL_KINDS.map((item) => <option key={item} value={item}>{materialKindLabel(item)}</option>)}
                </select>
                <button type="button" className="research-materials__add-button" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
                  {uploading ? <CircleNotchIcon className="is-spinning" size={16} /> : <FilePlusIcon size={16} />}
                  {uploading ? '正在上传' : '选择文件'}
                </button>
                <input ref={fileInputRef} className="research-materials__file-input" type="file" accept={RESEARCH_MATERIAL_ACCEPT} aria-label="选择研究材料文件" onChange={(event) => { void handleFileChange(event) }} />
              </div>
            </div>
            {error ? <p className="research-materials__message is-error" role="alert"><WarningCircleIcon size={15} />{error}</p> : null}
            {uploadNotice ? <p className="research-materials__message is-success" role="status"><CheckCircleIcon size={15} />{uploadNotice}</p> : null}
            {loading ? <p className="research-materials__loading" role="status"><CircleNotchIcon className="is-spinning" size={16} />正在加载材料</p> : null}
            {!loading && !materials.length ? <div className="research-materials__empty"><FilePlusIcon size={24} /><strong>还没有研究材料</strong><p>先加入一份论文、访谈转录或田野笔记，Agent 才能在本次研究中引用它。</p></div> : null}
            <div className="research-materials__list">
              {materials.map((material) => (
                <article className={`research-materials__item${selectedMaterial?.materialId === material.materialId ? ' is-selected' : ''}`} key={material.materialId} data-status={material.status}>
                  <button type="button" className="research-materials__item-main" aria-label={`查看材料：${material.filename}`} onClick={() => { void selectMaterial(material) }}>
                    <span className="research-materials__file-mark">{materialMediaLabel(material.mediaType, material.filename)}</span>
                    <span className="research-materials__item-copy">
                      <strong>{material.filename}</strong>
                      <small>{material.materialKind ? materialKindLabel(material.materialKind) : '研究材料'} · {formatMaterialSize(material.sizeBytes)}{formatUpdatedAt(material.updatedAt) ? ` · ${formatUpdatedAt(material.updatedAt)}` : ''}</small>
                    </span>
                    <span className="research-materials__item-status">{materialStatusIcon(material.status)}{materialStatusLabel(material.status)}</span>
                  </button>
                  <div className="research-materials__item-actions">
                    {material.status === 'failed' ? <button type="button" aria-label="重新解析" onClick={() => { void retry(material) }} disabled={busyMaterialId === material.materialId}>{busyMaterialId === material.materialId ? <CircleNotchIcon className="is-spinning" size={14} /> : <ArrowClockwiseIcon size={14} />}</button> : null}
                    <button type="button" aria-label="删除材料" onClick={() => { void remove(material) }} disabled={busyMaterialId === material.materialId}><TrashIcon size={14} /></button>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="research-materials__detail" aria-label="材料详情">
            {selectedMaterial ? (
              <>
                <header className="research-materials__detail-header">
                  <div>
                    <span>{selectedMaterial.materialKind ? materialKindLabel(selectedMaterial.materialKind) : materialMediaLabel(selectedMaterial.mediaType, selectedMaterial.filename)}</span>
                    <h3>{selectedMaterial.filename}</h3>
                  </div>
                  <small>{selectedMaterial.segmentCount ? `${selectedMaterial.segmentCount} 个可定位片段` : materialStatusLabel(selectedMaterial.status)}</small>
                </header>
                <div className="research-materials__detail-modes" aria-label="材料视图">
                  <button type="button" aria-pressed={detailMode === 'source'} onClick={() => setDetailMode('source')}>{isMediaResearchMaterial(selectedMaterial) ? '媒体与转录' : '原文'}</button>
                  <button type="button" aria-pressed={detailMode === 'analysis'} onClick={() => setDetailMode('analysis')}>分析</button>
                  <button type="button" aria-pressed={detailMode === 'archive'} onClick={() => setDetailMode('archive')}>档案</button>
                </div>
                {analysisNotice ? <p className="research-materials__analysis-notice" role="status">{analysisNotice}</p> : null}
                {analysisError ? <p className="research-materials__detail-note is-error" role="alert"><WarningCircleIcon size={15} />{analysisError}</p> : null}
                {detailMode === 'archive' ? (
                  <ProfessionalMaterialArchivePanel
                    taskId={taskId}
                    selectedMaterial={selectedMaterial}
                    materials={materials}
                    onMaterialsChanged={() => { void loadMaterials() }}
                  />
                ) : detailMode === 'source' ? (
                  isMediaResearchMaterial(selectedMaterial) ? (
                    <MediaTranscriptWorkspace
                      taskId={taskId}
                      materialId={selectedMaterial.materialId}
                      mediaType={selectedMaterial.mediaType}
                      initialParseId={initialMaterialId === selectedMaterial.materialId ? initialParseId : null}
                      initialSegmentId={initialMaterialId === selectedMaterial.materialId ? initialSegmentId : null}
                      onLocationChange={setMediaLocation}
                    />
                  ) : <>
                    {detailLoading ? <p className="research-materials__loading"><CircleNotchIcon className="is-spinning" size={16} />正在读取原文结构</p> : null}
                    {!detailLoading && selectedMaterial.status === 'failed' ? <p className="research-materials__detail-note is-error"><WarningCircleIcon size={15} />解析失败后，原材料仍保留；重新解析成功前不会进入检索。</p> : null}
                    {!detailLoading && selectedMaterial.status === 'processing' ? <p className="research-materials__detail-note"><CircleNotchIcon className="is-spinning" size={15} />解析完成后，这里会显示章节、段落和可引用位置。</p> : null}
                    {!detailLoading && selectedMaterial.status === 'ready' && !segments.length ? <p className="research-materials__detail-note">暂时没有可展示的片段。</p> : null}
                    <section className="research-materials__reader" role="region" aria-label="文档阅读器">
                      <div className="research-materials__reader-toolbar">
                        <label className="research-materials__reader-search">
                          <MagnifyingGlassIcon size={15} aria-hidden="true" />
                          <span className="sr-only">在材料中查找</span>
                          <input
                            type="search"
                            role="searchbox"
                            aria-label="在材料中查找"
                            value={readerQuery}
                            onChange={(event) => { setReaderQuery(event.target.value); setReaderPage(0) }}
                            placeholder="查找原文或定位"
                          />
                          {readerQuery ? <button type="button" aria-label="清除材料查找" onClick={() => { setReaderQuery(''); setReaderPage(0) }}><XIcon size={13} /></button> : null}
                        </label>
                        <label className="research-materials__reader-filter">
                          <span>显示</span>
                          <select aria-label="段落筛选" value={readerFilter} onChange={(event) => { setReaderFilter(event.target.value as typeof readerFilter); setReaderPage(0) }}>
                            <option value="all">全部原文</option>
                            <option value="headings">只看章节</option>
                          </select>
                        </label>
                        <span className="research-materials__reader-count">
                          {normalizedReaderQuery ? `${readerSegments.length} 处命中` : `${segments.length} 段原文`}
                        </span>
                      </div>
                      <div className="research-materials__reader-layout">
                        <nav className="research-materials__outline" aria-label="章节导航">
                          <span>章节</span>
                          {readerHeadings.length ? readerHeadings.map((heading) => {
                            const headingIndex = segments.findIndex((segment) => segment.segmentId === heading.segmentId)
                            return (
                              <button
                                type="button"
                                key={heading.segmentId}
                                onClick={() => {
                                  setReaderQuery('')
                                  setReaderFilter('all')
                                  setReaderPage(Math.floor(Math.max(0, headingIndex) / READER_PAGE_SIZE))
                                  void selectSegment(heading)
                                }}
                                title={heading.text}
                              >
                                {heading.text || heading.locator.headingPath.at(-1) || `第 ${headingIndex + 1} 段`}
                              </button>
                            )
                          }) : <small>解析出章节后会显示在这里。</small>}
                        </nav>
                        <div className="research-materials__reader-main">
                          <div className="research-materials__reader-page-meta">
                            <span>{readerPageCount > 1 ? `第 ${activeReaderPage + 1} / ${readerPageCount} 页` : '连续阅读'}</span>
                            {normalizedReaderQuery ? <span>按查找结果分页</span> : <span>每页 {READER_PAGE_SIZE} 段</span>}
                          </div>
                          <div className="research-materials__segments">
                            {pagedReaderSegments.map((segment) => {
                              const selected = segment.segmentId === selectedSegmentId
                              return (
                                <button
                                  type="button"
                                  className="research-materials__segment-button"
                                  key={segment.segmentId}
                                  aria-current={selected ? 'location' : undefined}
                                  ref={(element) => {
                                    if (element) segmentButtonRefs.current.set(segment.segmentId, element)
                                    else segmentButtonRefs.current.delete(segment.segmentId)
                                  }}
                                  onClick={() => { void selectSegment(segment) }}
                                >
                                  <SegmentCard segment={segment} selected={selected} onTextSelection={captureSelection} />
                                </button>
                              )
                            })}
                            {!pagedReaderSegments.length ? <p className="research-materials__reader-no-results">没有匹配的原文。换个词试试。</p> : null}
                          </div>
                          {readerPageCount > 1 ? (
                            <footer className="research-materials__reader-pagination" aria-label="文档分页">
                              <button type="button" aria-label="上一页" onClick={() => setReaderPage((page) => Math.max(0, page - 1))} disabled={activeReaderPage === 0}>上一页</button>
                              <span>{activeReaderPage + 1} / {readerPageCount}</span>
                              <button type="button" aria-label="下一页" onClick={() => setReaderPage((page) => Math.min(readerPageCount - 1, page + 1))} disabled={activeReaderPage >= readerPageCount - 1}>下一页</button>
                            </footer>
                          ) : null}
                        </div>
                      </div>
                    </section>
                    {selectionNotice ? <p className="research-materials__selection-notice" role="alert">{selectionNotice}</p> : null}
                    {selectionDraft ? (
                      <section className="research-materials__annotation-draft" role="region" aria-label="片段标记">
                        <header>
                          <div>
                            <span>已选原文</span>
                            <strong>{selectionDraft.quote}</strong>
                          </div>
                          <button type="button" aria-label="取消片段标记" onClick={clearSelectionDraft}><XIcon size={14} /></button>
                        </header>
                        <label>
                          <span>标记类型</span>
                          <select value={annotationKind} onChange={(event) => setAnnotationKind(event.target.value as typeof annotationKind)} aria-label="标记类型">
                            <option value="descriptive">描述性材料</option>
                            <option value="researcher_reflection">研究者反思</option>
                          </select>
                        </label>
                        <label>
                          <span>材料描述</span>
                          <textarea aria-label="材料描述" value={annotationNote} onChange={(event) => setAnnotationNote(event.target.value)} rows={2} />
                        </label>
                        <label>
                          <span>研究者反思</span>
                          <textarea aria-label="研究者反思" value={annotationReflection} onChange={(event) => setAnnotationReflection(event.target.value)} rows={2} />
                        </label>
                        <div className="research-materials__annotation-context">
                          <label>
                            <span>案例 <small>可选</small></span>
                            <input aria-label="案例" value={annotationCaseLabel} onChange={(event) => setAnnotationCaseLabel(event.target.value)} placeholder="如：家庭 A" />
                          </label>
                          <label>
                            <span>时间 <small>可选</small></span>
                            <input aria-label="时间" value={annotationObservedAt} onChange={(event) => setAnnotationObservedAt(event.target.value)} placeholder="如：迁移后" />
                          </label>
                        </div>
                        <footer>
                          <button type="button" disabled={savingAnnotation || !annotationNote.trim() || (annotationKind === 'researcher_reflection' && !annotationReflection.trim())} onClick={() => { void saveAnnotation() }}>
                            {savingAnnotation ? '正在保存' : '保存片段标记'}
                          </button>
                        </footer>
                      </section>
                    ) : null}
                  </>
                ) : analysisLoading ? (
                  <p className="research-materials__loading" role="status"><CircleNotchIcon className="is-spinning" size={16} />正在加载分析记录</p>
                ) : analysisSnapshot ? (
                  <>
                    {cycleLoading && !researchCycle ? <p className="research-materials__loading" role="status"><CircleNotchIcon className="is-spinning" size={16} />正在整理证据缺口</p> : null}
                    {cycleError ? <p className="research-materials__detail-note is-error" role="alert"><WarningCircleIcon size={15} />{cycleError}</p> : null}
                    {researchCycle ? <ResearchCyclePanel snapshot={researchCycle} /> : null}
                    <ResearchAnalysisWorkspace
                      snapshot={analysisSnapshot}
                      selectedMaterialId={selectedMaterial.materialId}
                      materialNames={Object.fromEntries(materials.map((material) => [material.materialId, material.filename]))}
                      onCreateCode={saveCode}
                      onCreateMemo={saveMemo}
                      onDecideCode={decideCode}
                      onDecideMemo={decideMemo}
                      onCreateComparison={saveComparison}
                      onDecideComparison={decideComparison}
                      onConfigureCodebook={configureCodebook}
                      onTransitionCodebook={transitionCodebook}
                      onCreateTheme={saveTheme}
                      onConfirmTheme={confirmTheme}
                      onAttachMemo={attachMemo}
                      onSaveCaseProfile={saveCaseProfile}
                      onSaveMatrixCell={saveMatrixCell}
                      onSetMethod={saveQualitativeMethod}
                    />
                  </>
                ) : (
                  <p className="research-analysis__empty">质性分析记录暂时无法加载。</p>
                )}
              </>
            ) : (
              <div className="research-materials__detail-empty"><MagnifyingGlassIcon size={25} /><strong>选择一份材料</strong><p>查看原文片段与页码、章节或行号。Agent 的引用会回到这里。</p></div>
            )}
          </section>
        </div>
      </section>
    </div>
  )
}

export type { ResearchMaterialsPanelProps }
