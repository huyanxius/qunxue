import { useEffect, useMemo, useState } from 'react'

import './research-framework.css'


export type ResolutionAction = 'accept' | 'reject' | 'defer' | 'override'

export type FrameworkResolution = {
  findingId: string
  action: ResolutionAction
  reason: string
}

export type ResearchFrameworkView = {
  frameworkId: string
  revisionId: string
  version: number
  status: 'draft' | 'under_review' | 'revision_required' | 'ready_to_confirm' | 'confirmed'
  contentOrigin: 'system_generated' | 'user_modified'
  revisionReason: string | null
  confirmedResearchQuestion: string
  theoryPlan: string[]
  conceptMappings: Array<{
    candidateId: string
    theoryConcept: string
    meaningInStudy: string
    empiricalIndicators: string[]
    unresolvedQuestions: string[]
  }>
  materialRequirements: string[]
  evidenceConstraints: string[]
  alternativeExplanations: string[]
  ethicalBoundaries: string[]
  nextActions: string[]
  scopeAndLimitations: string[]
  unresolvedItems: string[]
  audit: null | {
    auditId: string
    isStale: boolean
    findings: Array<{
      findingId: string
      severity: 'info' | 'warning' | 'blocking'
      summary: string
      reason: string
      impact: string
      recommendation: string
      blocking: boolean
    }>
  }
}

type Props = {
  framework: ResearchFrameworkView
  versions: ResearchFrameworkView[]
  busy?: boolean
  onSave: (next: ResearchFrameworkView, reason: string) => void | Promise<void>
  onReview: () => void | Promise<void>
  onResolve: (resolutions: FrameworkResolution[]) => void | Promise<void>
  onConfirm: (resolutions: FrameworkResolution[]) => void | Promise<void>
}

const resolutionLabels: Record<ResolutionAction, string> = {
  accept: '接受意见',
  reject: '拒绝意见',
  defer: '暂缓处理',
  override: '带理由覆盖',
}

function lines(value: string): string[] {
  return value.split('\n').map((item) => item.trim()).filter(Boolean)
}

function ListEditor({
  id,
  label,
  value,
  onChange,
}: {
  id: string
  label: string
  value: string[]
  onChange: (value: string[]) => void
}) {
  return (
    <label className="framework-list-editor" htmlFor={id}>
      <span>{label}</span>
      <textarea
        id={id}
        aria-label={label}
        rows={Math.max(3, value.length + 1)}
        value={value.join('\n')}
        onChange={(event) => onChange(lines(event.target.value))}
      />
      <small>每行一项</small>
    </label>
  )
}

function ReadonlyList({ label, value }: { label: string; value: string[] }) {
  return (
    <div className="framework-readonly-list" aria-label={label}>
      <ul>{value.map((item) => <li key={item}>{item}</li>)}</ul>
      <small>该部分来自系统草稿；修改其他可编辑部分时会原样保留。</small>
    </div>
  )
}

export function ResearchFrameworkWorkspace({
  framework,
  versions,
  busy = false,
  onSave,
  onReview,
  onResolve,
  onConfirm,
}: Props) {
  const [editing, setEditing] = useState(framework)
  const [revisionReason, setRevisionReason] = useState('')
  const [resolutionState, setResolutionState] = useState<Record<string, FrameworkResolution>>({})
  const [resolutionError, setResolutionError] = useState('')

  useEffect(() => {
    setEditing(framework)
    setRevisionReason('')
    setResolutionState(Object.fromEntries(
      (framework.audit?.findings ?? []).map((finding) => [finding.findingId, {
        findingId: finding.findingId,
        action: 'defer' as const,
        reason: '',
      }]),
    ))
    setResolutionError('')
  }, [framework])

  const resolutions = useMemo(
    () => Object.values(resolutionState),
    [resolutionState],
  )
  const canConfirm = Boolean(framework.audit && !framework.audit.isStale) && (
    framework.status === 'ready_to_confirm'
    || framework.audit?.findings
      .filter((finding) => finding.blocking)
      .every((finding) => {
        const resolution = resolutionState[finding.findingId]
        return resolution?.action === 'override' && Boolean(resolution.reason.trim())
      })
  )

  function updateList<K extends keyof ResearchFrameworkView>(key: K, value: ResearchFrameworkView[K]) {
    setEditing((current) => ({ ...current, [key]: value }))
  }

  function saveResolutions() {
    const missingOverrideReason = resolutions.some(
      (item) => item.action === 'override' && !item.reason.trim(),
    )
    if (missingOverrideReason) {
      setResolutionError('覆盖阻断意见必须说明理由。')
      return
    }
    if (resolutions.some((item) => !item.reason.trim())) {
      setResolutionError('每条审校处理都必须记录理由。')
      return
    }
    setResolutionError('')
    void onResolve(resolutions)
  }

  return (
    <div className="framework-workspace">
      <header className="framework-workspace__header">
        <div>
          <p className="framework-kicker">FRAMEWORK / V{framework.version}</p>
          <h1>研究框架</h1>
          <p>系统建议与你的修改分开保留；只有你能确认最终版本。</p>
        </div>
        <div className="framework-version-mark">
          <span className={`origin origin--${framework.contentOrigin}`}>
            {framework.contentOrigin === 'system_generated' ? '系统草稿' : '用户修改'}
          </span>
          <strong>{framework.status === 'confirmed' ? '已确认' : `版本 ${framework.version}`}</strong>
        </div>
      </header>

      <div className="framework-layout">
        <main className="framework-document">
          <section className="framework-section framework-section--question">
            <span className="section-index">01</span>
            <div>
              <h2>研究问题</h2>
              <p className="research-question">{editing.confirmedResearchQuestion}</p>
            </div>
          </section>

          <section className="framework-section">
            <span className="section-index">02</span>
            <div>
              <h2>理论方案</h2>
              <ul>{editing.theoryPlan.map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
          </section>

          <section className="framework-section">
            <span className="section-index">03</span>
            <div>
              <h2>概念映射</h2>
              <div className="concept-grid">
                {editing.conceptMappings.map((item) => (
                  <article key={item.candidateId}>
                    <strong>{item.theoryConcept}</strong>
                    <p>{item.meaningInStudy}</p>
                    <small>{item.empiricalIndicators.join(' · ')}</small>
                  </article>
                ))}
              </div>
            </div>
          </section>

          <section className="framework-section">
            <span className="section-index">04</span>
            <div>
              <h2>材料要求</h2>
              <ReadonlyList label="材料要求" value={editing.materialRequirements} />
            </div>
          </section>

          <section className="framework-section">
            <span className="section-index">05</span>
            <div>
              <h2>证据约束</h2>
              <ReadonlyList label="证据约束" value={editing.evidenceConstraints} />
            </div>
          </section>

          <section className="framework-section framework-section--editable">
            <span className="section-index">06</span>
            <div>
              <h2>替代解释</h2>
              <ListEditor id="alternative-explanations" label="替代解释" value={editing.alternativeExplanations} onChange={(value) => updateList('alternativeExplanations', value)} />
            </div>
          </section>

          <section className="framework-section framework-section--editable">
            <span className="section-index">07</span>
            <div>
              <h2>伦理边界</h2>
              <ListEditor id="ethical-boundaries" label="伦理边界" value={editing.ethicalBoundaries} onChange={(value) => updateList('ethicalBoundaries', value)} />
            </div>
          </section>

          <section className="framework-section framework-section--editable">
            <span className="section-index">08</span>
            <div>
              <h2>下一步行动</h2>
              <ListEditor id="next-actions" label="下一步行动" value={editing.nextActions} onChange={(value) => updateList('nextActions', value)} />
            </div>
          </section>

          {framework.status !== 'confirmed' ? (
            <section className="revision-controls" aria-label="版本保存">
              <label htmlFor="revision-reason">
                <span>修改理由</span>
                <input id="revision-reason" value={revisionReason} onChange={(event) => setRevisionReason(event.target.value)} />
              </label>
              <button type="button" disabled={busy || !revisionReason.trim()} onClick={() => void onSave(editing, revisionReason.trim())}>
                保存为新版本
              </button>
            </section>
          ) : null}
        </main>

        <aside className="framework-sidebar">
          <section className="review-panel">
            <div className="review-panel__heading">
              <p>AUDIT</p>
              <h2>审校意见</h2>
            </div>
            {framework.audit?.isStale ? <p className="stale-notice">框架已修改，该审校已失效。</p> : null}
            {framework.audit?.findings.map((finding) => {
              const resolution = resolutionState[finding.findingId] ?? {
                findingId: finding.findingId,
                action: 'defer' as const,
                reason: '',
              }
              return (
                <article className={`finding finding--${finding.severity}`} key={finding.findingId}>
                  <span>{finding.blocking ? '阻断' : '建议'}</span>
                  <h3>{finding.summary}</h3>
                  <p>{finding.reason}</p>
                  <dl><dt>影响</dt><dd>{finding.impact}</dd><dt>建议</dt><dd>{finding.recommendation}</dd></dl>
                  <label htmlFor={`action-${finding.findingId}`}>
                    <span>处理方式</span>
                    <select
                      id={`action-${finding.findingId}`}
                      aria-label="处理方式"
                      value={resolution.action}
                      onChange={(event) => setResolutionState((current) => ({
                        ...current,
                        [finding.findingId]: { ...resolution, action: event.target.value as ResolutionAction },
                      }))}
                    >
                      {Object.entries(resolutionLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                    </select>
                  </label>
                  <label htmlFor={`reason-${finding.findingId}`}>
                    <span>处理理由</span>
                    <textarea
                      id={`reason-${finding.findingId}`}
                      aria-label="处理理由"
                      value={resolution.reason}
                      onChange={(event) => setResolutionState((current) => ({
                        ...current,
                        [finding.findingId]: { ...resolution, reason: event.target.value },
                      }))}
                    />
                  </label>
                </article>
              )
            })}
            {resolutionError ? <p className="resolution-error" role="alert">{resolutionError}</p> : null}
            {framework.audit?.findings.length ? (
              <button type="button" className="secondary-action" disabled={busy} onClick={saveResolutions}>保存审校处理</button>
            ) : null}
            {framework.status !== 'confirmed' ? (
              <div className="review-actions">
                <button type="button" className="secondary-action" disabled={busy} onClick={() => void onReview()}>重新审校</button>
                <button
                  type="button"
                  className="primary-action"
                  disabled={busy || !canConfirm}
                  onClick={() => void onConfirm(resolutions.filter((item) => item.reason.trim()))}
                >
                  由我确认框架
                </button>
              </div>
            ) : <p className="confirmed-note">这是你确认的最终框架。</p>}
          </section>

          <section className="version-panel">
            <p>HISTORY</p>
            <h2>版本记录</h2>
            <ol>
              {[...versions].reverse().map((version) => (
                <li key={version.revisionId}>
                  <strong>V{version.version}</strong>
                  <span>{version.contentOrigin === 'system_generated' ? '系统草稿' : '用户修改'}</span>
                  {version.revisionReason ? <small>{version.revisionReason}</small> : null}
                </li>
              ))}
            </ol>
          </section>
        </aside>
      </div>
    </div>
  )
}
