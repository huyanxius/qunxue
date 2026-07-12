import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { CODEBOOK, REJECT_REASONS, SEGMENTS, TRANSCRIPT_TITLE } from '../data/demo'
import type { Segment } from '../data/demo'
import { finalLabel, setDecision, useDecisions } from '../store/decisions'
import { cohenKappa } from '../lib/kappa'

export default function Workbench() {
  const decisions = useDecisions()
  const [idx, setIdx] = useState(() => {
    const first = SEGMENTS.findIndex((s) => s.proposal && !decisions[s.id])
    return first === -1 ? 0 : first
  })
  const [pane, setPane] = useState<'none' | 'revise' | 'reject'>('none')
  const current = SEGMENTS[idx]
  const listRef = useRef<HTMLOListElement>(null)

  const coded = useMemo(() => SEGMENTS.filter((s) => s.proposal), [])
  const decided = coded.filter((s) => decisions[s.id])
  const disagreements = coded.filter((s) => {
    const d = decisions[s.id]
    return d && d.kind !== 'accept'
  })

  const kappa = useMemo(() => {
    const pairs: Array<[string, string]> = []
    for (const s of coded) {
      const fin = finalLabel(s.proposal!.label, decisions[s.id])
      if (fin) pairs.push([s.proposal!.label, fin])
    }
    return cohenKappa(pairs)
  }, [coded, decisions])

  const go = useCallback(
    (dir: 1 | -1) => {
      setPane('none')
      setIdx((i) => Math.min(SEGMENTS.length - 1, Math.max(0, i + dir)))
    },
    [],
  )

  const decide = useCallback(
    (seg: Segment, d: Parameters<typeof setDecision>[1]) => {
      setDecision(seg.id, d)
      setPane('none')
      const next = SEGMENTS.findIndex((s, i) => i > SEGMENTS.indexOf(seg) && s.proposal)
      if (next !== -1) setIdx(next)
    },
    [],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === 'j') go(1)
      if (e.key === 'k') go(-1)
      if (current.proposal) {
        if (e.key === 'a') decide(current, { kind: 'accept' })
        if (e.key === 'x') setPane('reject')
        if (e.key === 'e') setPane('revise')
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [current, decide, go])

  useEffect(() => {
    listRef.current
      ?.querySelector(`[data-seg="${current.id}"]`)
      ?.scrollIntoView({ block: 'nearest' })
  }, [current.id])

  return (
    <main className="workbench">
      <div className="wb-topbar">
        <span className="wb-title serif">{TRANSCRIPT_TITLE}</span>
        <div className="wb-stats">
          <span>
            裁决 <b className="num">{decided.length}</b>
            <i className="num"> / {coded.length}</i>
          </span>
          <span>
            分歧 <b className="num wb-red">{disagreements.length}</b>
          </span>
          <span>
            κ <b className="num">{kappa.kappa === null ? '—' : kappa.kappa.toFixed(2)}</b>
          </span>
        </div>
        <div className="wb-topbar-right">
          <span className="wb-keys">J/K 移动 · A 采纳 · E 修改 · X 驳回</span>
          <Link to="/report" className="btn btn-quiet wb-report-btn">
            查看报告
          </Link>
        </div>
      </div>

      <div className="wb-body">
        {/* 稿件 */}
        <ol className="wb-transcript" ref={listRef}>
          {SEGMENTS.map((s, i) => {
            const d = decisions[s.id]
            return (
              <li
                key={s.id}
                data-seg={s.id}
                className={[
                  'wb-seg',
                  i === idx ? 'is-current' : '',
                  d ? `is-${d.kind}` : '',
                ].join(' ')}
              >
                <button className="wb-seg-btn" onClick={() => { setIdx(i); setPane('none') }}>
                  <span className="wb-seg-meta num">
                    {String(s.id).padStart(2, '0')} · {s.speaker}
                  </span>
                  <span className="wb-seg-text serif">
                    {i === idx && s.proposal ? withQuote(s.text, s.proposal.quote) : s.text}
                  </span>
                  {d && (
                    <span className={`wb-seg-mark wb-mark-${d.kind}`}>
                      {d.kind === 'accept' ? '已采纳' : d.kind === 'revise' ? '已改判' : '已驳回'}
                    </span>
                  )}
                </button>
              </li>
            )
          })}
        </ol>

        {/* 页边批注 */}
        <aside className="wb-margin">
          {current.proposal ? (
            <ProposalCard
              seg={current}
              decisionKind={decisions[current.id]?.kind}
              pane={pane}
              setPane={setPane}
              onDecide={(d) => decide(current, d)}
            />
          ) : (
            <div className="wb-empty">
              <p className="serif">本段为访谈者提问,无编码建议。</p>
              <button className="btn btn-quiet" onClick={() => go(1)}>下一段</button>
            </div>
          )}
        </aside>
      </div>
    </main>
  )
}

function ProposalCard({
  seg,
  decisionKind,
  pane,
  setPane,
  onDecide,
}: {
  seg: Segment
  decisionKind?: 'accept' | 'revise' | 'reject'
  pane: 'none' | 'revise' | 'reject'
  setPane: (p: 'none' | 'revise' | 'reject') => void
  onDecide: (d: { kind: 'accept' } | { kind: 'revise'; newLabel: string } | { kind: 'reject'; reason: string }) => void
}) {
  const p = seg.proposal!
  const [reason, setReason] = useState(REJECT_REASONS[0])
  const [newLabel, setNewLabel] = useState(
    CODEBOOK.find((c) => c.label !== p.label)?.label ?? p.label,
  )

  return (
    <div className="wb-card">
      <div className="wb-card-head">
        <b>{p.label}</b>
        <span className="ai-mark">AI 初编</span>
      </div>
      <dl className="wb-card-body">
        <div>
          <dt>依据</dt>
          <dd className="serif">“{p.quote}”</dd>
        </div>
        <div>
          <dt>出处</dt>
          <dd>{p.source}</dd>
        </div>
        <div>
          <dt>置信</dt>
          <dd>
            <b className={`wb-conf wb-conf-${p.confidence}`}>{p.confidence}</b> · {p.rationale}
          </dd>
        </div>
      </dl>

      {decisionKind && pane === 'none' && (
        <p className={`wb-decided wb-mark-${decisionKind}`}>
          {decisionKind === 'accept' ? '你已采纳这条编码。' : decisionKind === 'revise' ? '你已改判这条编码。' : '你已驳回这条编码。'}
          可重新裁决覆盖。
        </p>
      )}

      {pane === 'none' && (
        <div className="wb-actions">
          <button className="btn btn-solid" onClick={() => onDecide({ kind: 'accept' })}>采纳</button>
          <button className="btn" onClick={() => setPane('revise')}>修改</button>
          <button className="btn wb-btn-reject" onClick={() => setPane('reject')}>驳回</button>
        </div>
      )}

      {pane === 'revise' && (
        <div className="wb-subpane">
          <p>改判为编码簿条目:</p>
          {CODEBOOK.map((c) => (
            <label key={c.label} className="choice choice-compact">
              <input
                type="radio"
                name="newLabel"
                checked={newLabel === c.label}
                onChange={() => setNewLabel(c.label)}
              />
              <span><b>{c.label}</b><i>{c.definition}</i></span>
            </label>
          ))}
          <div className="wb-actions">
            <button className="btn btn-solid" onClick={() => onDecide({ kind: 'revise', newLabel })}>确认改判</button>
            <button className="btn btn-quiet" onClick={() => setPane('none')}>取消</button>
          </div>
        </div>
      )}

      {pane === 'reject' && (
        <div className="wb-subpane">
          <p>驳回必须给理由——这是分歧报告的原料:</p>
          {REJECT_REASONS.map((r) => (
            <label key={r} className="choice choice-compact">
              <input type="radio" name="reason" checked={reason === r} onChange={() => setReason(r)} />
              <span><b>{r}</b></span>
            </label>
          ))}
          <div className="wb-actions">
            <button className="btn wb-btn-reject" onClick={() => onDecide({ kind: 'reject', reason })}>确认驳回</button>
            <button className="btn btn-quiet" onClick={() => setPane('none')}>取消</button>
          </div>
        </div>
      )}
    </div>
  )
}

function withQuote(text: string, quote: string) {
  const at = text.indexOf(quote)
  if (at === -1) return text
  return (
    <>
      {text.slice(0, at)}
      <mark>{quote}</mark>
      {text.slice(at + quote.length)}
    </>
  )
}
