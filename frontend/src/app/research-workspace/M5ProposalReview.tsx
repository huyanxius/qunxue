import { ArrowRightIcon, CheckIcon, CircleNotchIcon, XIcon } from '@phosphor-icons/react'
import { useRef, useState } from 'react'

import './m5-research-delivery.css'

export type M5Proposal = Readonly<{
  proposalId: string
  status: 'pending' | 'accepted' | 'rejected' | 'aborted'
  kind: 'create' | 'revise_section'
  targetLabel: string
  before: string | null
  after: string
  rationale: string
  decisionReason?: string | null
  provenance: Readonly<{
    releaseLabel: string
    modelLabel: string
    agentRunLabel: string
  }>
}>

type Props = {
  proposal: M5Proposal
  onAccept: (proposalId: string) => Promise<void>
  onReject: (proposalId: string, reason: string) => Promise<void>
}

export function M5ProposalReview({ proposal, onAccept, onReject }: Props) {
  const [busyAction, setBusyAction] = useState<'accept' | 'reject' | null>(null)
  const [result, setResult] = useState<'accepted' | 'rejected' | null>(null)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const lockRef = useRef(false)
  const finalStatus = result ?? proposal.status
  const pending = finalStatus === 'pending'

  async function decide(action: 'accept' | 'reject') {
    if (!pending || lockRef.current) return
    const rejectionReason = reason.trim()
    if (action === 'reject' && !rejectionReason) {
      setError('请填写拒绝理由。')
      return
    }
    lockRef.current = true
    setBusyAction(action)
    setError(null)
    try {
      if (action === 'accept') await onAccept(proposal.proposalId)
      else await onReject(proposal.proposalId, rejectionReason)
      setResult(action === 'accept' ? 'accepted' : 'rejected')
    } catch (failure: unknown) {
      setError(failure instanceof Error ? failure.message : '处理建议失败，请重试。')
    } finally {
      lockRef.current = false
      setBusyAction(null)
    }
  }

  return (
    <article className="m5-proposal" aria-label={`${proposal.targetLabel}修改建议`} aria-busy={busyAction !== null}>
      <div className="m5-panel-heading">
        <div>
          <span className="m5-panel-kicker">Agent 建议 · {proposal.kind === 'create' ? '创建草稿' : '局部修改'}</span>
          <h3>{proposal.targetLabel}</h3>
        </div>
        <span className={`m5-status-chip is-${finalStatus}`}>
          {{ pending: '等待决定', accepted: '已接受', rejected: '已拒绝', aborted: '生成已中止' }[finalStatus]}
        </span>
      </div>

      <p className="m5-proposal__rationale">{proposal.rationale}</p>
      <div className="m5-proposal__comparison">
        <section aria-label="修改前">
          <span>修改前</span>
          <p>{proposal.before?.trim() || '新建内容，无既有正文。'}</p>
        </section>
        <ArrowRightIcon className="m5-proposal__arrow" aria-hidden="true" />
        <section aria-label="建议稿">
          <span>建议稿</span>
          <p>{proposal.after}</p>
        </section>
      </div>

      <dl className="m5-provenance">
        <div><dt>知识</dt><dd>{proposal.provenance.releaseLabel}</dd></div>
        <div><dt>模型</dt><dd>{proposal.provenance.modelLabel}</dd></div>
        <div><dt>运行</dt><dd>{proposal.provenance.agentRunLabel}</dd></div>
      </dl>

      {pending && (
        <label className="m5-proposal__reason">
          <span>拒绝理由（必填，将写入审阅记录）</span>
          <textarea required value={reason} onChange={(event) => setReason(event.target.value)} rows={2} />
        </label>
      )}

      <div className="m5-panel-actions">
        <button type="button" className="m5-secondary-button" disabled={!pending || busyAction !== null || !reason.trim()} onClick={() => void decide('reject')}>
          {busyAction === 'reject' ? <CircleNotchIcon className="m5-spin" aria-hidden="true" /> : <XIcon aria-hidden="true" />}
          拒绝建议
        </button>
        <button type="button" className="m5-primary-button" disabled={!pending || busyAction !== null} onClick={() => void decide('accept')}>
          {busyAction === 'accept' ? <CircleNotchIcon className="m5-spin" aria-hidden="true" /> : <CheckIcon aria-hidden="true" />}
          接受建议
        </button>
      </div>
      <p className={`m5-live-message ${error ? 'is-error' : ''}`} role="status" aria-live="polite">
        {error ?? (finalStatus === 'accepted'
          ? '建议已接受，正式文档已生成新版本。'
          : finalStatus === 'rejected'
            ? '建议已拒绝，正式文档没有被修改。'
            : finalStatus === 'aborted'
              ? proposal.decisionReason || '本次生成未完成，正式文档没有被修改。'
            : '')}
      </p>
    </article>
  )
}
