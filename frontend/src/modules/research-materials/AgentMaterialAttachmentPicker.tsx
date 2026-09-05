import { CheckIcon, FileTextIcon, XIcon } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'

import type { ResearchMaterial } from './researchMaterialsModel'
import './agent-material-attachment-picker.css'

type AgentMaterialAttachmentPickerProps = {
  inline?: boolean
  loading?: boolean
  materials: ResearchMaterial[]
  selectedIds: ReadonlySet<string>
  onToggle: (material: ResearchMaterial) => void
  onClose: () => void
  locale?: 'zh-CN' | 'en-US'
}

function unavailableReason(material: ResearchMaterial, locale: 'zh-CN' | 'en-US') {
  if (material.unavailableReason === 'ocr_required') {
    return locale === 'en-US' ? 'OCR is required but not configured' : '需要 OCR，当前未配置，暂不可检索'
  }
  if (material.unavailableReason === 'transcription_unavailable') {
    return locale === 'en-US' ? 'Transcription is not configured' : '转写服务未配置，暂不可检索'
  }
  if (material.unavailableReason === 'transcription_required') {
    return locale === 'en-US' ? 'Transcription is required first' : '需要先完成转写'
  }
  if (material.ingestionStatus === 'queued') {
    return locale === 'en-US' ? 'Queued for parsing; cannot attach yet' : '等待解析，暂时不能附加'
  }
  if (material.status === 'processing' || material.status === 'uploaded') {
    return locale === 'en-US' ? 'Still processing; cannot attach yet' : '正在解析，暂时不能附加'
  }
  if (material.status === 'failed') {
    return locale === 'en-US' ? 'Processing failed; retry it in the library' : '解析失败，请先在材料库重试'
  }
  return locale === 'en-US' ? 'Unavailable' : '当前不可附加'
}

export function AgentMaterialAttachmentPicker({
  materials,
  inline = false,
  loading = false,
  selectedIds,
  onToggle,
  onClose,
  locale = 'zh-CN',
}: AgentMaterialAttachmentPickerProps) {
  const [query, setQuery] = useState('')
  const visibleMaterials = materials.filter((material) => material.filename.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()))
  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  return (
    <div className={inline ? "agent-material-picker__inline" : "agent-material-picker__backdrop"} role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose()
    }}>
      <section className="agent-material-picker" role="dialog" aria-modal={inline ? undefined : true} aria-label={locale === 'en-US' ? 'Choose materials for this turn' : '选择本轮材料'}>
        <header>
          <div>
            <strong>{locale === 'en-US' ? 'Choose research materials' : '选择研究材料'}</strong>
            <small>{locale === 'en-US' ? 'The Agent will only search the selected files for this turn.' : '本轮 Agent 将只检索你选中的材料。'}</small>
          </div>
          <button type="button" aria-label={locale === 'en-US' ? 'Close' : '关闭'} onClick={onClose}><XIcon size={17} /></button>
        </header>
        <input className="agent-material-picker__search" type="search" aria-label={locale === 'en-US' ? 'Search files' : '搜索文件'} placeholder={locale === 'en-US' ? 'Search files' : '搜索文件名'} value={query} onChange={(event) => setQuery(event.target.value)} />
        <div className="agent-material-picker__list" aria-busy={loading}>
          {visibleMaterials.length ? visibleMaterials.map((material) => {
            const ready = material.status === 'ready'
            const selected = selectedIds.has(material.materialId)
            return (
              <label key={material.materialId} className={`agent-material-picker__item${ready ? '' : ' is-disabled'}`}>
                <input
                  type="checkbox"
                  checked={selected}
                  disabled={!ready}
                  aria-label={`${material.filename}${ready ? '' : `，${unavailableReason(material, locale)}`}`}
                  onChange={() => onToggle(material)}
                />
                <span className="agent-material-picker__file"><FileTextIcon size={18} /></span>
                <span className="agent-material-picker__copy">
                  <b>{material.filename}</b>
                  <small>{ready ? (locale === 'en-US' ? 'Ready to search' : '可检索') : unavailableReason(material, locale)}</small>
                </span>
                {selected ? <CheckIcon size={16} weight="bold" /> : null}
              </label>
            )
          }) : <p className="agent-material-picker__empty">{loading ? (locale === 'en-US' ? 'Loading files…' : '正在加载文件…') : query ? (locale === 'en-US' ? 'No matching files.' : '没有找到匹配的文件。') : (locale === 'en-US' ? 'No files yet. Upload one to get started.' : '还没有文件，可以直接上传。')}</p>}
        </div>
        <footer>
          <span>{locale === 'en-US' ? `${selectedIds.size} selected` : `已选择 ${selectedIds.size} 份`}</span>
          <button type="button" onClick={onClose}>{locale === 'en-US' ? 'Done' : '完成'}</button>
        </footer>
      </section>
    </div>
  )
}
