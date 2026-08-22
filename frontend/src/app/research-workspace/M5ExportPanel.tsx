import { CircleNotchIcon, FileTextIcon, FileTsIcon } from '@phosphor-icons/react'
import { useRef, useState } from 'react'

import './m5-research-delivery.css'

type ExportFormat = 'markdown' | 'json'

type Props = {
  confirmed: boolean
  gateReady: boolean
  saveState: 'saved' | 'saving' | 'unsaved'
  onExport: (format: ExportFormat) => Promise<void>
}

export function M5ExportPanel({ confirmed, gateReady, saveState, onExport }: Props) {
  const [busyFormat, setBusyFormat] = useState<ExportFormat | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState(false)
  const lockRef = useRef(false)
  const ready = confirmed && gateReady && saveState === 'saved'

  async function exportAs(format: ExportFormat) {
    if (!ready || lockRef.current) return
    lockRef.current = true
    setBusyFormat(format)
    setMessage(null)
    setError(false)
    try {
      await onExport(format)
      setMessage(`${format === 'markdown' ? 'Markdown' : 'JSON'} 成果包已下载。`)
    } catch (failure: unknown) {
      setMessage(failure instanceof Error ? failure.message : '成果包导出失败，请重试。')
      setError(true)
    } finally {
      lockRef.current = false
      setBusyFormat(null)
    }
  }

  return (
    <section className="m5-export-panel" aria-labelledby="m5-export-heading" aria-busy={busyFormat !== null}>
      <div className="m5-panel-heading">
        <div>
          <span className="m5-panel-kicker">完整研究成果包</span>
          <h3 id="m5-export-heading">导出与交付</h3>
        </div>
      </div>
      <p>Markdown 便于审阅与归档；JSON 保留章节、证据、决策、版本与来源结构。</p>
      <div className="m5-panel-actions">
        <button type="button" className="m5-secondary-button" disabled={!ready || busyFormat !== null} onClick={() => void exportAs('markdown')}>
          {busyFormat === 'markdown' ? <CircleNotchIcon className="m5-spin" aria-hidden="true" /> : <FileTextIcon aria-hidden="true" />}
          下载 Markdown
        </button>
        <button type="button" className="m5-primary-button" disabled={!ready || busyFormat !== null} onClick={() => void exportAs('json')}>
          {busyFormat === 'json' ? <CircleNotchIcon className="m5-spin" aria-hidden="true" /> : <FileTsIcon aria-hidden="true" />}
          下载 JSON
        </button>
      </div>
      <p className={`m5-live-message ${error ? 'is-error' : ''}`} role="status" aria-live="polite">
        {message ?? (!ready ? '研究完成并通过门禁后，才会生成可审查的成果包。' : '成果包已就绪。')}
      </p>
    </section>
  )
}
