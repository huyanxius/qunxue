import { ArchiveBoxIcon, CheckCircleIcon, WarningCircleIcon, XIcon } from '@phosphor-icons/react'
import { useEffect, useRef, useState, type ChangeEvent } from 'react'

import { MaterialAnnotationDrawer, type AnnotationKind } from './MaterialAnnotationDrawer'
import { MaterialLibraryView } from './MaterialLibraryView'
import { MaterialReaderView, type ReaderHeading } from './MaterialReaderView'
import { MediaTranscriptWorkspace } from './MediaTranscriptWorkspace'
import { ProfessionalMaterialArchivePanel } from './ProfessionalMaterialArchive'
import { createAnalysisAnnotation, getAnalysisSnapshot } from './researchAnalysisApi'
import type { AnalysisAnnotation, AnalysisCode } from './researchAnalysisModel'
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
  isMediaResearchMaterial,
  isSupportedResearchMaterialFile,
  type ResearchMaterial,
  type ResearchMaterialKind,
  type ResearchMaterialSegment,
} from './researchMaterialsModel'
import {
  selectionDraftFromDomRange,
  type ResearchMaterialSelectionDraft,
} from './researchMaterialSelection'
import './research-materials.css'

const READER_PAGE_SIZE = 24

type ResearchMaterialsPanelProps = {
  readonly taskId: string
  readonly onClose?: () => void
  readonly presentation?: 'dialog' | 'workspace'
  readonly onMaterialDeleted?: (materialId: string) => void
  readonly initialMaterialId?: string | null
  readonly initialSegmentId?: string | null
  readonly initialParseId?: string | null
  readonly onWorkspaceLocationChange?: (location: {
    readonly materialId: string | null
    readonly parseId: string | null
    readonly segmentId: string | null
  }) => void
}

/**
 * 材料工具的容器：只管两件事——材料库和阅读台之间的切换，以及数据的读写。
 *
 * 页面身份由 `selectedMaterial` 一个值决定：没选是库，选了是阅读台。以前这里靠
 * `presentation` × `detailMode` 两组开关交叉出六种形态，同一份界面在弹窗里和工作区里长得
 * 不一样，工作区那一版还得把半数控件藏掉——那是层级混乱的根，不是样式问题。现在两种呈现
 * 走同一套结构，弹窗只是多包一层模态外壳。
 */
export function ResearchMaterialsPanel({
  taskId,
  onClose,
  presentation = 'dialog',
  onMaterialDeleted,
  initialMaterialId = null,
  initialSegmentId = null,
  initialParseId = null,
  onWorkspaceLocationChange,
}: ResearchMaterialsPanelProps) {
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
  const [annotationKind, setAnnotationKind] = useState<AnnotationKind>('descriptive')
  const [annotationNote, setAnnotationNote] = useState('')
  const [annotationReflection, setAnnotationReflection] = useState('')
  const [annotationCaseLabel, setAnnotationCaseLabel] = useState('')
  const [annotationObservedAt, setAnnotationObservedAt] = useState('')
  const [savingAnnotation, setSavingAnnotation] = useState(false)
  const [annotationNotice, setAnnotationNotice] = useState<string | null>(null)
  const [annotationError, setAnnotationError] = useState<string | null>(null)
  const [readerPage, setReaderPage] = useState(0)
  const [readerQuery, setReaderQuery] = useState('')
  const [outlineOpen, setOutlineOpen] = useState(true)
  const [searchOpen, setSearchOpen] = useState(false)
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [mediaLocation, setMediaLocation] = useState<{ versionId: string | null; segmentId: string | null } | null>(null)
  const [analysisAnnotations, setAnalysisAnnotations] = useState<AnalysisAnnotation[]>([])
  const [analysisCodes, setAnalysisCodes] = useState<AnalysisCode[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const materialsLoadGeneration = useRef(0)
  const materialsLoadAbortController = useRef<AbortController | null>(null)
  const materialDetailGeneration = useRef(0)
  const materialDetailAbortController = useRef<AbortController | null>(null)
  const segmentGeneration = useRef(0)
  const segmentAbortController = useRef<AbortController | null>(null)
  const initialSelectionApplied = useRef(false)
  const segmentRefs = useRef(new Map<string, HTMLElement>())
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
    void getAnalysisSnapshot(taskId, controller.signal).then((snapshot) => {
      if (controller.signal.aborted) return
      setAnalysisAnnotations(snapshot.annotations)
      setAnalysisCodes(snapshot.codes)
    }).catch(() => {
      if (!controller.signal.aborted) {
        setAnalysisAnnotations([])
        setAnalysisCodes([])
      }
    })
    return () => controller.abort()
  }, [taskId])

  useEffect(() => {
    return () => {
      materialsLoadAbortController.current?.abort()
      materialDetailAbortController.current?.abort()
      segmentAbortController.current?.abort()
      materialsLoadGeneration.current += 1
      materialDetailGeneration.current += 1
      segmentGeneration.current += 1
    }
  }, [])

  useEffect(() => {
    materialDetailAbortController.current?.abort()
    segmentAbortController.current?.abort()
    materialDetailGeneration.current += 1
    segmentGeneration.current += 1
    setSelectedMaterial(null)
    setSelectedSegmentId(null)
    setReaderPage(0)
    setReaderQuery('')
    setSearchOpen(false)
    setArchiveOpen(false)
    setMediaLocation(null)
    setAnnotationNotice(null)
    setAnnotationError(null)
    clearSelectionDraft()
  }, [taskId])

  useEffect(() => {
    if (
      selectedMaterial
      && initialMaterialId === selectedMaterial.materialId
      && isMediaResearchMaterial(selectedMaterial)
    ) return
    initialSelectionApplied.current = false
    scrolledCitationTarget.current = null
  }, [taskId, initialMaterialId, initialSegmentId, initialParseId, selectedMaterial])

  // 保存成功的提示说完就该走。留在屏幕上的旧回执会让人以为刚才那次操作还没结束。
  useEffect(() => {
    if (!annotationNotice) return
    const timer = window.setTimeout(() => setAnnotationNotice(null), 4000)
    return () => window.clearTimeout(timer)
  }, [annotationNotice])

  useEffect(() => {
    if (!initialMaterialId || initialSelectionApplied.current || !materials.length) return
    const target = materials.find((item) => item.materialId === initialMaterialId)
    if (target) {
      initialSelectionApplied.current = true
      void selectMaterial(target, initialParseId, initialSegmentId)
    }
  }, [initialMaterialId, initialParseId, initialSegmentId, materials])

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
    const target = segmentRefs.current.get(initialSegmentId)
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
    if (initialMaterialId && !selectedMaterial) return
    const selectedSegment = selectedMaterial?.segments?.find((segment) => segment.segmentId === selectedSegmentId)
    const mediaSelected = selectedMaterial ? isMediaResearchMaterial(selectedMaterial) : false
    if (mediaSelected && !mediaLocation) return
    onWorkspaceLocationChange({
      materialId: selectedMaterial?.materialId ?? null,
      parseId: mediaSelected
        ? mediaLocation?.versionId ?? null
        : selectedSegment?.parseId
          ?? (selectedMaterial?.materialId === initialMaterialId ? initialParseId : null),
      segmentId: mediaSelected ? mediaLocation?.segmentId ?? null : selectedSegmentId,
    })
  }, [initialMaterialId, initialParseId, mediaLocation, onWorkspaceLocationChange, selectedMaterial, selectedSegmentId])

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
    setSearchOpen(false)
    setArchiveOpen(false)
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

  function returnToLibrary() {
    materialDetailAbortController.current?.abort()
    segmentAbortController.current?.abort()
    materialDetailGeneration.current += 1
    segmentGeneration.current += 1
    initialSelectionApplied.current = true
    clearSelectionDraft()
    setSelectedMaterial(null)
    setSelectedSegmentId(null)
    setArchiveOpen(false)
    setSearchOpen(false)
    setReaderQuery('')
    setReaderPage(0)
    setDetailLoading(false)
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

  function jumpToHeading(segment: ResearchMaterialSegment) {
    const index = (selectedMaterial?.segments ?? []).findIndex((item) => item.segmentId === segment.segmentId)
    setReaderQuery('')
    setReaderPage(Math.floor(Math.max(0, index) / READER_PAGE_SIZE))
    void selectSegment(segment)
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
      // 上传响应可能只带片段数不带片段本身，补一次详情把可定位片段数补齐，让新加进来的这行
      // 立刻说得出自己有多少可引用位置。补完仍然留在材料库：加材料是库这一层的动作，刚上传
      // 就把人甩进阅读台，多半还在解析中，等于推开一扇空门。
      await refreshMaterialDetail(created)
      setUploadNotice('材料已加入，解析完成后即可检索。')
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : '研究材料上传失败。')
    } finally {
      setUploading(false)
    }
  }

  async function refreshMaterialDetail(material: ResearchMaterial) {
    if (material.segments) return
    try {
      const detail = await getResearchMaterial(taskId, material.materialId)
      setMaterials((current) => current.map((item) => item.materialId === detail.materialId ? { ...item, ...detail } : item))
    } catch {
      // 列表行退回上传响应里的信息即可，补详情失败不该把刚加进来的材料判成出错。
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
    setAnnotationError(null)
    setAnnotationNotice(null)
    try {
      await createAnalysisAnnotation(taskId, {
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
      clearSelectionDraft()
      setAnnotationNotice('片段标记已保存。')
    } catch (cause: unknown) {
      setAnnotationError(cause instanceof Error ? cause.message : '片段标记未保存。')
    } finally {
      setSavingAnnotation(false)
    }
  }

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

  function captureSelection(segment: ResearchMaterialSegment, container: HTMLElement, range: Range) {
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
    setAnnotationNotice(null)
  }

  const segments = selectedMaterial?.segments ?? []
  const normalizedReaderQuery = readerQuery.trim().toLocaleLowerCase()
  const readerSegments = normalizedReaderQuery
    ? segments.filter((segment) => `${segment.text} ${formatMaterialLocator(segment.locator)}`.toLocaleLowerCase().includes(normalizedReaderQuery))
    : segments
  const readerPageCount = Math.max(1, Math.ceil(readerSegments.length / READER_PAGE_SIZE))
  const activeReaderPage = Math.min(readerPage, readerPageCount - 1)
  const pagedReaderSegments = readerSegments.slice(activeReaderPage * READER_PAGE_SIZE, (activeReaderPage + 1) * READER_PAGE_SIZE)
  /*
   * 一个章节在片段流里出现两次：标题片段自己，和它下面第一个带 headingPath 的正文片段。
   * 按标题文字去重而不是按片段 id，否则目录里每一章都会列两遍——之前就是这样。标题片段
   * 排在正文之前，所以先到先得正好保证跳转落在标题上。
   */
  const readerHeadings: ReaderHeading[] = []
  const seenHeadings = new Set<string>()
  segments.forEach((segment, index) => {
    if (segment.kind !== 'heading' && !segment.locator.headingPath.length) return
    const label = (segment.kind === 'heading' ? segment.text : segment.locator.headingPath.at(-1))?.trim()
      || `第 ${index + 1} 段`
    if (seenHeadings.has(label)) return
    seenHeadings.add(label)
    readerHeadings.push({ segment, label })
  })

  const mediaSelected = selectedMaterial ? isMediaResearchMaterial(selectedMaterial) : false
  const readerNote = !detailLoading && selectedMaterial
    ? selectedMaterial.status === 'failed'
      ? { tone: 'error' as const, text: '解析失败后，原材料仍保留；重新解析成功前不会进入检索。' }
      : selectedMaterial.status === 'processing'
        ? { tone: 'plain' as const, text: '解析完成后，这里会显示章节、段落和可引用位置。' }
        : null
    : null

  const workspacePresentation = presentation === 'workspace'
  const body = selectedMaterial ? (
    <div className="qx-materials__workbench">
      {mediaSelected ? (
        <section className="qx-reader qx-reader--media" aria-label="材料阅读台">
          <header className={`qx-reader__bar${workspacePresentation ? ' is-workspace-chrome' : ''}`}>
            {!workspacePresentation ? <>
              <button type="button" className="qx-reader__back" onClick={returnToLibrary}>材料库</button>
              <div className="qx-reader__identity">
                <h2>{selectedMaterial.filename}</h2>
                <p>媒体转录</p>
              </div>
            </> : null}
            <div className="qx-reader__tools">
              <button type="button" className="qx-icon-button" aria-label="材料档案" title="材料档案" onClick={() => setArchiveOpen(true)}><ArchiveBoxIcon size={17} aria-hidden="true" /></button>
            </div>
          </header>
          <MediaTranscriptWorkspace
            taskId={taskId}
            materialId={selectedMaterial.materialId}
            mediaType={selectedMaterial.mediaType}
            initialParseId={initialMaterialId === selectedMaterial.materialId ? initialParseId : null}
            initialSegmentId={initialMaterialId === selectedMaterial.materialId ? initialSegmentId : null}
            onLocationChange={setMediaLocation}
          />
        </section>
      ) : (
        <MaterialReaderView
          material={selectedMaterial}
          segments={pagedReaderSegments}
          totalSegmentCount={segments.length}
          headings={readerHeadings}
          selectedSegmentId={selectedSegmentId}
          detailLoading={detailLoading}
          note={readerNote}
          outlineOpen={outlineOpen}
          searchOpen={searchOpen}
          query={readerQuery}
          matchCount={readerSegments.length}
          page={activeReaderPage}
          pageCount={readerPageCount}
          annotations={analysisAnnotations.filter((annotation) => annotation.material_id === selectedMaterial.materialId)}
          codes={analysisCodes}
          workspaceChrome={workspacePresentation}
          registerSegment={(segmentId, element) => {
            if (element) segmentRefs.current.set(segmentId, element)
            else segmentRefs.current.delete(segmentId)
          }}
          onBack={returnToLibrary}
          onToggleOutline={() => setOutlineOpen((open) => !open)}
          onToggleSearch={() => setSearchOpen((open) => !open)}
          onQueryChange={(next) => { setReaderQuery(next); setReaderPage(0) }}
          onOpenArchive={() => setArchiveOpen(true)}
          onSelectSegment={(segment) => { void (segment.kind === 'heading' ? jumpToHeading(segment) : selectSegment(segment)) }}
          onTextSelection={captureSelection}
          onPageChange={setReaderPage}
        />
      )}

      {selectionDraft ? (
        <MaterialAnnotationDrawer
          draft={selectionDraft}
          kind={annotationKind}
          note={annotationNote}
          reflection={annotationReflection}
          caseLabel={annotationCaseLabel}
          observedAt={annotationObservedAt}
          saving={savingAnnotation}
          onKindChange={setAnnotationKind}
          onNoteChange={setAnnotationNote}
          onReflectionChange={setAnnotationReflection}
          onCaseLabelChange={setAnnotationCaseLabel}
          onObservedAtChange={setAnnotationObservedAt}
          onCancel={clearSelectionDraft}
          onSave={() => { void saveAnnotation() }}
        />
      ) : null}
    </div>
  ) : (
    <MaterialLibraryView
      materials={materials}
      loading={loading}
      error={error}
      notice={uploadNotice}
      uploading={uploading}
      busyMaterialId={busyMaterialId}
      kind={kind}
      fileInputRef={fileInputRef}
      onKindChange={setKind}
      onFileChange={(event) => { void handleFileChange(event) }}
      onOpenMaterial={(material) => { void selectMaterial(material) }}
      onOpenArchive={(material) => { void selectMaterial(material).then(() => setArchiveOpen(true)) }}
      onRetry={(material) => { void retry(material) }}
      onDelete={(material) => { void remove(material) }}
    />
  )

  return (
    <div className={`qx-materials__shell${workspacePresentation ? ' is-workspace' : ''}`} role={workspacePresentation ? undefined : 'presentation'}>
      <section
        className="qx-materials"
        role={workspacePresentation ? 'region' : 'dialog'}
        aria-modal={workspacePresentation ? undefined : 'true'}
        aria-label="研究材料"
      >
        {onClose ? (
          <button type="button" className="qx-materials__close qx-icon-button" aria-label="关闭研究材料" onClick={onClose}>
            <XIcon size={18} aria-hidden="true" />
          </button>
        ) : null}

        {selectedMaterial && error ? <p className="qx-message is-error" role="alert"><WarningCircleIcon size={15} aria-hidden="true" />{error}</p> : null}
        {selectionNotice ? <p className="qx-message is-error" role="alert">{selectionNotice}</p> : null}
        {annotationError ? <p className="qx-message is-error" role="alert"><WarningCircleIcon size={15} aria-hidden="true" />{annotationError}</p> : null}
        {annotationNotice ? <p className="qx-message is-success" role="status"><CheckCircleIcon size={15} aria-hidden="true" />{annotationNotice}</p> : null}

        {body}

        {archiveOpen && selectedMaterial ? (
          <>
            <button type="button" className="qx-drawer__scrim" aria-label="关闭材料档案" onClick={() => setArchiveOpen(false)} />
            <aside className="qx-drawer" role="region" aria-label="材料档案">
              <header className="qx-drawer__head">
                <div>
                  <span className="qx-eyebrow">材料档案</span>
                  <strong>{selectedMaterial.filename}</strong>
                </div>
                <button type="button" className="qx-icon-button" aria-label="收起材料档案" onClick={() => setArchiveOpen(false)}>
                  <XIcon size={15} aria-hidden="true" />
                </button>
              </header>
              <div className="qx-drawer__body">
                <ProfessionalMaterialArchivePanel
                  taskId={taskId}
                  selectedMaterial={selectedMaterial}
                  materials={materials}
                  onMaterialsChanged={() => { void loadMaterials() }}
                />
              </div>
            </aside>
          </>
        ) : null}
      </section>
    </div>
  )
}

export type { ResearchMaterialsPanelProps }
