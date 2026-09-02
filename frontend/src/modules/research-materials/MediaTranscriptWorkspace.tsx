import { useEffect, useRef, useState, type ChangeEvent } from 'react'

import {
  createCorrectedTranscriptVersion,
  getTranscriptionWorkspace,
  importTranscript,
  mediaContentUrl,
  startAutomaticTranscription,
} from './transcriptionApi'
import {
  formatTranscriptTime,
  transcriptSourceLabel,
  type TranscriptSegment,
  type TranscriptionWorkspace,
} from './transcriptionModel'

type MediaTranscriptWorkspaceProps = {
  readonly taskId: string
  readonly materialId: string
  readonly mediaType: string
  readonly initialParseId?: string | null
  readonly initialSegmentId?: string | null
  readonly onLocationChange?: (location: { versionId: string | null; segmentId: string | null }) => void
}

function errorMessage(cause: unknown, fallback: string): string {
  return cause instanceof Error && cause.message ? cause.message : fallback
}

function copySegments(segments: TranscriptSegment[]): TranscriptSegment[] {
  return segments.map((segment) => ({ ...segment }))
}

function formatElapsed(seconds: number): string {
  const minutes = Math.floor(seconds / 60)
  return `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}

export function MediaTranscriptWorkspace({ taskId, materialId, mediaType, initialParseId = null, initialSegmentId = null, onLocationChange }: MediaTranscriptWorkspaceProps) {
  const playerRef = useRef<HTMLMediaElement>(null)
  const importInputRef = useRef<HTMLInputElement>(null)
  const cueRefs = useRef(new Map<string, HTMLButtonElement>())
  const [workspace, setWorkspace] = useState<TranscriptionWorkspace | null>(null)
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [activeSegmentId, setActiveSegmentId] = useState<string | null>(initialSegmentId)
  const [draft, setDraft] = useState<TranscriptSegment[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [transcriptionStartedAt, setTranscriptionStartedAt] = useState<number | null>(null)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)

  async function load(signal?: AbortSignal, selectCurrent = false) {
    setLoading(true)
    setError(null)
    try {
      const next = await getTranscriptionWorkspace(taskId, materialId, signal)
      if (signal?.aborted) return
      setWorkspace(next)
      setSelectedVersionId((current) => {
        if (selectCurrent) return next.currentVersion?.versionId ?? next.versions[0]?.versionId ?? null
        if (initialParseId && next.versions.some((version) => version.versionId === initialParseId)) return initialParseId
        if (current && next.versions.some((version) => version.versionId === current)) return current
        return next.currentVersion?.versionId ?? next.versions[0]?.versionId ?? null
      })
    } catch (cause: unknown) {
      if ((cause as { name?: string } | null)?.name !== 'AbortError' && !signal?.aborted) {
        setError(errorMessage(cause, '转录时间轴暂时无法加载。'))
      }
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }

  useEffect(() => {
    const controller = new AbortController()
    setWorkspace(null)
    setSelectedVersionId(null)
    setEditing(false)
    setDraft([])
    void load(controller.signal)
    return () => controller.abort()
  }, [taskId, materialId])

  const selectedVersion = workspace?.versions.find((version) => version.versionId === selectedVersionId)
    ?? workspace?.currentVersion
    ?? null
  const canCorrect = selectedVersion?.isCurrent === true && !editing

  useEffect(() => {
    if (!initialParseId || !workspace?.versions.some((version) => version.versionId === initialParseId)) return
    setSelectedVersionId(initialParseId)
  }, [initialParseId, workspace?.versions])

  useEffect(() => {
    if (transcriptionStartedAt === null) return
    const updateElapsed = () => setElapsedSeconds(Math.floor((Date.now() - transcriptionStartedAt) / 1_000))
    updateElapsed()
    const timer = window.setInterval(updateElapsed, 1_000)
    return () => window.clearInterval(timer)
  }, [transcriptionStartedAt])

  useEffect(() => {
    onLocationChange?.({
      versionId: selectedVersion?.versionId ?? null,
      segmentId: activeSegmentId,
    })
  }, [activeSegmentId, onLocationChange, selectedVersion?.versionId])

  useEffect(() => {
    if (!initialSegmentId || !selectedVersion) return
    const target = selectedVersion.segments.find((segment) => segment.segmentId === initialSegmentId)
    if (!target) return
    setActiveSegmentId(initialSegmentId)
    if (playerRef.current && target.startMs !== null) playerRef.current.currentTime = target.startMs / 1_000
    cueRefs.current.get(initialSegmentId)?.scrollIntoView?.({ block: 'center' })
  }, [initialSegmentId, selectedVersion])

  function seek(segment: TranscriptSegment) {
    if (!playerRef.current || segment.startMs === null) return
    setActiveSegmentId(segment.segmentId)
    playerRef.current.currentTime = segment.startMs / 1_000
  }

  function beginCorrection() {
    if (!selectedVersion?.isCurrent) return
    setDraft(copySegments(selectedVersion.segments))
    setEditing(true)
    setError(null)
  }

  function updateDraft(index: number, patch: Partial<TranscriptSegment>) {
    setDraft((current) => current.map((segment, segmentIndex) => (
      segmentIndex === index ? { ...segment, ...patch } : segment
    )))
  }

  async function saveCorrection() {
    if (!selectedVersion?.isCurrent) return
    setBusy(true)
    setError(null)
    try {
      await createCorrectedTranscriptVersion(taskId, materialId, selectedVersion.versionId, draft)
      setEditing(false)
      await load(undefined, true)
    } catch (cause: unknown) {
      setError(errorMessage(cause, '转录校订保存失败。'))
    } finally {
      setBusy(false)
    }
  }

  async function handleImport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      await importTranscript(taskId, materialId, file)
      setEditing(false)
      await load(undefined, true)
    } catch (cause: unknown) {
      setError(errorMessage(cause, '转录稿导入失败。'))
    } finally {
      setBusy(false)
    }
  }

  async function startAutomatic() {
    setBusy(true)
    setError(null)
    setNotice('正在转写音频，请稍候…')
    setElapsedSeconds(0)
    setTranscriptionStartedAt(Date.now())
    try {
      await startAutomaticTranscription(taskId, materialId)
      await load(undefined, true)
      setTranscriptionStartedAt(null)
      setNotice('转写完成')
    } catch (cause: unknown) {
      setTranscriptionStartedAt(null)
      setNotice(null)
      setError(errorMessage(cause, '自动转写未能完成。'))
    } finally {
      setBusy(false)
    }
  }

  const mediaProps = {
    ref: playerRef as never,
    className: 'media-transcript__player',
    controls: true,
    preload: 'metadata' as const,
    src: mediaContentUrl(taskId, materialId),
    'aria-label': '原始媒体',
  }
  const transcriptionActive = transcriptionStartedAt !== null || (!loading && workspace?.status === 'processing')

  return (
    <section className="media-transcript" aria-label="媒体转录时间轴">
      <section className="media-transcript__source" aria-label="录音与转写操作">
        <header className="media-transcript__header">
          <div>
            <span>原始媒体</span>
            <h2>{mediaType.startsWith('video/') ? '视频' : '录音'}</h2>
            <p>保留原始材料；转录文本中的时间码可直接回到对应位置。</p>
          </div>
          <div className="media-transcript__actions">
            {workspace?.automaticAvailable ? (
              <button type="button" className="is-primary" onClick={() => { void startAutomatic() }} disabled={busy}>
                {transcriptionActive ? '正在转写…' : selectedVersion ? '重新转写' : '启动自动转写'}
              </button>
            ) : null}
            <button type="button" onClick={() => importInputRef.current?.click()} disabled={busy}>导入转录稿</button>
            <input
              ref={importInputRef}
              className="media-transcript__file-input"
              type="file"
              accept=".srt,.vtt,.txt,.docx,application/x-subrip,text/vtt,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              aria-label="选择转录稿"
              onChange={(event) => { void handleImport(event) }}
            />
          </div>
        </header>

        {mediaType.startsWith('video/') ? <video {...mediaProps} /> : <audio {...mediaProps} />}

        {loading ? <p className="media-transcript__notice" role="status">正在加载转录时间轴……</p> : null}
        {notice || transcriptionActive ? (
          <div className={`media-transcript__status${transcriptionActive ? ' is-active' : ''}`} role="status" aria-label="转写状态">
            <div>
              <strong>{transcriptionActive ? '正在转写音频' : notice}</strong>
              {transcriptionStartedAt !== null ? <span>已等待 {formatElapsed(elapsedSeconds)}</span> : null}
            </div>
            {transcriptionActive ? <>
              <p>预计约 1–3 分钟，长音频会更久。可以离开此页，完成后重新打开即可查看。</p>
              <span className="media-transcript__progress" aria-hidden="true"><i /></span>
            </> : null}
          </div>
        ) : null}
        {error ? <p className="media-transcript__notice is-error" role="alert">{error}</p> : null}
        {!loading && workspace && !workspace.automaticAvailable ? (
          <p className="media-transcript__notice">自动转写服务未配置</p>
        ) : null}
        {!loading && workspace?.status === 'failed' ? (
          <p className="media-transcript__notice is-error">自动转写失败。原始媒体已保留，可导入现成转录稿。</p>
        ) : null}
      </section>

      <section className="media-transcript__document" aria-label="转录文本">
        <header className="media-transcript__document-header">
          <div>
            <span>逐字记录</span>
            <h2>转录文本</h2>
          </div>
          <p>点击时间码播放对应片段。校订会另存为新版本，不覆盖底稿。</p>
        </header>

        {selectedVersion ? (
          <div className="media-transcript__version-bar">
            <label>
              <span>转录版本</span>
              <select
                aria-label="转录版本"
                value={selectedVersion.versionId}
                disabled={editing}
                onChange={(event) => {
                  setSelectedVersionId(event.target.value)
                  setActiveSegmentId(null)
                }}
              >
                {workspace?.versions.map((version) => (
                  <option key={version.versionId} value={version.versionId}>
                    版本 {version.version} · {transcriptSourceLabel(version.source)}{version.isCurrent ? ' · 当前' : ''}
                  </option>
                ))}
              </select>
            </label>
            <small>{selectedVersion.source === 'automatic' ? '机器底稿' : transcriptSourceLabel(selectedVersion.source)}</small>
            {canCorrect ? <button type="button" onClick={beginCorrection}>校订当前版本</button> : null}
          </div>
        ) : null}

        {editing ? (
        <form className="media-transcript__editor" onSubmit={(event) => { event.preventDefault(); void saveCorrection() }}>
          {draft.map((segment, index) => (
            <fieldset key={segment.segmentId}>
              <legend>第 {index + 1} 段</legend>
              <label>
                <span>说话人</span>
                <input aria-label={`第 ${index + 1} 段说话人`} value={segment.speaker ?? ''} onChange={(event) => updateDraft(index, { speaker: event.target.value || null })} />
              </label>
              <div className="media-transcript__time-inputs">
                <label>
                  <span>开始（毫秒）</span>
                  <input type="number" min="0" aria-label={`第 ${index + 1} 段开始时间`} value={segment.startMs ?? ''} onChange={(event) => updateDraft(index, { startMs: event.target.value === '' ? null : Number(event.target.value) })} />
                </label>
                <label>
                  <span>结束（毫秒）</span>
                  <input type="number" min="0" aria-label={`第 ${index + 1} 段结束时间`} value={segment.endMs ?? ''} onChange={(event) => updateDraft(index, { endMs: event.target.value === '' ? null : Number(event.target.value) })} />
                </label>
              </div>
              <label>
                <span>文字</span>
                <textarea rows={3} aria-label={`第 ${index + 1} 段文字`} value={segment.text} onChange={(event) => updateDraft(index, { text: event.target.value })} />
              </label>
            </fieldset>
          ))}
          <footer>
            <button type="button" onClick={() => setEditing(false)} disabled={busy}>取消</button>
            <button type="submit" disabled={busy || !draft.length}>{busy ? '正在保存' : '保存为新版本'}</button>
          </footer>
        </form>
      ) : selectedVersion ? (
        <div className="media-transcript__timeline">
          {selectedVersion.segments.map((segment) => (
            <button
              type="button"
              className="media-transcript__cue"
              key={segment.segmentId}
              onClick={() => seek(segment)}
              aria-current={segment.segmentId === activeSegmentId ? 'location' : undefined}
              ref={(element) => {
                if (element) cueRefs.current.set(segment.segmentId, element)
                else cueRefs.current.delete(segment.segmentId)
              }}
              disabled={segment.startMs === null}
              aria-label={`${formatTranscriptTime(segment.startMs)} ${segment.speaker ?? '未标记说话人'} ${segment.text}`}
            >
              <time>{formatTranscriptTime(segment.startMs)}</time>
              <span>
                <strong>{segment.speaker ?? '未标记说话人'}</strong>
                <span>{segment.text}</span>
              </span>
            </button>
          ))}
        </div>
      ) : !loading ? (
        <div className="media-transcript__empty">
          <strong>还没有转录版本</strong>
          <p>可导入 SRT、VTT、TXT 或 DOCX；即使自动服务不可用，原始媒体也不会丢失。</p>
        </div>
        ) : null}
      </section>
    </section>
  )
}

export type { MediaTranscriptWorkspaceProps }
