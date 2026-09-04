import { CheckIcon, FileTextIcon, XIcon } from '@phosphor-icons/react'
import { useEffect } from 'react'

import type { ResearchMaterial } from './researchMaterialsModel'
import './agent-material-attachment-picker.css'

type AgentMaterialAttachmentPickerProps = {
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
  selectedIds,
  onToggle,
  onClose,
  locale = 'zh-CN',
}: AgentMaterialAttachmentPickerProps) {
  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  return (
    <div className="agent-material-picker__backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose()
    }}>
      <section className="agent-material-picker" role="dialog" aria-modal="true" aria-label={locale === 'en-US' ? 'Choose materials for this turn' : '选择本轮材料'}>
        <header>
          <div>
            <strong>{locale === 'en-US' ? 'Choose research materials' : '选择研究材料'}</strong>
            <small>{locale === 'en-US' ? 'The Agent will only search the selected files for this turn.' : '本轮 Agent 将只检索你选中的材料。'}</small>
          </div>
          <button type="button" aria-label={locale === 'en-US' ? 'Close' : '关闭'} onClick={onClose}><XIcon size={17} /></button>
        </header>
        <div className="agent-material-picker__list">
          {materials.length ? materials.map((material) => {
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
          }) : <p className="agent-material-picker__empty">{locale === 'en-US' ? 'No materials in this task yet.' : '当前任务还没有研究材料。'}</p>}
        </div>
        <footer>
          <span>{locale === 'en-US' ? `${selectedIds.size} selected` : `已选择 ${selectedIds.size} 份`}</span>
          <button type="button" onClick={onClose}>{locale === 'en-US' ? 'Done' : '完成'}</button>
        </footer>
      </section>
    </div>
  )
}
