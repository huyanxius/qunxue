import {
  ArrowClockwiseIcon,
  CheckCircleIcon,
  CircleNotchIcon,
  FilePlusIcon,
  IdentificationCardIcon,
  TrashIcon,
  WarningCircleIcon,
} from '@phosphor-icons/react'
import type { ChangeEvent, RefObject } from 'react'

import {
  formatMaterialSize,
  materialKindLabel,
  materialMediaLabel,
  RESEARCH_MATERIAL_ACCEPT,
  type ResearchMaterial,
  type ResearchMaterialKind,
} from './researchMaterialsModel'

const MATERIAL_KINDS: readonly ResearchMaterialKind[] = [
  'paper',
  'interview_transcript',
  'observation_record',
  'field_note',
  'other',
]

function formatUpdatedAt(value: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric' }).format(date)
}

/**
 * 状态列写的是「这份材料现在能干什么」，不是它的内部状态名。
 *
 * ready 不写「已就绪」而写片段数：每行都挂一个「已就绪」等于每行都没说话，而片段数直接
 * 回答了研究者真正要判断的事——这份材料能不能拿来引用、够不够细。processing 和 failed
 * 才是需要占用注意力的状态，只有它们配图标。
 */
function statusSummary(material: ResearchMaterial) {
  if (material.status === 'processing') {
    return { tone: 'processing' as const, icon: <CircleNotchIcon className="is-spinning" size={14} aria-hidden="true" />, text: '正在解析' }
  }
  if (material.status === 'failed') {
    return { tone: 'failed' as const, icon: <WarningCircleIcon size={14} aria-hidden="true" />, text: '解析失败' }
  }
  if (material.status === 'ready') {
    return material.segmentCount
      ? { tone: 'ready' as const, icon: null, text: `${material.segmentCount} 个可定位片段` }
      : { tone: 'ready' as const, icon: <CheckCircleIcon size={14} aria-hidden="true" />, text: '已就绪' }
  }
  return { tone: 'pending' as const, icon: null, text: '等待解析' }
}

type MaterialLibraryViewProps = {
  readonly materials: readonly ResearchMaterial[]
  readonly loading: boolean
  readonly error: string | null
  readonly notice: string | null
  readonly uploading: boolean
  readonly busyMaterialId: string | null
  readonly kind: ResearchMaterialKind
  readonly fileInputRef: RefObject<HTMLInputElement | null>
  readonly onKindChange: (kind: ResearchMaterialKind) => void
  readonly onFileChange: (event: ChangeEvent<HTMLInputElement>) => void
  readonly onOpenMaterial: (material: ResearchMaterial) => void
  readonly onOpenArchive: (material: ResearchMaterial) => void
  readonly onRetry: (material: ResearchMaterial) => void
  readonly onDelete: (material: ResearchMaterial) => void
}

/**
 * 材料库：这个研究里有哪些材料，我要打开哪一份、再加一份。
 *
 * 顺序上材料列表紧跟标题，上传收在列表末尾。上传是低频动作，把它摆在列表之前会让页面的
 * 第一屏回答不了「我有什么」这个唯一的问题。只有一份材料都没有时，上传才升级成页面主体。
 */
export function MaterialLibraryView({
  materials,
  loading,
  error,
  notice,
  uploading,
  busyMaterialId,
  kind,
  fileInputRef,
  onKindChange,
  onFileChange,
  onOpenMaterial,
  onOpenArchive,
  onRetry,
  onDelete,
}: MaterialLibraryViewProps) {
  const readyCount = materials.filter((material) => material.status === 'ready').length
  const empty = !loading && !materials.length

  const fileField = (
    <input
      ref={fileInputRef}
      className="qx-library__file-input"
      type="file"
      accept={RESEARCH_MATERIAL_ACCEPT}
      aria-label="选择研究材料文件"
      onChange={onFileChange}
    />
  )

  const kindField = (
    <label className="qx-library__kind">
      <span>类型</span>
      <select
        id="research-material-kind"
        value={kind}
        aria-label="材料类型"
        onChange={(event) => onKindChange(event.target.value as ResearchMaterialKind)}
      >
        {MATERIAL_KINDS.map((item) => <option key={item} value={item}>{materialKindLabel(item)}</option>)}
      </select>
    </label>
  )

  const pickButton = (
    <button type="button" className="qx-button qx-button--primary" disabled={uploading} onClick={() => fileInputRef.current?.click()}>
      {uploading ? <CircleNotchIcon className="is-spinning" size={16} aria-hidden="true" /> : <FilePlusIcon size={16} aria-hidden="true" />}
      {uploading ? '正在上传' : '选择文件'}
    </button>
  )

  return (
    <section className="qx-library" aria-label="材料库">
      <header className="qx-library__head">
        <span className="qx-eyebrow">当前研究</span>
        <h2 id="research-materials-heading">研究材料</h2>
        <p className="qx-library__summary">
          {materials.length
            ? `${materials.length} 份材料${readyCount ? ` · ${readyCount} 份可检索` : ''}`
            : '把论文、访谈和田野记录放在同一处'}
        </p>
      </header>

      {error ? <p className="qx-message is-error" role="alert"><WarningCircleIcon size={15} aria-hidden="true" />{error}</p> : null}
      {notice ? <p className="qx-message is-success" role="status"><CheckCircleIcon size={15} aria-hidden="true" />{notice}</p> : null}
      {loading ? <p className="qx-message" role="status"><CircleNotchIcon className="is-spinning" size={16} aria-hidden="true" />正在加载材料</p> : null}

      {empty ? (
        <div className="qx-library__empty">
          <FilePlusIcon size={26} aria-hidden="true" />
          <strong>还没有研究材料</strong>
          <p>先加入一份论文、访谈转录或田野笔记，Agent 才能在本次研究中引用它。</p>
          <div className="qx-library__empty-actions">
            {kindField}
            {pickButton}
          </div>
          <small>支持文档、MP3、M4A、WAV、MP4、WebM</small>
          {fileField}
        </div>
      ) : (
        <>
          <ul className="qx-library__list">
            {materials.map((material) => {
              const status = statusSummary(material)
              const busy = busyMaterialId === material.materialId
              return (
                <li className="qx-library__row" key={material.materialId} data-status={material.status}>
                  <button
                    type="button"
                    className="qx-library__open"
                    aria-label={`查看材料：${material.filename}`}
                    onClick={() => onOpenMaterial(material)}
                  >
                    <span className="qx-library__mark" aria-hidden="true">{materialMediaLabel(material.mediaType, material.filename)}</span>
                    <span className="qx-library__identity">
                      <strong>{material.filename}</strong>
                      <small>
                        {material.materialKind ? materialKindLabel(material.materialKind) : '研究材料'}
                        {' · '}{formatMaterialSize(material.sizeBytes)}
                        {formatUpdatedAt(material.updatedAt) ? ` · ${formatUpdatedAt(material.updatedAt)}` : ''}
                      </small>
                    </span>
                    <span className={`qx-library__status is-${status.tone}`}>{status.icon}{status.text}</span>
                  </button>
                  <div className="qx-library__row-actions">
                    <button type="button" aria-label={`材料档案：${material.filename}`} title="材料档案" onClick={() => onOpenArchive(material)}>
                      <IdentificationCardIcon size={15} aria-hidden="true" />
                    </button>
                    {material.status === 'failed' ? (
                      <button type="button" aria-label={`重新解析：${material.filename}`} title="重新解析" disabled={busy} onClick={() => onRetry(material)}>
                        {busy ? <CircleNotchIcon className="is-spinning" size={15} aria-hidden="true" /> : <ArrowClockwiseIcon size={15} aria-hidden="true" />}
                      </button>
                    ) : null}
                    <button type="button" aria-label={`删除材料：${material.filename}`} title="删除材料" disabled={busy} onClick={() => onDelete(material)}>
                      <TrashIcon size={15} aria-hidden="true" />
                    </button>
                  </div>
                </li>
              )
            })}
          </ul>

          <div className="qx-library__add">
            <div className="qx-library__add-copy">
              <strong>添加材料</strong>
              <small>支持文档、MP3、M4A、WAV、MP4、WebM</small>
            </div>
            <div className="qx-library__add-actions">
              {kindField}
              {pickButton}
            </div>
            {fileField}
          </div>
        </>
      )}
    </section>
  )
}
