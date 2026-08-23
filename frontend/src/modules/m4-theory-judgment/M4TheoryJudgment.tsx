import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import './m4-theory-judgment.css'

export type M4ApplicabilityJudgement = 'applicable' | 'partially_applicable' | 'not_applicable' | 'insufficient_evidence'
export type M4DecisionAction = 'adopt' | 'exclude' | 'retain' | 'combine' | 'defer' | 'request_more_evidence' | 'revise_applicability'

export interface M4Evidence {
  readonly evidenceRefId: string
  readonly claim: string
  readonly excerpt: string | null
  readonly locator: string | null
  readonly sourceId: string | null
  readonly sourceTitle: string | null
  readonly sourceUrl: string | null
  readonly verificationStatus: 'verified' | 'system_summary' | 'pending'
  readonly useBoundary: string
}

export interface M4RelatedTheory {
  readonly theoryId: string
  readonly title: string
  readonly explanation: string
}

export interface M4Candidate {
  readonly candidateId: string
  readonly version: number
  readonly title: string
  readonly problemFocus: string
  readonly coreClaims: readonly string[]
  readonly analysisLevels: readonly string[]
  readonly prerequisites: readonly string[]
  readonly applicabilityJudgement: M4ApplicabilityJudgement
  readonly applicabilityRationale: string
  readonly supportingEvidence: readonly M4Evidence[]
  readonly conflictingEvidence: readonly M4Evidence[]
  readonly missingEvidence: readonly string[]
  readonly requestedMaterial: readonly string[]
  readonly limitations: readonly string[]
  readonly misuseBoundaries: readonly string[]
  readonly competingTheories: readonly M4RelatedTheory[]
  readonly complementaryTheories: readonly M4RelatedTheory[]
  readonly sourceIds: readonly string[]
  readonly reviewStatus: 'pre_review_completed' | null
  readonly formalAdoptionEligible: boolean
  readonly adoptionBlockers: readonly string[]
  readonly modelLabel: string
  readonly modelTraceId: string
}

export interface M4FailedCandidate {
  readonly candidateId: string
  readonly version: number
  readonly title: string
  readonly failureCode: string
  readonly retryable: boolean
}

export interface M4MatchRun {
  readonly matchRunId: string
  readonly taskId: string
  readonly version: number
  readonly status: 'generating' | 'awaiting_decision' | 'partial_failure' | 'no_reliable_candidate' | 'completed' | 'failed'
  readonly knowledgeReleaseId: string
  readonly completionBasis: 'complete' | 'partial' | 'partial_with_user_ack'
  readonly partialCompletionAcknowledged: boolean
  readonly failedCandidates: readonly M4FailedCandidate[]
  readonly candidates: readonly M4Candidate[]
}

export interface M4DraftDecision {
  readonly candidateId: string
  readonly candidateVersion: number
  readonly action: M4DecisionAction | null
  readonly reason: string
  readonly roleCode: string
  readonly responsibility: string
  readonly relatedSourceIds: readonly string[]
  readonly revisedApplicability: string
}

export interface M4DecisionDraft {
  readonly matchRunId: string
  readonly version: number
  readonly updatedAt: string
  readonly partialAcknowledgementReason: string
  readonly decisions: readonly M4DraftDecision[]
  readonly relation: {
    readonly explanation: string
    readonly premiseCompatibility: string
    readonly supportingEvidence: string
    readonly excludingEvidence: string
    readonly distinguishingEvidence: string
  }
}

export interface M4DecisionSet {
  readonly decisionSetId: string
  readonly version: number
  readonly canConfirm: boolean
  readonly knowledgeReleaseId: string
}

export interface M4ConfirmedPlan {
  readonly theoryPlanId: string
  readonly taskId: string
  readonly matchRunId: string
  readonly decisionSetId: string
  readonly knowledgeReleaseId: string
  readonly confirmedAt: string
}

export interface M4Workspace {
  readonly matchRun: M4MatchRun
  readonly draft: M4DecisionDraft
  readonly decisionSet: M4DecisionSet | null
  readonly confirmedPlan: M4ConfirmedPlan | null
}

export interface M4TaskContract {
  readonly taskId: string
  readonly taskVersion: number
  readonly matchRunId: string | null
  readonly theoryPlanId: string | null
  readonly phenomenonQueryId: string | null
  readonly phenomenonVersion: number | null
  readonly canStartMatching: boolean
}

interface KeyedRequest {
  readonly idempotencyKey: string
}

export interface M4TheoryJudgmentGateway {
  start(request: KeyedRequest & { readonly task: M4TaskContract }): Promise<M4Workspace>
  restore(request: { readonly task: M4TaskContract }): Promise<M4Workspace>
  saveDraft(request: KeyedRequest & { readonly matchRunId: string; readonly expectedVersion: number; readonly draft: M4DecisionDraft }): Promise<M4DecisionDraft>
  retryCandidate(request: KeyedRequest & { readonly matchRunId: string; readonly matchRunVersion: number; readonly candidateId: string; readonly candidateVersion: number }): Promise<M4Workspace>
  acknowledgePartial(request: KeyedRequest & { readonly matchRunId: string; readonly matchRunVersion: number; readonly failedCandidateIds: readonly string[]; readonly acknowledgedCandidateIds: readonly string[]; readonly reason: string }): Promise<M4Workspace>
  createDecisionSet(request: KeyedRequest & { readonly matchRun: M4MatchRun; readonly draft: M4DecisionDraft }): Promise<M4DecisionSet>
  confirmPlan(request: KeyedRequest & { readonly decisionSetId: string; readonly expectedVersion: number }): Promise<M4ConfirmedPlan>
}

export type M4FailureCode = 'catalog_not_ready' | 'network' | 'model_failed' | 'draft_conflict' | 'conflict' | 'not_found' | 'unknown'

export class M4TheoryJudgmentFailure extends Error {
  readonly code: M4FailureCode
  readonly context?: { readonly workspace?: M4Workspace }

  constructor(code: M4FailureCode, message: string, context?: { readonly workspace?: M4Workspace }) {
    super(message)
    this.name = 'M4TheoryJudgmentFailure'
    this.code = code
    this.context = context
  }
}

export interface M4TheoryJudgmentProps {
  readonly task: M4TaskContract
  readonly gateway: M4TheoryJudgmentGateway
  readonly onConfirmed?: (plan: M4ConfirmedPlan) => void
}

type SaveState = 'saved' | 'dirty' | 'saving' | 'error'

const actionLabels: Readonly<Record<M4DecisionAction, string>> = {
  adopt: '作为主理论',
  combine: '组合使用',
  retain: '作为备选',
  exclude: '排除',
  defer: '暂缓判断',
  request_more_evidence: '需要更多证据',
  revise_applicability: '修正适用范围',
}

const verdictLabels: Readonly<Record<M4ApplicabilityJudgement, string>> = {
  applicable: '适配',
  partially_applicable: '部分适配',
  not_applicable: '不适配',
  insufficient_evidence: '证据不足',
}

const activeActions = new Set<M4DecisionAction>(['adopt', 'combine'])

function requestKey(prefix: string) {
  const random = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`
  return `${prefix}-${random}`
}

function blankDecision(candidate: M4Candidate): M4DraftDecision {
  return {
    candidateId: candidate.candidateId,
    candidateVersion: candidate.version,
    action: null,
    reason: '',
    roleCode: 'secondary',
    responsibility: '',
    relatedSourceIds: candidate.sourceIds,
    revisedApplicability: '',
  }
}

function alignDraft(workspace: M4Workspace): M4DecisionDraft {
  const byCandidate = new Map(workspace.draft.decisions.map((item) => [item.candidateId, item]))
  return {
    ...workspace.draft,
    decisions: workspace.matchRun.candidates.map((candidate) => {
      const restored = byCandidate.get(candidate.candidateId)
      return restored?.candidateVersion === candidate.version ? restored : blankDecision(candidate)
    }),
  }
}

function failureFrom(reason: unknown): M4TheoryJudgmentFailure {
  if (reason instanceof M4TheoryJudgmentFailure) return reason
  return new M4TheoryJudgmentFailure('unknown', reason instanceof Error ? reason.message : '理论判断暂时无法完成。')
}

function startFailureCopy(failure: M4TheoryJudgmentFailure) {
  if (failure.code === 'catalog_not_ready') return { action: '重试检查', detail: '只有预审核完成并发布为内测固定版本的理论档案才会进入匹配。' }
  if (failure.code === 'network') return { action: '重新连接', detail: '恢复连接后会从服务器继续，不会生成静态候选。' }
  if (failure.code === 'model_failed') return { action: '重试匹配', detail: '本次失败不会成为研究结论。' }
  return { action: '重试恢复', detail: '重试会读取同一研究任务的已保存状态。' }
}

function ListBlock({ title, items, empty }: { readonly title: string; readonly items: readonly string[]; readonly empty: string }) {
  return (
    <section className="m4-theory-card__section">
      <h4>{title}</h4>
      {items.length ? <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="m4-theory-card__empty">{empty}</p>}
    </section>
  )
}

function EvidenceBlock({ title, items }: { readonly title: string; readonly items: readonly M4Evidence[] }) {
  return (
    <section className="m4-theory-card__section">
      <h4>{title}</h4>
      {items.length ? <ol className="m4-evidence-list">{items.map((item) => (
        <li key={item.evidenceRefId}>
          <p>{item.claim}</p>
          {item.excerpt ? <blockquote>{item.excerpt}</blockquote> : null}
          <div className="m4-evidence-list__source">
            {item.sourceUrl && item.sourceTitle
              ? <a href={item.sourceUrl} target="_blank" rel="noreferrer">{item.sourceTitle}<span aria-hidden="true"> ↗</span></a>
              : <span>{item.sourceTitle ?? item.sourceId ?? '来源名称未记录'}</span>}
            <span>{item.locator ?? '定位信息未记录'}</span>
            <span className={`m4-evidence-list__verification m4-evidence-list__verification--${item.verificationStatus}`}>
              {item.verificationStatus === 'verified' ? '已核验' : item.verificationStatus === 'system_summary' ? '系统摘要' : '待核验'}
            </span>
          </div>
          <small>{item.useBoundary}</small>
        </li>
      ))}</ol> : <p className="m4-theory-card__empty">当前正式档案未记录这类证据。</p>}
    </section>
  )
}

function RelatedTheoryBlock({ title, items }: { readonly title: string; readonly items: readonly M4RelatedTheory[] }) {
  return (
    <section className="m4-theory-card__section">
      <h4>{title}</h4>
      {items.length ? <ul className="m4-related-theories">{items.map((item) => <li key={item.theoryId}><strong>{item.title}</strong><span>{item.explanation}</span></li>)}</ul> : <p className="m4-theory-card__empty">当前发布未记录关联理论。</p>}
    </section>
  )
}

interface CandidateCardProps {
  readonly candidate: M4Candidate
  readonly decision: M4DraftDecision
  readonly disabled: boolean
  readonly onChange: (decision: M4DraftDecision) => void
}

function CandidateCard({ candidate, decision, disabled, onChange }: CandidateCardProps) {
  const choose = (action: M4DecisionAction) => onChange({
    ...decision,
    action,
    roleCode: action === 'adopt' ? 'primary' : decision.roleCode,
    relatedSourceIds: decision.relatedSourceIds.length ? decision.relatedSourceIds : candidate.sourceIds,
  })
  const usesTheory = decision.action !== null && activeActions.has(decision.action)
  const selectableSources = [...new Map(
    candidate.supportingEvidence
      .filter((item): item is M4Evidence & { readonly sourceId: string } => Boolean(item.sourceId))
      .map((item) => [item.sourceId, item]),
  ).values()]
  return (
    <article className="m4-theory-card" aria-label={`候选理论：${candidate.title}`}>
      <header className="m4-theory-card__header">
        <div>
          <span className={`m4-verdict m4-verdict--${candidate.applicabilityJudgement}`}>{verdictLabels[candidate.applicabilityJudgement]}</span>
          <h3>{candidate.title}</h3>
          <p>{candidate.problemFocus}</p>
        </div>
        <div className="m4-theory-card__trace" aria-label="判断溯源">
          <span>{candidate.modelLabel}</span>
          <code>{candidate.modelTraceId}</code>
        </div>
      </header>

      <p className="m4-theory-card__rationale">{candidate.applicabilityRationale}</p>
      {candidate.reviewStatus === 'pre_review_completed' ? <p className="m4-theory-card__review-status" role="note" aria-label="档案审核状态：预审核完成；仅供内测，后续仍可继续深度复核">
        <strong>预审核完成</strong>
        <span aria-hidden="true">·</span>
        <span>仅供内测，后续仍可继续深度复核</span>
      </p> : null}
      <div className="m4-theory-card__quick-facts">
        <span>分析层次</span>
        {candidate.analysisLevels.map((level) => <strong key={level}>{level}</strong>)}
      </div>

      <details open className="m4-theory-card__dossier">
        <summary>完整适配与风险档案</summary>
        <div className="m4-theory-card__dossier-body">
          <ListBlock title="核心主张" items={candidate.coreClaims} empty="当前档案未记录核心主张。" />
          <ListBlock title="适用前提" items={candidate.prerequisites} empty="当前档案未记录适用前提。" />
          <EvidenceBlock title="支持证据" items={candidate.supportingEvidence} />
          <EvidenceBlock title="冲突与反例" items={candidate.conflictingEvidence} />
          <ListBlock title="缺失证据" items={candidate.missingEvidence} empty="当前未标记缺失证据。" />
          <ListBlock title="建议补充的材料" items={candidate.requestedMaterial} empty="当前未提出额外材料请求。" />
          <ListBlock title="局限" items={candidate.limitations} empty="当前档案未记录局限，不代表该理论没有局限。" />
          <ListBlock title="误用边界" items={candidate.misuseBoundaries} empty="当前档案未记录误用边界。" />
          <RelatedTheoryBlock title="竞争理论" items={candidate.competingTheories} />
          <RelatedTheoryBlock title="可补充理论" items={candidate.complementaryTheories} />
          {candidate.adoptionBlockers.length ? <ListBlock title="正式采用阻断项" items={candidate.adoptionBlockers} empty="" /> : null}
        </div>
      </details>

      <fieldset className="m4-decision-editor" disabled={disabled}>
        <legend>我的判断</legend>
        <div className="m4-decision-editor__actions" role="group" aria-label={`${candidate.title}的决定`}>
          {(Object.keys(actionLabels) as M4DecisionAction[]).map((action) => {
            const blocked = !candidate.formalAdoptionEligible && activeActions.has(action)
            return <button key={action} type="button" aria-pressed={decision.action === action} disabled={blocked || disabled} title={blocked ? candidate.adoptionBlockers.join('；') : undefined} onClick={() => choose(action)}>{actionLabels[action]}</button>
          })}
        </div>
        <label>
          <span>选择{candidate.title}的理由</span>
          <textarea rows={3} value={decision.reason} onChange={(event) => onChange({ ...decision, reason: event.target.value })} aria-label={`选择${candidate.title}的理由`} placeholder="写下你使用、保留或排除它的具体理由" />
        </label>
        {usesTheory ? <div className="m4-decision-editor__role">
          <label>
            <span>在方案中的角色</span>
            <select value={decision.roleCode} onChange={(event) => onChange({ ...decision, roleCode: event.target.value })}>
              <option value="primary">主要解释视角</option>
              <option value="secondary">补充解释视角</option>
              <option value="contrast">对照解释</option>
              <option value="scope">限定适用范围</option>
            </select>
          </label>
          <label>
            <span>{candidate.title}在方案中的作用</span>
            <textarea rows={2} value={decision.responsibility} onChange={(event) => onChange({ ...decision, responsibility: event.target.value })} aria-label={`${candidate.title}在方案中的作用`} placeholder="它具体负责解释什么，不负责解释什么" />
          </label>
        </div> : null}
        {decision.action === 'revise_applicability' ? <label>
          <span>修正后的适用范围</span>
          <textarea rows={2} value={decision.revisedApplicability} onChange={(event) => onChange({ ...decision, revisedApplicability: event.target.value })} />
        </label> : null}
        {candidate.supportingEvidence.length ? <fieldset className="m4-source-selection">
          <legend>这个决定使用的来源</legend>
          {selectableSources.map((item) => {
            const sourceId = item.sourceId
            return <label key={sourceId}><input type="checkbox" checked={decision.relatedSourceIds.includes(sourceId)} onChange={(event) => onChange({ ...decision, relatedSourceIds: event.target.checked ? [...decision.relatedSourceIds, sourceId] : decision.relatedSourceIds.filter((id) => id !== sourceId) })} />{item.sourceTitle ?? sourceId}</label>
          })}
        </fieldset> : null}
      </fieldset>
    </article>
  )
}

function draftIsComplete(matchRun: M4MatchRun, draft: M4DecisionDraft) {
  if (!matchRun.candidates.length || draft.decisions.length !== matchRun.candidates.length) return false
  if (draft.decisions.some((item) => !item.action || !item.reason.trim())) return false
  const adopted = draft.decisions.filter((item) => item.action && activeActions.has(item.action))
  if (!adopted.length || adopted.some((item) => !item.roleCode.trim() || !item.responsibility.trim())) return false
  if (draft.decisions.some((item) => item.action === 'revise_applicability' && !item.revisedApplicability.trim())) return false
  if (adopted.length > 1 && Object.values(draft.relation).some((item) => !item.trim())) return false
  return true
}

export function M4TheoryJudgment({ task, gateway, onConfirmed }: M4TheoryJudgmentProps) {
  const [workspace, setWorkspace] = useState<M4Workspace | null>(null)
  const [draftState, setDraftState] = useState<M4DecisionDraft | null>(null)
  const [decisionSet, setDecisionSet] = useState<M4DecisionSet | null>(null)
  const [confirmedPlan, setConfirmedPlan] = useState<M4ConfirmedPlan | null>(null)
  const [saveState, setSaveState] = useState<SaveState>('saved')
  const [failure, setFailure] = useState<M4TheoryJudgmentFailure | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [operation, setOperation] = useState<'loading' | 'starting' | 'retrying' | 'acknowledging' | 'deciding' | 'confirming' | null>('loading')
  const [decisionStale, setDecisionStale] = useState(false)
  const saveAttempt = useRef<{ fingerprint: string; key: string } | null>(null)
  const acknowledgementAttempt = useRef<{ fingerprint: string; key: string } | null>(null)
  const decisionKey = useRef<string | null>(null)
  const confirmKey = useRef<string | null>(null)
  const restartKey = useRef<string | null>(null)
  const loadInFlight = useRef<Promise<void> | null>(null)
  const confirmPending = useRef(false)
  const confirmedEmitted = useRef(false)

  const adoptWorkspace = useCallback((next: M4Workspace) => {
    setWorkspace(next)
    setDraftState(alignDraft(next))
    setDecisionSet(next.decisionSet)
    setConfirmedPlan(next.confirmedPlan)
    setDecisionStale(false)
    setSaveState('saved')
    setFailure(null)
    saveAttempt.current = null
    acknowledgementAttempt.current = null
    decisionKey.current = null
    confirmKey.current = null
    restartKey.current = null
  }, [])

  const load = useCallback(() => {
    if (loadInFlight.current) return loadInFlight.current
    const attempt = (async () => {
      setFailure(null)
      setNotice(null)
      setOperation(task.matchRunId ? 'loading' : 'starting')
      try {
        const next = task.matchRunId
          ? await gateway.restore({ task })
          : await gateway.start({ task, idempotencyKey: requestKey('start-match') })
        adoptWorkspace(next)
      } catch (reason) {
        setFailure(failureFrom(reason))
      } finally {
        setOperation(null)
      }
    })()
    loadInFlight.current = attempt
    void attempt.finally(() => {
      if (loadInFlight.current === attempt) loadInFlight.current = null
    })
    return attempt
  }, [adoptWorkspace, gateway, task])

  useEffect(() => { void load() }, [load])

  const restartMatching = useCallback(async () => {
    if (operation) return
    setOperation('starting')
    setFailure(null)
    setNotice(null)
    if (!restartKey.current) restartKey.current = requestKey('restart-match')
    try {
      const next = await gateway.start({ task, idempotencyKey: restartKey.current })
      adoptWorkspace(next)
    } catch (reason) {
      setFailure(failureFrom(reason))
    } finally {
      setOperation(null)
    }
  }, [adoptWorkspace, gateway, operation, task])

  useEffect(() => {
    if (workspace?.matchRun.status !== 'generating') return
    const timer = window.setTimeout(() => {
      void gateway.restore({ task }).then(adoptWorkspace).catch((reason: unknown) => setFailure(failureFrom(reason)))
    }, 1400)
    return () => window.clearTimeout(timer)
  }, [adoptWorkspace, gateway, task, workspace?.matchRun.status, workspace?.matchRun.version])

  const updateDraft = useCallback((updater: (current: M4DecisionDraft) => M4DecisionDraft) => {
    setDraftState((current) => current ? updater(current) : current)
    setSaveState('dirty')
    setDecisionSet(null)
    setDecisionStale(true)
    setNotice(null)
    decisionKey.current = null
    confirmKey.current = null
    acknowledgementAttempt.current = null
  }, [])

  const persistDraft = useCallback(async (pendingDraft: M4DecisionDraft) => {
    if (!workspace) throw new M4TheoryJudgmentFailure('not_found', '理论匹配记录尚未恢复。')
    const fingerprint = JSON.stringify(pendingDraft)
    const attempt = saveAttempt.current?.fingerprint === fingerprint
      ? saveAttempt.current
      : { fingerprint, key: requestKey('draft') }
    saveAttempt.current = attempt
    setSaveState('saving')
    setFailure(null)
    const saved = await gateway.saveDraft({
      matchRunId: workspace.matchRun.matchRunId,
      expectedVersion: pendingDraft.version,
      draft: pendingDraft,
      idempotencyKey: attempt.key,
    })
    setDraftState(saved)
    setSaveState('saved')
    saveAttempt.current = null
    return saved
  }, [gateway, workspace])

  const recoverDraftFailure = useCallback((reason: unknown) => {
    const nextFailure = failureFrom(reason)
    if (nextFailure.code === 'draft_conflict' && nextFailure.context?.workspace) {
      adoptWorkspace(nextFailure.context.workspace)
      setFailure(new M4TheoryJudgmentFailure('draft_conflict', '其他页面已保存更新版本，已恢复服务器上的最新草稿。'))
    } else {
      setSaveState('error')
      setFailure(nextFailure)
    }
  }, [adoptWorkspace])

  const saveDraft = useCallback(async () => {
    if (!draftState || saveState !== 'dirty') return
    try {
      await persistDraft(draftState)
    } catch (reason) {
      recoverDraftFailure(reason)
    }
  }, [draftState, persistDraft, recoverDraftFailure, saveState])

  useEffect(() => {
    if (saveState !== 'dirty') return
    const timer = window.setTimeout(() => { void saveDraft() }, 700)
    return () => window.clearTimeout(timer)
  }, [saveDraft, saveState])

  const retryCandidate = useCallback(async (candidate: M4FailedCandidate) => {
    if (!workspace || operation) return
    setOperation('retrying')
    setFailure(null)
    try {
      const next = await gateway.retryCandidate({
        matchRunId: workspace.matchRun.matchRunId,
        matchRunVersion: workspace.matchRun.version,
        candidateId: candidate.candidateId,
        candidateVersion: candidate.version,
        idempotencyKey: requestKey(`retry-${candidate.candidateId}`),
      })
      adoptWorkspace(next)
      if (!next.matchRun.failedCandidates.length) setNotice('所有候选已完成判断')
    } catch (reason) {
      setFailure(failureFrom(reason))
    } finally {
      setOperation(null)
    }
  }, [adoptWorkspace, gateway, operation, workspace])

  const acknowledgePartial = useCallback(async () => {
    if (!workspace || !draftState?.partialAcknowledgementReason.trim() || operation || saveState === 'saving') return
    setOperation('acknowledging')
    setFailure(null)
    let draftPersisted = saveState === 'saved'
    try {
      const persistedDraft = draftPersisted
        ? draftState
        : await persistDraft(draftState)
      draftPersisted = true
      const payload = {
        matchRunId: workspace.matchRun.matchRunId,
        matchRunVersion: workspace.matchRun.version,
        failedCandidateIds: workspace.matchRun.failedCandidates.map((item) => item.candidateId),
        acknowledgedCandidateIds: workspace.matchRun.candidates.map((item) => item.candidateId),
        reason: persistedDraft.partialAcknowledgementReason.trim(),
      }
      const fingerprint = JSON.stringify(payload)
      const attempt = acknowledgementAttempt.current?.fingerprint === fingerprint
        ? acknowledgementAttempt.current
        : { fingerprint, key: requestKey('acknowledge-partial') }
      acknowledgementAttempt.current = attempt
      const next = await gateway.acknowledgePartial({
        ...payload,
        idempotencyKey: attempt.key,
      })
      adoptWorkspace(next)
      setNotice('已记录你继续使用部分候选的理由。')
    } catch (reason) {
      if (!draftPersisted) recoverDraftFailure(reason)
      else setFailure(failureFrom(reason))
    } finally {
      setOperation(null)
    }
  }, [adoptWorkspace, draftState, gateway, operation, persistDraft, recoverDraftFailure, saveState, workspace])

  const createDecisionSet = useCallback(async () => {
    if (!workspace || !draftState || !draftIsComplete(workspace.matchRun, draftState) || saveState !== 'saved' || operation) return
    setOperation('deciding')
    setFailure(null)
    if (!decisionKey.current) decisionKey.current = requestKey('decision-set')
    try {
      const next = await gateway.createDecisionSet({ matchRun: workspace.matchRun, draft: draftState, idempotencyKey: decisionKey.current })
      setDecisionSet(next)
      setDecisionStale(false)
      setNotice('完整理论决定已保存，请做最后确认。')
      confirmKey.current = null
    } catch (reason) {
      setFailure(failureFrom(reason))
    } finally {
      setOperation(null)
    }
  }, [draftState, gateway, operation, saveState, workspace])

  const confirmTheoryPlan = useCallback(async () => {
    if (!decisionSet || !decisionSet.canConfirm || decisionStale || confirmPending.current) return
    confirmPending.current = true
    setOperation('confirming')
    setFailure(null)
    if (!confirmKey.current) confirmKey.current = requestKey(`confirm-${decisionSet.decisionSetId}`)
    try {
      const plan = await gateway.confirmPlan({ decisionSetId: decisionSet.decisionSetId, expectedVersion: decisionSet.version, idempotencyKey: confirmKey.current })
      setConfirmedPlan(plan)
      if (!confirmedEmitted.current) {
        confirmedEmitted.current = true
        onConfirmed?.(plan)
      }
    } catch (reason) {
      setFailure(failureFrom(reason))
    } finally {
      confirmPending.current = false
      setOperation(null)
    }
  }, [decisionSet, decisionStale, gateway, onConfirmed])

  const adoptedDecisions = useMemo(() => draftState?.decisions.filter((item) => item.action && activeActions.has(item.action)) ?? [], [draftState])

  if (confirmedPlan) {
    return (
      <section className="m4-theory-judgment m4-theory-judgment--confirmed" aria-label="M4 理论判断">
        <div className="m4-confirmed" role="status">
          <span aria-hidden="true">✓</span>
          <div><strong>理论方案已确认</strong><p>方案已固定到发布 {confirmedPlan.knowledgeReleaseId}，后续阶段可用以下方案 ID 恢复。</p><code>{confirmedPlan.theoryPlanId}</code></div>
        </div>
      </section>
    )
  }

  if (operation === 'loading' || operation === 'starting') {
    return <section className="m4-theory-judgment" aria-label="M4 理论判断"><div className="m4-state m4-state--loading" role="status"><span className="m4-state__spinner" aria-hidden="true" />{operation === 'starting' ? '正在从正式知识发布生成候选…' : '正在恢复理论判断与决定草稿…'}</div></section>
  }

  if (failure && !workspace) {
    const copy = startFailureCopy(failure)
    return <section className="m4-theory-judgment" aria-label="M4 理论判断"><div className="m4-state m4-state--error" role="alert"><strong>{failure.message}</strong><p>{copy.detail}</p><button type="button" onClick={() => void load()}>{copy.action}</button></div></section>
  }

  if (!workspace || !draftState) {
    return <section className="m4-theory-judgment" aria-label="M4 理论判断"><div className="m4-state" role="status">这项研究尚未到达理论匹配阶段。</div></section>
  }

  const matchRun = workspace.matchRun
  const partialNeedsAcknowledgement = matchRun.status === 'partial_failure' && !matchRun.partialCompletionAcknowledged && matchRun.candidates.length > 0
  const decisionReady = draftIsComplete(matchRun, draftState) && saveState === 'saved' && !partialNeedsAcknowledgement

  return (
    <section className="m4-theory-judgment" aria-label="M4 理论判断">
      <header className="m4-theory-judgment__heading">
        <div><span>理论判断</span><h3>先看适配与风险，再做你的决定</h3><p>系统提供候选和证据边界；选择、理由与理论分工由你确认。</p></div>
        <div className="m4-release-stamp" aria-label="匹配发布"><span>固定发布</span><code>{matchRun.knowledgeReleaseId}</code></div>
      </header>

      {failure ? <div className="m4-inline-alert" role="alert"><strong>{failure.message}</strong>{saveState === 'error' ? <button type="button" onClick={() => { setSaveState('dirty'); setFailure(null) }}>重试保存</button> : null}</div> : null}
      {notice ? <p className="m4-inline-notice" aria-live="polite">{notice}</p> : null}

      {matchRun.status === 'generating' ? <div className="m4-state" role="status"><span className="m4-state__spinner" aria-hidden="true" /><strong>候选仍在生成</strong><p>页面会自动恢复，中途离开不会丢失进度。</p><button type="button" onClick={() => void load()}>立即刷新</button></div> : null}

      {matchRun.status === 'no_reliable_candidate' ? <div className="m4-state m4-state--empty" role="status"><strong>暂时没有足够可靠的候选理论</strong><p>你可以返回补充现象材料，或使用当前预审核版本重新匹配。</p><button type="button" onClick={() => void restartMatching()}>重新检查候选</button></div> : null}

      {matchRun.status === 'failed' ? <div className="m4-state m4-state--error" role="alert"><strong>理论判断服务本次未完成</strong><p>没有将未完成的模型结果当作候选。</p><button type="button" onClick={() => void load()}>重试匹配</button></div> : null}

      {matchRun.failedCandidates.length ? <section className="m4-partial-failure" role="alert" aria-label="候选判断部分失败">
        <header><div><strong>{matchRun.failedCandidates.length} 个候选未完成</strong><p>未完成候选不会被隐藏，也不会自动当作已排除。</p></div><span>{matchRun.completionBasis === 'partial_with_user_ack' ? '已确认风险' : '需处理'}</span></header>
        <ul>{matchRun.failedCandidates.map((item) => <li key={item.candidateId}><div><strong>{item.title}</strong><code>{item.failureCode}</code></div><button type="button" disabled={!item.retryable || operation === 'retrying'} onClick={() => void retryCandidate(item)}>{item.retryable ? `重试${item.title}` : '当前不可重试'}</button></li>)}</ul>
        {partialNeedsAcknowledgement ? <div className="m4-partial-failure__ack"><label><span>继续使用部分候选的理由</span><textarea rows={2} value={draftState.partialAcknowledgementReason} onChange={(event) => updateDraft((current) => ({ ...current, partialAcknowledgementReason: event.target.value }))} aria-label="继续使用部分候选的理由" /></label><button type="button" disabled={!draftState.partialAcknowledgementReason.trim() || operation === 'acknowledging' || saveState === 'saving'} onClick={() => void acknowledgePartial()}>确认以当前候选继续</button></div> : null}
      </section> : notice === '所有候选已完成判断' ? null : matchRun.candidates.length ? <p className="m4-all-complete">所有候选已完成判断</p> : null}

      {matchRun.candidates.length ? <div className="m4-theory-list">{matchRun.candidates.map((candidate) => {
        const decision = draftState.decisions.find((item) => item.candidateId === candidate.candidateId) ?? blankDecision(candidate)
        return <CandidateCard key={candidate.candidateId} candidate={candidate} decision={decision} disabled={Boolean(confirmedPlan)} onChange={(next) => updateDraft((current) => ({ ...current, decisions: current.decisions.map((item) => item.candidateId === candidate.candidateId ? next : item) }))} />
      })}</div> : null}

      {adoptedDecisions.length > 1 ? <fieldset className="m4-relation-editor">
        <legend>说明多理论如何共同工作</legend>
        <p>不用关系图代替判断。请用文字固定前提、证据和区分边界。</p>
        <label><span>关系说明</span><textarea rows={2} value={draftState.relation.explanation} onChange={(event) => updateDraft((current) => ({ ...current, relation: { ...current.relation, explanation: event.target.value } }))} /></label>
        <label><span>前提兼容性</span><textarea rows={2} value={draftState.relation.premiseCompatibility} onChange={(event) => updateDraft((current) => ({ ...current, relation: { ...current.relation, premiseCompatibility: event.target.value } }))} /></label>
        <label><span>支持组合的证据</span><textarea rows={2} value={draftState.relation.supportingEvidence} onChange={(event) => updateDraft((current) => ({ ...current, relation: { ...current.relation, supportingEvidence: event.target.value } }))} /></label>
        <label><span>排除组合的证据</span><textarea rows={2} value={draftState.relation.excludingEvidence} onChange={(event) => updateDraft((current) => ({ ...current, relation: { ...current.relation, excludingEvidence: event.target.value } }))} /></label>
        <label><span>区分各理论贡献的证据</span><textarea rows={2} value={draftState.relation.distinguishingEvidence} onChange={(event) => updateDraft((current) => ({ ...current, relation: { ...current.relation, distinguishingEvidence: event.target.value } }))} /></label>
      </fieldset> : null}

      {matchRun.candidates.length ? <footer className="m4-decision-footer">
        <div className={`m4-save-indicator m4-save-indicator--${saveState}`} role="status" aria-live="polite">
          <span aria-hidden="true">{saveState === 'saved' ? '✓' : saveState === 'saving' ? '···' : '•'}</span>
          {saveState === 'saved' ? '已保存到云端' : saveState === 'saving' ? '正在保存…' : saveState === 'error' ? '保存失败，内容仍在当前页面' : '尚未保存'}
        </div>
        <div className="m4-decision-footer__actions">
          <button type="button" disabled={!decisionReady || operation === 'deciding'} onClick={() => void createDecisionSet()}>{operation === 'deciding' ? '正在形成决定…' : '保存完整理论决定'}</button>
          {decisionSet && !decisionStale ? <button className="m4-confirm-button" type="button" disabled={!decisionSet.canConfirm || operation === 'confirming'} onClick={() => void confirmTheoryPlan()}>{operation === 'confirming' ? '正在确认…' : '确认理论方案'}</button> : null}
        </div>
        {!decisionReady ? <small>请先为每个候选选择动作并写下理由；正式采用的理论还需明确分工。</small> : null}
      </footer> : null}
    </section>
  )
}
