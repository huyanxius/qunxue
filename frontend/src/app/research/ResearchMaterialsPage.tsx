import { FileDocIcon, FilePdfIcon, FileTextIcon, FolderOpenIcon, MarkdownLogoIcon, PlusIcon, VideoCameraIcon, WaveformIcon } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import { listMyResearchViaApi, type MyResearchItem } from '../../modules/account'
import {
  addResearchLibraryMaterial,
  formatMaterialSize,
  listResearchLibraryMaterials,
  materialMediaLabel,
  materialStatusLabel,
  RESEARCH_MATERIAL_ACCEPT,
  ResearchMaterialsPanel,
  type ResearchMaterial,
} from '../../modules/research-materials'
import { PageContent, PageShell } from '../ui/PageShell'
import { ResearchMaterialsShader } from './ResearchMaterialsShader'
import './research-materials-page.css'

type LibraryMaterial = { material: ResearchMaterial; research: MyResearchItem }

function MaterialTypeIcon({ material }: { material: ResearchMaterial }) {
  const format = materialMediaLabel(material.mediaType, material.filename)
  if (format === 'PDF') return <FilePdfIcon size={24} />
  if (format === 'DOCX') return <FileDocIcon size={24} />
  if (format === 'Markdown') return <MarkdownLogoIcon size={24} />
  if (format === 'MP3' || format === 'M4A' || format === 'WAV') return <WaveformIcon size={24} />
  if (format === 'MP4' || format === 'WebM') return <VideoCameraIcon size={24} />
  return <FileTextIcon size={24} />
}

/**
 * 材料始终属于一个 ResearchTask；页面只负责让用户找到该研究的材料面板。
 * 不在这里复制上传、解析或分析逻辑，避免出现第二套材料系统。
 */
export function ResearchMaterialsPage({ userId: _userId = null }: { userId?: string | null }) {
  const navigate = useNavigate()
  const uploadInputRef = useRef<HTMLInputElement>(null)
  const uploadPopoverRef = useRef<HTMLDivElement>(null)
  const [searchParams] = useSearchParams()
  const selectedTaskId = searchParams.get('task_id')
  const selectedMaterialId = searchParams.get('material_id')
  const [research, setResearch] = useState<MyResearchItem[]>([])
  const [libraryMaterials, setLibraryMaterials] = useState<LibraryMaterial[]>([])
  const [loading, setLoading] = useState(true)
  const [libraryLoading, setLibraryLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploadTaskId, setUploadTaskId] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadNotice, setUploadNotice] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    void listMyResearchViaApi()
      .then((items) => {
        if (active) {
          setResearch(items)
          setUploadTaskId((current) => current || items[0]?.taskId || '')
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
    if (loading || selectedTaskId) return undefined
    if (!research.length) {
      setLibraryLoading(false)
      return undefined
    }
    let active = true
    setLibraryLoading(true)
    void Promise.allSettled(research.map(async (item) => {
      const result = await listResearchLibraryMaterials(item.taskId)
      return result.items.map((material) => ({ material, research: item }))
    })).then((results) => {
      if (!active) return
      const materials = results.flatMap((result) => result.status === 'fulfilled' ? result.value : [])
      materials.sort((left, right) => right.material.updatedAt.localeCompare(left.material.updatedAt))
      setLibraryMaterials(materials)
      setLibraryLoading(false)
    })
    return () => {
      active = false
    }
  }, [loading, research, selectedTaskId])

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

  async function addMaterial(file: File) {
    if (!uploadTaskId) return
    setUploading(true)
    setUploadError(null)
    setUploadNotice(null)
    try {
      const material = await addResearchLibraryMaterial(uploadTaskId, file)
      const owner = research.find((item) => item.taskId === uploadTaskId)
      if (owner) setLibraryMaterials((current) => [{ material, research: owner }, ...current])
      setUploadOpen(false)
      setUploadNotice('材料已添加')
    } catch {
      setUploadError('材料添加失败，请重试。')
    } finally {
      setUploading(false)
    }
  }

  return (
    <PageShell workspace>
      <PageContent>
        {!selectedResearch ? <ResearchMaterialsShader /> : null}
        {loading ? <p className="research-materials-page__status" role="status">正在读取你的研究</p> : null}
        {error ? <p className="research-materials-page__status is-error" role="alert">{error}</p> : null}

        {!loading && !error && !research.length ? (
          <section className="research-materials-page__empty" aria-label="还没有研究">
            <FolderOpenIcon size={25} aria-hidden="true" />
            <h2>先建立一项研究</h2>
            <p>研究材料需要绑定到具体研究，建立后就能在这里持续导入和管理。</p>
            <Link className="research-materials-page__primary" to="/research/new"><PlusIcon size={16} />新建研究</Link>
          </section>
        ) : null}

        {!loading && !error && research.length && !selectedResearch ? (
          <section className="research-materials-page__library" aria-label="全部研究材料" role="region">
            <header className="research-materials-page__identity">
              <FileTextIcon size={18} weight="regular" aria-hidden="true" />
              <h1>研究材料</h1>
              <small>{libraryMaterials.length}</small>
            </header>
            <div className="research-materials-page__add-entry" ref={uploadPopoverRef}>
              <button
                className="work-home__start research-materials-page__add-material"
                type="button"
                aria-expanded={uploadOpen}
                aria-controls="research-materials-upload-popover"
                onClick={() => setUploadOpen((open) => !open)}
              >
                <PlusIcon size={17} weight="regular" aria-hidden="true" />添加材料
              </button>
              {uploadOpen ? (
                <div id="research-materials-upload-popover" className="qx-popover-surface research-materials-page__upload" role="dialog" aria-label="添加材料">
                  <select aria-label="材料所属研究" value={uploadTaskId} onChange={(event) => setUploadTaskId(event.target.value)}>
                    {research.map((item) => <option key={item.taskId} value={item.taskId}>{item.phenomenonSummary || '未命名研究'}</option>)}
                  </select>
                  <button type="button" disabled={uploading} onClick={() => uploadInputRef.current?.click()}>{uploading ? '正在上传…' : '选择文件'}</button>
                  <input ref={uploadInputRef} hidden type="file" accept={RESEARCH_MATERIAL_ACCEPT} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void addMaterial(file) }} />
                  {uploadError ? <span role="alert">{uploadError}</span> : null}
                </div>
              ) : null}
            </div>
            {uploadNotice ? <p className="research-materials-page__status" role="status">{uploadNotice}</p> : null}
            {libraryLoading ? <p className="research-materials-page__status" role="status">正在整理材料库</p> : null}
            {!libraryLoading && libraryMaterials.length ? (
              <div className="research-materials-page__material-grid">
                {libraryMaterials.map(({ material, research: owner }) => (
                  <Link
                    className="research-materials-page__material-card"
                    key={`${material.taskId}:${material.materialId}`}
                    to={`/research/materials?task_id=${encodeURIComponent(material.taskId)}&material_id=${encodeURIComponent(material.materialId)}`}
                    aria-label={`打开材料 ${material.filename}`}
                  >
                    <span className="research-materials-page__material-mark" aria-hidden="true"><MaterialTypeIcon material={material} /></span>
                    <div className="research-materials-page__material-copy">
                      <strong>{material.filename}</strong>
                      <p>{owner.phenomenonSummary || '未命名研究'}</p>
                    </div>
                    <div className="research-materials-page__material-meta">
                      <span>{materialMediaLabel(material.mediaType, material.filename)} · {formatMaterialSize(material.sizeBytes)}</span>
                      <span className={`is-${material.status}`}>{materialStatusLabel(material.status)}</span>
                    </div>
                  </Link>
                ))}
              </div>
            ) : null}
            {!libraryLoading && !libraryMaterials.length ? (
              <div className="research-materials-page__library-empty">
                <FolderOpenIcon size={22} aria-hidden="true" />
                <p>还没有材料。你可以从新建研究页放入第一批论文、访谈或田野记录。</p>
                <Link to="/research/new">去添加材料</Link>
              </div>
            ) : null}
          </section>
        ) : null}

        {selectedResearch ? (
          <section className="research-materials-page__reader" aria-label="材料阅读" role="region">
            <ResearchMaterialsPanel
              taskId={selectedResearch.taskId}
              initialMaterialId={selectedMaterialId}
              presentation="workspace"
              onClose={() => navigate('/research/materials')}
            />
          </section>
        ) : null}
      </PageContent>
    </PageShell>
  )
}
