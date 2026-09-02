import {
  ArchiveBoxIcon,
  CheckCircleIcon,
  DownloadSimpleIcon,
  FileArrowUpIcon,
  ShieldCheckIcon,
  WarningCircleIcon,
} from '@phosphor-icons/react'
import { useCallback, useEffect, useState, type ChangeEvent } from 'react'

import {
  exportResearchArchive,
  listResearchAuditEvents,
  previewQdpxImport,
  type ResearchArchiveDownload,
  type QdpxImportPreview,
  type ResearchAuditEvent,
} from './researchExchangeApi'
import './research-exchange.css'

type ResearchArchivePanelProps = {
  readonly taskId: string
}

function downloadArchive(value: ResearchArchiveDownload) {
  const url = URL.createObjectURL(value.blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = value.filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function formatTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export function ResearchArchivePanel({ taskId }: ResearchArchivePanelProps) {
  const [events, setEvents] = useState<ResearchAuditEvent[]>([])
  const [auditLoading, setAuditLoading] = useState(true)
  const [exporting, setExporting] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [exported, setExported] = useState<ResearchArchiveDownload | null>(null)
  const [preview, setPreview] = useState<QdpxImportPreview | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadAudit = useCallback(async (signal?: AbortSignal) => {
    setAuditLoading(true)
    try {
      setEvents(await listResearchAuditEvents(taskId, signal))
    } catch (cause: unknown) {
      if ((cause as { name?: string } | null)?.name !== 'AbortError') {
        setError(cause instanceof Error ? cause.message : '审计记录暂时无法加载。')
      }
    } finally {
      if (!signal?.aborted) setAuditLoading(false)
    }
  }, [taskId])

  useEffect(() => {
    const controller = new AbortController()
    void loadAudit(controller.signal)
    return () => controller.abort()
  }, [loadAudit])

  async function handleExport() {
    setExporting(true)
    setError(null)
    try {
      const value = await exportResearchArchive(taskId)
      setExported(value)
      downloadArchive(value)
      await loadAudit()
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : '研究归档导出失败。')
    } finally {
      setExporting(false)
    }
  }

  async function handlePreview(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setPreviewing(true)
    setPreview(null)
    setError(null)
    try {
      setPreview(await previewQdpxImport(taskId, file))
      await loadAudit()
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : 'QDPX 文件校验失败。')
    } finally {
      setPreviewing(false)
    }
  }

  return (
    <section className="research-exchange" role="region" aria-label="项目归档与交换">
      <header className="research-exchange__header">
        <div>
          <h2>研究归档</h2>
          <p>保存研究证据链、跨工具交换与审计记录。</p>
        </div>
        <ShieldCheckIcon size={24} aria-hidden="true" />
      </header>

      <div className="research-exchange__actions">
        <article>
          <ArchiveBoxIcon size={22} aria-hidden="true" />
          <div>
            <h3>完整研究归档</h3>
            <p>BagIt 校验包、QDPX、原生恢复 JSON、损失报告、审计与文稿成果。</p>
          </div>
          <button className="qx-button qx-button--primary" type="button" disabled={exporting} onClick={() => void handleExport()}>
            <DownloadSimpleIcon size={16} aria-hidden="true" />
            {exporting ? '正在归档…' : '导出研究归档'}
          </button>
        </article>

        <article>
          <FileArrowUpIcon size={22} aria-hidden="true" />
          <div>
            <h3>QDPX 导入预览</h3>
            <p>按官方 XSD 校验并清点项目内容，不自动合并、重绑或写入当前研究。</p>
          </div>
          <label className={`qx-button${previewing ? ' is-disabled' : ''}`}>
            <span>{previewing ? '正在校验…' : '选择 QDPX 文件'}</span>
            <input
              type="file"
              accept=".qdpx,application/vnd.qdpx,application/zip"
              aria-label="选择 QDPX 文件"
              disabled={previewing}
              onChange={(event) => void handlePreview(event)}
            />
          </label>
        </article>
      </div>

      {error && (
        <div className="research-exchange__notice qx-notice-surface is-error" role="alert">
          <WarningCircleIcon size={17} aria-hidden="true" />
          {error}
        </div>
      )}

      {exported && (
        <div className="research-exchange__notice qx-notice-surface">
          <CheckCircleIcon size={17} aria-hidden="true" />
          <span>
            归档已生成：{exported.lossCount} 项交换损失，其中 {exported.blockingLossCount} 项阻断；
            完整说明已写入归档。
          </span>
        </div>
      )}

      {preview && (
        <article className="research-exchange__preview">
          <div>
            <span>QDPX {preview.specification_version}</span>
            <h3>{preview.project.name}</h3>
            <p>{preview.project.origin}</p>
          </div>
          <dl>
            <div><dt>材料</dt><dd>{preview.project.source_count}</dd></div>
            <div><dt>编码</dt><dd>{preview.project.code_count}</dd></div>
            <div><dt>备忘</dt><dd>{preview.project.memo_count}</dd></div>
            <div><dt>案例</dt><dd>{preview.project.case_count}</dd></div>
          </dl>
          <p>只完成校验与预览，未写入当前研究。</p>
        </article>
      )}

      <section className="research-exchange__audit" aria-labelledby="research-exchange-audit-title">
        <div>
          <h3 id="research-exchange-audit-title">交换审计</h3>
        </div>
        {auditLoading ? <p>正在读取审计记录…</p> : events.length === 0 ? (
          <p>还没有项目交换记录。</p>
        ) : (
          <ol>
            {events.map((event) => (
              <li key={event.event_id}>
                <code>{event.event_type}</code>
                <span>对象版本 {event.object_version ?? '—'}</span>
                <time dateTime={event.occurred_at}>{formatTime(event.occurred_at)}</time>
              </li>
            ))}
          </ol>
        )}
      </section>
    </section>
  )
}
