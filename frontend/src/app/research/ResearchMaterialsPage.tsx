import { ArrowLeftIcon, ArrowUpRightIcon, BrainIcon, FolderSimpleIcon, CheckCircleIcon, FileDocIcon, FilePdfIcon, FileTextIcon, MarkdownLogoIcon, MagnifyingGlassIcon, PlusIcon, TrashIcon, VideoCameraIcon, WaveformIcon } from '@phosphor-icons/react'
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router'

import { listMyResearchViaApi, type MyResearchItem } from '../../modules/account'
import {
  addResearchLibraryMaterial,
  formatMaterialSize,
  listResearchLibraryMaterials,
  removeResearchLibraryMaterial,
  materialMediaLabel,
  materialStatusLabel,
  isSupportedResearchMaterialFile,
  RESEARCH_MATERIAL_ACCEPT,
  uploadInitialResearchMaterials,
  startResearchBatchCoding,
  type ResearchMaterial,
} from '../../modules/research-materials'
import { createMaterialFirstResearchProject } from '../../modules/socio-match-workspace'
import { PageContent, PageShell } from '../ui/PageShell'
import { ResearchLibraryBot } from './ResearchLibraryBot'
import { ResearchMaterialsShader } from './ResearchMaterialsShader'
import { researchLibraryPreview } from './researchLibraryPreview'
import './research-materials-page.css'

type LibraryMaterial = { material: ResearchMaterial; research: MyResearchItem }

function researchTitle(item: MyResearchItem) {
  return (item.projectTitle !== '未命名研究' ? item.projectTitle : '') || (item.phenomenonSummary !== '尚未确认现象' ? item.phenomenonSummary : '') || '未命名研究'
}

function MaterialTypeIcon({ material }: { material: ResearchMaterial }) {
  const format = materialMediaLabel(material.mediaType, material.filename)
  if (format === 'PDF') return <FilePdfIcon size={24} />
  if (format === 'DOCX') return <FileDocIcon size={24} />
  if (format === 'Markdown') return <MarkdownLogoIcon size={24} />
  if (format === 'MP3' || format === 'M4A' || format === 'WAV') return <WaveformIcon size={24} />
  if (format === 'MP4' || format === 'WebM') return <VideoCameraIcon size={24} />
  return <FileTextIcon size={24} />
}

function ResearchHubToolbar({ query, onQueryChange, searchLabel, placeholder, children }: {
  query: string
  onQueryChange: (query: string) => void
  searchLabel: string
  placeholder: string
  children: ReactNode
}) {
  return <div className="research-hub__toolbar">
    <label className="research-hub__search"><MagnifyingGlassIcon size={17} /><input type="search" aria-label={searchLabel} placeholder={placeholder} value={query} onChange={(event) => onQueryChange(event.target.value)} /></label>
    {children}
  </div>
}

/**
 * 材料始终属于一个 ResearchTask；页面只负责让用户找到该研究的材料面板。
 * 不在这里复制上传、解析或分析逻辑，避免出现第二套材料系统。
 */
export function ResearchMaterialsPage({ userId: _userId = null }: { userId?: string | null }) {
  const navigate = useNavigate()
  const emptyUploadInputRef = useRef<HTMLInputElement>(null)
  const uploadInputRef = useRef<HTMLInputElement>(null)
  const uploadPopoverRef = useRef<HTMLDivElement>(null)
  const [searchParams] = useSearchParams()
  const selectedTaskId = searchParams.get('task_id')
  const selectedMaterialId = searchParams.get('material_id')
  const previewFiles = import.meta.env.DEV && searchParams.get('preview') === 'files'
  const interviewView = searchParams.get('view') === 'interviews'
  const batchCodingEntry = searchParams.get('entry') === 'batch-coding'
  const batchRunId = searchParams.get('batch_run_id')
  const [projectQuery, setProjectQuery] = useState('')
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState<'all' | 'documents' | 'media'>('all')
  const [ownerFilter, setOwnerFilter] = useState('')
  const [sortBy, setSortBy] = useState<'updated' | 'name'>('updated')
  const [research, setResearch] = useState<MyResearchItem[]>([])
  const [libraryMaterials, setLibraryMaterials] = useState<LibraryMaterial[]>([])
  const [loading, setLoading] = useState(true)
  const [libraryLoading, setLibraryLoading] = useState(true)
  const [materialLoadStates, setMaterialLoadStates] = useState<Record<string, 'loading' | 'ready' | 'error'>>({})
  const [materialReload, setMaterialReload] = useState(0)
  const [removingMaterialId, setRemovingMaterialId] = useState<string | null>(null)
  const [materialActionError, setMaterialActionError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploadTaskId, setUploadTaskId] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadNotice, setUploadNotice] = useState<string | null>(null)
  const [emptyUploading, setEmptyUploading] = useState(false)
  const [emptyUploadError, setEmptyUploadError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    void listMyResearchViaApi()
      .then((items) => {
        if (active) {
          setResearch(items)
          setUploadTaskId((current) => selectedTaskId || current || items[0]?.taskId || '')
        }
      })
      .catch(() => {
        if (active) setError('研究列表暂时无法加载，请稍后重试。')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (loading) return undefined
    if (!research.length) {
      setLibraryLoading(false)
      return undefined
    }
    const controller = new AbortController()
    let remaining = research.length
    setLibraryLoading(true)
    setMaterialLoadStates(Object.fromEntries(research.map(item => [item.taskId, 'loading'])))
    for (const item of research) {
      void listResearchLibraryMaterials(item.taskId, controller.signal).then((result) => {
        if (controller.signal.aborted) return
        setLibraryMaterials(current => [
          ...current.filter(({ material }) => material.taskId !== item.taskId),
          ...result.items.map(material => ({ material, research: item })),
        ])
        setMaterialLoadStates(current => ({ ...current, [item.taskId]: 'ready' }))
      }).catch(() => {
        if (!controller.signal.aborted) setMaterialLoadStates(current => ({ ...current, [item.taskId]: 'error' }))
      }).finally(() => {
        remaining -= 1
        if (!controller.signal.aborted && !remaining) setLibraryLoading(false)
      })
    }
    return () => controller.abort()
  }, [loading, research, materialReload])

  useEffect(() => {
    if (selectedTaskId) setUploadTaskId(selectedTaskId)
    setUploadOpen(false)
    setUploadNotice(null)
    setMaterialActionError(null)
  }, [selectedTaskId])

  useEffect(() => {
    if (batchCodingEntry && !loading && research.length === 0) emptyUploadInputRef.current?.click()
    if (batchCodingEntry && !loading && research.length > 0 && !selectedTaskId) setUploadOpen(true)
  }, [batchCodingEntry, loading, research.length, selectedTaskId])

  useEffect(() => {
    if (batchCodingEntry && uploadOpen && research.length > 0 && !selectedTaskId) uploadInputRef.current?.click()
  }, [batchCodingEntry, uploadOpen, research.length, selectedTaskId])


  useEffect(() => {
    if (!uploadOpen) return undefined
    function closeUpload(event: KeyboardEvent | PointerEvent) {
      if (event instanceof KeyboardEvent) {
        if (event.key === 'Escape') setUploadOpen(false)
        return
      }
      if (!uploadPopoverRef.current?.contains(event.target as Node)) setUploadOpen(false)
    }
    document.addEventListener('keydown', closeUpload)
    document.addEventListener('pointerdown', closeUpload)
    return () => {
      document.removeEventListener('keydown', closeUpload)
      document.removeEventListener('pointerdown', closeUpload)
    }
  }, [uploadOpen])

  const selectedResearch = research.find((item) => item.taskId === selectedTaskId) ?? null
  const displayedMaterials = previewFiles && selectedResearch
    ? researchLibraryPreview(selectedResearch.taskId).map(material => ({ material, research: selectedResearch }))
    : libraryMaterials
  const currentLibraryLoading = previewFiles && selectedResearch ? false : selectedTaskId
    ? loading || !materialLoadStates[selectedTaskId] || materialLoadStates[selectedTaskId] === 'loading'
    : libraryLoading
  const failedProjects = Object.entries(materialLoadStates).filter(([taskId, state]) => !previewFiles && state === 'error' && (!selectedTaskId || selectedTaskId === taskId))
  function fileCount(taskId: string) {
    if (previewFiles && taskId === selectedTaskId) return `${displayedMaterials.length} 份文件`
    const state = materialLoadStates[taskId]
    if (state === 'error') return '文件读取失败'
    if (state !== 'ready') return '正在读取文件…'
    return `${libraryMaterials.filter(({ material }) => material.taskId === taskId).length} 份文件`
  }

  const visibleMaterials = displayedMaterials.filter(({ material, research: owner }) => {
    const media = material.mediaType.startsWith('audio/') || material.mediaType.startsWith('video/')
    return (!interviewView || media || material.materialKind === 'interview_transcript')
      && (category === 'all' || (category === 'media' ? media : !media))
      && (!(selectedTaskId || ownerFilter) || material.taskId === (selectedTaskId || ownerFilter))
      && `${material.filename} ${researchTitle(owner)}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())
  }).sort((a, b) => sortBy === 'name' ? a.material.filename.localeCompare(b.material.filename, 'zh-CN') : b.material.updatedAt.localeCompare(a.material.updatedAt))

  async function addMaterial(file: File) {
    const targetTaskId = selectedTaskId || uploadTaskId
    if (!targetTaskId) return
    setUploading(true)
    setUploadError(null)
    setUploadNotice(null)
    try {
      const material = await addResearchLibraryMaterial(targetTaskId, file)
      const owner = research.find((item) => item.taskId === targetTaskId)
      if (owner) setLibraryMaterials((current) => [{ material, research: owner }, ...current])
      setUploadOpen(false)
      setUploadNotice('材料已添加')
    } catch {
      setUploadError('材料添加失败，请重试。')
    } finally {
      setUploading(false)
    }
  }

  async function removeMaterial(material: ResearchMaterial) {
    if (removingMaterialId || !globalThis.confirm(`确定删除“${material.filename}”？删除后，Agent 将不能再检索或引用它。`)) return
    setRemovingMaterialId(material.materialId)
    setMaterialActionError(null)
    try {
      await removeResearchLibraryMaterial(material.taskId, material.materialId)
      setLibraryMaterials(current => current.filter(item => item.material.materialId !== material.materialId))
    } catch {
      setMaterialActionError('文件删除失败，请重试。')
    } finally {
      setRemovingMaterialId(null)
    }
  }

  async function startFromMaterials(files: File[]) {
    if (!files.length || emptyUploading) return
    const unsupported = files.find((file) => !isSupportedResearchMaterialFile(file))
    if (unsupported) {
      setEmptyUploadError(`${unsupported.name} 不是可导入的研究材料。`)
      return
    }
    setEmptyUploading(true)
    setEmptyUploadError(null)
    try {
      const requestKey = `material-entry:${globalThis.crypto?.randomUUID?.() ?? Date.now()}`
      const { taskId } = await createMaterialFirstResearchProject(requestKey, files[0].name)
      await uploadInitialResearchMaterials(taskId, files)
      setResearch(await listMyResearchViaApi())
      setUploadTaskId(taskId)
      const imported = await listResearchLibraryMaterials(taskId)
      const material = imported.items[0]
      if (batchCodingEntry && material) {
        const run = await startResearchBatchCoding(taskId, material.materialId)
        navigate(`/research/materials?task_id=${encodeURIComponent(taskId)}&material_id=${encodeURIComponent(material.materialId)}&batch_run_id=${encodeURIComponent(run.runId)}`, { replace: true })
      } else {
        navigate(`/research/materials?task_id=${encodeURIComponent(taskId)}`, { replace: true })
      }
    } catch (cause: unknown) {
      setEmptyUploadError(cause instanceof Error ? cause.message : '材料暂时无法导入，请重试。')
    } finally {
      setEmptyUploading(false)
    }
  }

  async function addBatchMaterial(file: File) {
    const targetTaskId = selectedTaskId || uploadTaskId
    if (!targetTaskId) return
    setUploading(true)
    setUploadError(null)
    try {
      const material = await addResearchLibraryMaterial(targetTaskId, file)
      const run = await startResearchBatchCoding(targetTaskId, material.materialId)
      navigate(`/research/materials?task_id=${encodeURIComponent(targetTaskId)}&material_id=${encodeURIComponent(material.materialId)}&batch_run_id=${encodeURIComponent(run.runId)}`, { replace: true })
    } catch (cause: unknown) {
      setUploadError(cause instanceof Error ? cause.message : '批量编码启动失败，请重试。')
    } finally {
      setUploading(false)
    }
  }

  if (selectedResearch && selectedMaterialId) return <Navigate replace to={`/research/${encodeURIComponent(selectedResearch.taskId)}/workspace/materials${selectedMaterialId ? `?material_id=${encodeURIComponent(selectedMaterialId)}${batchRunId ? `&batch_run_id=${encodeURIComponent(batchRunId)}` : ''}` : ''}`} />

  const activeTab = searchParams.get('tab') === 'memory' ? 'memory'
    : selectedTaskId || searchParams.get('tab') === 'files' || interviewView || batchCodingEntry ? 'files' : 'projects'
  const tabs = selectedResearch
    ? [{ id: 'files', label: '研究材料' }, { id: 'memory', label: '项目记忆' }]
    : [{ id: 'projects', label: '研究项目' }, { id: 'files', label: '全部文件' }, { id: 'memory', label: '个人记忆' }]
  const visibleProjects = research.filter((item) => researchTitle(item).toLocaleLowerCase().includes(projectQuery.trim().toLocaleLowerCase()))
  function changeTab(tab: string) {
    const params = new URLSearchParams(searchParams)
    params.set('tab', tab)
    navigate(`/research/materials?${params}`, { replace: true })
    setUploadOpen(false)
  }

  return <PageShell workspace wide backdrop={<ResearchMaterialsShader />}><PageContent>
    <div className="material-files__scene research-hub-scene">
      <section className={`research-hub${selectedResearch ? ' is-project' : ''}`} aria-label="我的研究">
        {selectedResearch ? <header className="research-hub__project-header">
          <Link className="research-hub__back" to="/research/materials"><ArrowLeftIcon size={16} />我的研究</Link>
          <div className="research-hub__project-title"><FolderSimpleIcon size={28} /><h1>{researchTitle(selectedResearch)}</h1></div>
          <p>{previewFiles ? '示例预览' : selectedResearch.stageLabel}<span className="research-hub__project-count">{fileCount(selectedResearch.taskId)}</span>{previewFiles ? <Link className="research-hub__preview-exit" to={`/research/materials?task_id=${encodeURIComponent(selectedResearch.taskId)}`}>退出预览</Link> : null}</p>
        </header> : <header className="research-hub__hero">
          <ResearchLibraryBot />
          <h1 className="research-hub__accessible-title">我的研究</h1>
        </header>}

        <div className="research-hub__tabs" style={{ '--tab-count': tabs.length, '--tab-index': Math.max(0, tabs.findIndex(tab => tab.id === activeTab)) } as CSSProperties} role="tablist" aria-label={selectedResearch ? '项目内容' : '我的研究视图'} onKeyDown={(event) => {
          const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]'))
          const index = buttons.indexOf(document.activeElement as HTMLButtonElement)
          const next = event.key === 'ArrowRight' ? (index + 1) % buttons.length : event.key === 'ArrowLeft' ? (index + buttons.length - 1) % buttons.length : event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : null
          if (next !== null) { event.preventDefault(); buttons[next].focus(); buttons[next].click() }
        }}>
          {tabs.map(({ id, label }) => <button key={id} id={`research-tab-${id}`} type="button" role="tab" aria-controls={`research-panel-${id}`} aria-selected={activeTab === id} tabIndex={activeTab === id ? 0 : -1} onClick={() => changeTab(id)}>{label}</button>)}
        </div>

        <div className="research-hub__body">
          {error ? <p className="research-hub__notice" role="alert">{error}</p> : null}
          {!selectedResearch ? <section className="research-hub__panel research-hub__panel--scroll" onScroll={(event) => event.currentTarget.style.setProperty('--scroll-fade', `${Math.min(36, event.currentTarget.scrollTop)}px`)} role="tabpanel" id="research-panel-projects" aria-labelledby="research-tab-projects" hidden={activeTab !== 'projects'}>
            <ResearchHubToolbar query={projectQuery} onQueryChange={setProjectQuery} searchLabel="搜索研究项目" placeholder="搜索项目">
              <Link className="research-hub__new" to="/research/new"><PlusIcon size={17} />新建研究</Link>
            </ResearchHubToolbar>
            {loading ? <p className="research-hub__notice" role="status">正在读取研究项目…</p> : <div className="research-hub__projects">
              {visibleProjects.map((item) => <Link className="research-project-card" key={item.taskId} to={`/research/materials?task_id=${encodeURIComponent(item.taskId)}`} aria-label={`打开研究 ${researchTitle(item)}`} onClick={() => { setQuery(''); setCategory('all'); setUploadTaskId(item.taskId) }}>
                <div className="research-project-card__top"><span className="research-project-card__icon"><FolderSimpleIcon size={23} /></span><ArrowUpRightIcon className="research-project-card__arrow" size={16} /></div>
                <h2 title={researchTitle(item)}>{researchTitle(item)}</h2>
                <p>{item.stageLabel}</p>
                <footer><span>{fileCount(item.taskId)}</span><time dateTime={item.updatedAt}>{new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric' }).format(new Date(item.updatedAt))}</time></footer>
              </Link>)}
            </div>}
            {!loading && !visibleProjects.length ? <div className="research-hub__empty"><FolderSimpleIcon size={30} /><h2>{projectQuery ? '没有找到这个项目' : '开始你的第一项研究'}</h2><p>{projectQuery ? '换一个项目名称试试。' : '从一个问题或一份材料开始。'}</p>{!projectQuery ? <Link className="research-hub__new" to="/research/new">新建研究</Link> : null}</div> : null}
          </section> : null}

          <section className="research-hub__panel research-hub__panel--scroll material-files" onScroll={(event) => event.currentTarget.style.setProperty('--scroll-fade', `${Math.min(36, event.currentTarget.scrollTop)}px`)} role="tabpanel" id="research-panel-files" aria-labelledby="research-tab-files" hidden={activeTab !== 'files'}>
            <ResearchHubToolbar query={query} onQueryChange={setQuery} searchLabel="搜索研究材料" placeholder={selectedResearch ? '搜索项目内的材料' : '搜索文件或研究名称'}>
      <div className="material-files__upload-anchor" ref={uploadPopoverRef}>
      <button type="button" className="research-hub__new" aria-expanded={uploadOpen} aria-controls="research-materials-upload-popover" disabled={previewFiles || uploading || emptyUploading} onClick={() => research.length ? setUploadOpen((open) => !open) : emptyUploadInputRef.current?.click()}><PlusIcon size={17} aria-hidden="true" />{uploading || emptyUploading ? '正在导入…' : batchCodingEntry ? '选择材料并批量编码' : '添加材料'}</button>
        {uploadOpen && research.length ? <div id="research-materials-upload-popover" className="qx-popover-surface research-materials-page__upload" role="dialog" aria-label="添加材料">
          {!selectedResearch ? <label>保存到研究<select aria-label="材料所属研究" value={uploadTaskId} onChange={(event) => setUploadTaskId(event.target.value)}>{research.map((item) => <option key={item.taskId} value={item.taskId}>{researchTitle(item)}</option>)}</select></label> : <span>添加到「{researchTitle(selectedResearch)}」</span>}
          <button type="button" disabled={uploading} onClick={() => uploadInputRef.current?.click()}>选择文件</button>
          <input ref={uploadInputRef} hidden type="file" accept={RESEARCH_MATERIAL_ACCEPT} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void (batchCodingEntry ? addBatchMaterial(file) : addMaterial(file)) }} />
          {uploadError ? <span role="alert">{uploadError}</span> : null}
        </div> : null}
      </div>
            </ResearchHubToolbar>
            <div className="research-hub__file-list" role="region" aria-label="全部研究材料">
              <div className="research-hub__filters">
                <select aria-label="材料类型" value={category} onChange={(event) => setCategory(event.target.value as typeof category)}><option value="all">所有类型</option><option value="documents">文档与文本</option><option value="media">录音与视频</option></select>
                {!selectedResearch ? <select aria-label="按研究筛选材料" value={ownerFilter} onChange={(event) => setOwnerFilter(event.target.value)}><option value="">全部研究</option>{research.map(item => <option key={item.taskId} value={item.taskId}>{researchTitle(item)}</option>)}</select> : null}
                <span>{currentLibraryLoading ? `已读取 ${visibleMaterials.length} 份材料` : `${visibleMaterials.length} 份材料`}</span>
                <select className="research-hub__sort" aria-label="材料排序" value={sortBy} onChange={(event) => setSortBy(event.target.value as typeof sortBy)}><option value="updated">最近修改</option><option value="name">文件名称</option></select>
              </div>
              {loading || currentLibraryLoading ? <p className="research-hub__notice" role="status">正在读取研究材料…</p> : null}
              {failedProjects.length ? <p className="research-hub__notice" role="alert">{selectedTaskId ? '当前项目的文件暂时无法读取。' : `${failedProjects.length} 个项目的文件暂时无法读取。`}<button type="button" onClick={() => setMaterialReload(value => value + 1)}>重试</button></p> : null}
              {materialActionError ? <p className="research-hub__notice" role="alert">{materialActionError}</p> : null}
              {emptyUploadError ? <p className="research-hub__notice" role="alert">{emptyUploadError}</p> : null}
              {uploadNotice ? <p className="research-hub__notice" role="status">{uploadNotice}</p> : null}
      {!loading && visibleMaterials.length ? <div className="material-files__table-scroll"><table aria-label="研究材料文件列表"><thead><tr><th scope="col">文件名称</th><th scope="col">所属研究</th><th scope="col">最近修改</th><th scope="col">大小</th><th scope="col">状态</th><th scope="col" className="material-files__actions-heading"><span className="research-hub__accessible-title">文件操作</span></th></tr></thead><tbody>{visibleMaterials.map(({ material, research: owner }) => <tr key={material.materialId}>
        <td><Link className="material-files__filename" to={`/research/${encodeURIComponent(material.taskId)}/workspace/materials?material_id=${encodeURIComponent(material.materialId)}`} aria-label={`打开材料 ${material.filename}`} aria-disabled={previewFiles || undefined} onClick={previewFiles ? (event) => event.preventDefault() : undefined}><span className="material-files__file-icon" aria-hidden="true"><MaterialTypeIcon material={material} /></span><span className="material-files__file-copy"><strong>{material.filename}</strong></span><ArrowUpRightIcon className="material-files__open-icon" size={15} aria-hidden="true" /></Link></td>
        <td title={researchTitle(owner)}>{researchTitle(owner)}</td><td><time dateTime={material.updatedAt}>{new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(material.updatedAt))}</time></td><td>{formatMaterialSize(material.sizeBytes)}</td><td><span className={`material-files__status is-${material.status}`}>{material.status === 'ready' ? <CheckCircleIcon size={14} aria-hidden="true" /> : null}{materialStatusLabel(material.status)}</span></td><td className="material-files__actions"><button type="button" aria-label={`删除文件 ${material.filename}`} title="删除文件" disabled={previewFiles || !!removingMaterialId} onClick={() => void removeMaterial(material)}><TrashIcon size={16} /></button></td>
      </tr>)}</tbody></table></div> : null}
      {!loading && !currentLibraryLoading && !failedProjects.length && !visibleMaterials.length ? <div className="material-files__empty" role="region" aria-label={!research.length ? '还没有研究' : '材料列表为空'}><FileTextIcon size={34} aria-hidden="true" /><h2>{query || ownerFilter ? '没有匹配的材料' : '从材料开始研究'}</h2><p>{query || ownerFilter ? '调整搜索词或分类，材料仍保存在所属研究中。' : '导入文档、访谈录音或视频，打开文件即可阅读和编码。'}</p>{!research.length ? <button type="button" className="qx-button" disabled={emptyUploading} onClick={() => emptyUploadInputRef.current?.click()}>{emptyUploading ? '正在导入…' : '导入研究材料'}</button> : null}</div> : null}
            </div>
      <input ref={emptyUploadInputRef} hidden type="file" multiple accept={RESEARCH_MATERIAL_ACCEPT} onChange={(event) => { const files = Array.from(event.target.files ?? []); event.target.value = ''; void startFromMaterials(files) }} />
          </section>

          <section className="research-hub__panel" role="tabpanel" id="research-panel-memory" aria-labelledby="research-tab-memory" hidden={activeTab !== 'memory'}>
            <div className="research-memory-preview">
              <span className="research-memory-preview__icon"><BrainIcon size={30} weight="light" /></span>
              <h2>{selectedResearch ? '让研究的上下文延续' : '属于你的长期记忆'}</h2>
              <p>{selectedResearch ? '研究问题、方法约定与重要决定，保留在这个项目中。' : '研究兴趣、写作偏好与长期背景，伴随你开展不同的研究。'}</p>
              <div className="research-memory-preview__scope"><span>{selectedResearch ? '作用于当前项目' : '作用于你的所有研究'}</span><span>记忆管理尚未接入</span></div>
            </div>
          </section>
        </div>
      </section>
    </div>
  </PageContent></PageShell>
}
