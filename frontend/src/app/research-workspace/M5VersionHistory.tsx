import { ArrowCounterClockwiseIcon, CircleNotchIcon } from '@phosphor-icons/react'
import { useRef, useState } from 'react'

import './m5-research-delivery.css'

export type M5DocumentVersion = Readonly<{
  version: number
  createdAt: string
  actorLabel: string
  summary: string
  status: 'draft' | 'confirmed'
  restoredFromVersion?: number | null
}>

type Props = {
  currentVersion: number
  versions: readonly M5DocumentVersion[]
  onRestore: (version: number) => Promise<void>
}

function displayDate(value: string) {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed)
}

export function M5VersionHistory({ currentVersion, versions, onRestore }: Props) {
  const [busyVersion, setBusyVersion] = useState<number | null>(null)
  const [restoredVersion, setRestoredVersion] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const lockRef = useRef(false)

  async function restore(version: number) {
    if (version === currentVersion || lockRef.current) return
    lockRef.current = true
    setBusyVersion(version)
    setError(null)
    try {
      await onRestore(version)
      setRestoredVersion(version)
    } catch (failure: unknown) {
      setError(failure instanceof Error ? failure.message : '版本恢复失败，请重试。')
    } finally {
      lockRef.current = false
      setBusyVersion(null)
    }
  }

  return (
    <section className="m5-version-history" aria-labelledby="m5-version-heading" aria-busy={busyVersion !== null}>
      <div className="m5-panel-heading">
        <div>
          <span className="m5-panel-kicker">版本记录</span>
          <h3 id="m5-version-heading">可恢复历史</h3>
        </div>
        <span className="m5-status-chip">第 {currentVersion} 版</span>
      </div>
      <ol className="m5-version-list">
        {versions.map((version) => {
          const current = version.version === currentVersion
          return (
            <li key={version.version}>
              <div>
                <strong>第 {version.version} 版</strong>
                {current && <span>当前版本</span>}
                {version.status === 'confirmed' && <span>正式版</span>}
                <small>{displayDate(version.createdAt)} · {version.actorLabel}</small>
                <p>{version.summary}</p>
                {version.restoredFromVersion && <em>由第 {version.restoredFromVersion} 版恢复</em>}
              </div>
              {!current && (
                <button type="button" className="m5-quiet-button" disabled={busyVersion !== null} onClick={() => void restore(version.version)} aria-label={`恢复第 ${version.version} 版`}>
                  {busyVersion === version.version
                    ? <CircleNotchIcon className="m5-spin" aria-hidden="true" />
                    : <ArrowCounterClockwiseIcon aria-hidden="true" />}
                </button>
              )}
            </li>
          )
        })}
      </ol>
      <p className={`m5-live-message ${error ? 'is-error' : ''}`} role="status" aria-live="polite">
        {error ?? (restoredVersion ? `已从第 ${restoredVersion} 版创建新的可编辑版本。` : '')}
      </p>
    </section>
  )
}
