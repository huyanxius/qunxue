import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState, type FormEvent } from 'react'

import {
  confirmTheoryPlanViaApi,
  deferTheoryPlanViaApi,
  restoreTheoryWorkspaceViaApi,
  saveTheoryDecisionsViaApi,
} from './theoryDecisionApi'
import type {
  ConfirmedTheoryPlan,
  SavedDecisionSet,
  TheoryDecisionAction,
  TheoryWorkspace,
} from './types'
import './theory-decision-workspace.css'

const actionOptions: readonly [TheoryDecisionAction, string][] = [
  ['adopt', '采用'],
  ['exclude', '排除'],
  ['retain', '保留'],
  ['combine', '组合'],
  ['defer', '暂缓'],
  ['request_more_evidence', '请求补充依据'],
  ['revise_applicability', '修订适用性'],
]

interface CandidateDecisionForm {
  action: TheoryDecisionAction | ''
  reason: string
  revisedApplicability: string
  roleCode: string
  responsibility: string
}

const emptyDecision = (): CandidateDecisionForm => ({
  action: '',
  reason: '',
  revisedApplicability: '',
  roleCode: '',
  responsibility: '',
})

export function TheoryDecisionWorkspace({ taskId }: { readonly taskId: string }) {
  const queryClient = useQueryClient()
  const queryKey = ['theory-workspace', taskId] as const
  const workspace = useQuery({
    queryKey,
    queryFn: ({ signal }) => restoreTheoryWorkspaceViaApi(taskId, signal),
    retry: false,
  })
  const [forms, setForms] = useState<Record<string, CandidateDecisionForm>>({})
  const [saved, setSaved] = useState<SavedDecisionSet | null>(null)
  const [confirmed, setConfirmed] = useState<ConfirmedTheoryPlan | null>(null)
  const [deferredReason, setDeferredReason] = useState('')
  const [relation, setRelation] = useState({
    kind: '',
    explanation: '',
    premiseCompatibility: '',
    supportingEvidence: '',
    excludingEvidence: '',
    distinguishingEvidence: '',
  })

  useEffect(() => {
    if (!workspace.data) return
    const latest = workspace.data.latestDecisionSet
    setSaved(latest)
    setConfirmed(workspace.data.confirmedPlan)
    setDeferredReason(workspace.data.deferredPlan?.reason ?? '')
    setForms(Object.fromEntries(workspace.data.candidates.map((candidate) => {
      const decision = latest?.decisions?.find((item) => item.candidateId === candidate.candidateId)
      const assignment = latest?.useAssignments?.find((item) => item.candidateId === candidate.candidateId)
      return [candidate.candidateId, {
        ...emptyDecision(),
        action: decision?.action ?? '',
        reason: decision?.reason ?? '',
        revisedApplicability: decision?.revisedApplicability ?? '',
        roleCode: assignment?.roleCode ?? '',
        responsibility: assignment?.responsibility ?? '',
      }]
    })))
    const restoredRelation = latest?.relations?.[0]
    setRelation(restoredRelation ? {
      kind: restoredRelation.relationKind,
      explanation: restoredRelation.explanation,
      premiseCompatibility: restoredRelation.premiseCompatibility,
      supportingEvidence: restoredRelation.supportingEvidence[0] ?? '',
      excludingEvidence: restoredRelation.excludingEvidence[0] ?? '',
      distinguishingEvidence: restoredRelation.distinguishingEvidence[0] ?? '',
    } : {
      kind: '', explanation: '', premiseCompatibility: '', supportingEvidence: '',
      excludingEvidence: '', distinguishingEvidence: '',
    })
  }, [workspace.data])

  const selectedCandidates = useMemo(() => workspace.data?.candidates.filter((candidate) => {
    const action = forms[candidate.candidateId]?.action
    return action === 'adopt' || action === 'combine'
  }) ?? [], [forms, workspace.data])

  const saving = useMutation({
    mutationFn: saveTheoryDecisionsViaApi,
    onSuccess: (result) => setSaved(result),
  })
  const confirmation = useMutation({
    mutationFn: confirmTheoryPlanViaApi,
    onSuccess: (result) => {
      setConfirmed(result)
      queryClient.setQueryData<TheoryWorkspace>(queryKey, (current) => (
        current ? { ...current, confirmedPlan: result } : current
      ))
    },
  })
  const deferral = useMutation({
    mutationFn: deferTheoryPlanViaApi,
    onSuccess: (result) => setDeferredReason(result.reason),
  })

  function update(candidateId: string, changes: Partial<CandidateDecisionForm>) {
    setForms((current) => ({
      ...current,
      [candidateId]: { ...(current[candidateId] ?? emptyDecision()), ...changes },
    }))
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = workspace.data
    if (!data) return
    const chosenIds = selectedCandidates.map((item) => item.candidateId)
    saving.mutate({
      matchRunId: data.matchRunId,
      matchRunVersion: data.matchRunVersion,
      completionBasis: data.completionBasis,
      decisions: data.candidates.map((candidate) => {
        const form = forms[candidate.candidateId]
        return {
          candidateId: candidate.candidateId,
          candidateVersion: candidate.version,
          action: form.action as TheoryDecisionAction,
          reason: form.reason,
          relatedSourceIds: candidate.supportingEvidence
            .map((item) => item.sourceId)
            .filter((value): value is string => Boolean(value)),
          relatedCandidateIds: form.action === 'combine'
            ? chosenIds.filter((value) => value !== candidate.candidateId)
            : [],
          revisedApplicability: form.action === 'revise_applicability'
            ? form.revisedApplicability
            : null,
        }
      }),
      useAssignments: selectedCandidates.map((candidate) => ({
        candidateId: candidate.candidateId,
        roleCode: forms[candidate.candidateId].roleCode,
        responsibility: forms[candidate.candidateId].responsibility,
      })),
      relations: selectedCandidates.length > 1 ? [{
        candidateIds: chosenIds,
        relationKind: relation.kind,
        explanation: relation.explanation,
        premiseCompatibility: relation.premiseCompatibility,
        supportingEvidence: [relation.supportingEvidence],
        excludingEvidence: [relation.excludingEvidence],
        distinguishingEvidence: [relation.distinguishingEvidence],
      }] : [],
    })
  }

  if (workspace.isPending) return <p role="status">正在恢复候选与用户决定…</p>
  if (workspace.isError || !workspace.data) {
    return <p role="alert">暂时无法进入理论比较，请确认现象后重试。</p>
  }
  if (workspace.data.candidates.length === 0) {
    return (
      <section className="theory-empty">
        <p className="eyebrow">资格门禁已执行</p>
        <h2>没有达到资格门槛的候选</h2>
        <p>系统不会用未审校内容填满页面。你可以回到现象确认或等待知识发布补充。</p>
      </section>
    )
  }

  const hasNonFinal = Object.values(forms).some((item) => (
    item.action === 'defer'
    || item.action === 'request_more_evidence'
    || item.action === 'revise_applicability'
  ))

  return (
    <form className="theory-workspace" onSubmit={save}>
      <header className="theory-workspace__intro">
        <div>
          <p className="eyebrow">统一维度比较 · {workspace.data.candidates.length} 个候选</p>
          <h2>模型负责提出判断，你负责作出决定。</h2>
        </div>
        <p>发布 {workspace.data.knowledgeReleaseId.slice(0, 22)}</p>
      </header>

      <div className="theory-comparison" aria-label="候选理论比较">
        {workspace.data.candidates.map((candidate, index) => {
          const form = forms[candidate.candidateId] ?? emptyDecision()
          const selected = form.action === 'adopt' || form.action === 'combine'
          const detailSearch = new URLSearchParams({
            knowledge_release_id: workspace.data.knowledgeReleaseId,
            return_to: `/research/${taskId}/match`,
          })
          return (
            <article className="theory-card" key={candidate.candidateId}>
              <header>
                <span>0{index + 1}</span>
                <div>
                  <p>{candidate.originLabel} · {candidate.verificationLabel}</p>
                  <h3>{candidate.title}</h3>
                </div>
              </header>
              {!candidate.formalAdoptionEligible ? (
                <p className="theory-card__blocked">不可正式采用 · {candidate.adoptionBlockers.join('、')}</p>
              ) : null}
              <dl className="comparison-dimensions">
                <div><dt>问题焦点</dt><dd>{candidate.problemFocus}</dd></div>
                <div><dt>核心命题</dt><dd>{candidate.coreClaims.join('；')}</dd></div>
                <div><dt>分析层次</dt><dd>{candidate.analysisLevels.join('、')}</dd></div>
                <div><dt>适用条件</dt><dd>{candidate.prerequisites.join('、')}</dd></div>
                <div><dt>限制</dt><dd>{candidate.limitations.join('、') || '暂未记录'}</dd></div>
                <div><dt>证据缺口</dt><dd>{candidate.missingEvidence.join('、') || '暂无'}</dd></div>
              </dl>
              <section className="ai-judgement">
                <p className="content-owner">AI 适用性判断</p>
                <strong>{candidate.applicabilityJudgement}</strong>
                <p>{candidate.applicabilityRationale}</p>
                <small>{candidate.misuseBoundaries.join('；')}</small>
              </section>
              <section className="evidence-list">
                <h4>来源与核验</h4>
                {candidate.supportingEvidence.map((item) => (
                  <p key={item.evidenceRefId}>
                    <strong>{item.title}</strong> · {item.verificationStatus}<br />
                    <small>{item.useBoundary}</small>
                  </p>
                ))}
                {candidate.knowledgeId ? (
                  <a href={`/knowledge/${encodeURIComponent(candidate.knowledgeId)}?${detailSearch}`}>
                    查看知识详情
                  </a>
                ) : null}
              </section>
              <fieldset className="user-decision">
                <legend>你的决定</legend>
                <label>
                  决定
                  <select
                    aria-label={`对${candidate.title} 的决定`}
                    value={form.action}
                    onChange={(event) => update(candidate.candidateId, {
                      action: event.target.value as TheoryDecisionAction,
                    })}
                    required
                  >
                    <option value="">请选择</option>
                    {actionOptions.map(([value, label]) => (
                      <option key={value} value={value} disabled={(
                        (value === 'adopt' || value === 'combine')
                        && !candidate.formalAdoptionEligible
                      )}>{label}</option>
                    ))}
                  </select>
                </label>
                <label>
                  决定理由
                  <textarea value={form.reason} onChange={(event) => update(candidate.candidateId, { reason: event.target.value })} required rows={3} />
                </label>
                {form.action === 'revise_applicability' ? (
                  <label>
                    修订后的适用性
                    <textarea value={form.revisedApplicability} onChange={(event) => update(candidate.candidateId, { revisedApplicability: event.target.value })} required rows={2} />
                  </label>
                ) : null}
                {selected ? (
                  <div className="assignment-fields">
                    <label>
                      理论角色
                      <input value={form.roleCode} onChange={(event) => update(candidate.candidateId, { roleCode: event.target.value })} required placeholder="primary / complementary" />
                    </label>
                    <label>
                      解释分工
                      <textarea value={form.responsibility} onChange={(event) => update(candidate.candidateId, { responsibility: event.target.value })} required rows={2} />
                    </label>
                  </div>
                ) : null}
              </fieldset>
            </article>
          )
        })}
      </div>

      {selectedCandidates.length > 1 ? (
        <fieldset className="theory-relation">
          <legend>多理论关系</legend>
          <label>关系类型<input aria-label="关系类型" required value={relation.kind} onChange={(event) => setRelation({ ...relation, kind: event.target.value })} /></label>
          <label>关系说明<textarea aria-label="关系说明" required value={relation.explanation} onChange={(event) => setRelation({ ...relation, explanation: event.target.value })} /></label>
          <label>前提兼容性<textarea required value={relation.premiseCompatibility} onChange={(event) => setRelation({ ...relation, premiseCompatibility: event.target.value })} /></label>
          <label>支持组合的证据<textarea required value={relation.supportingEvidence} onChange={(event) => setRelation({ ...relation, supportingEvidence: event.target.value })} /></label>
          <label>排除组合的证据<textarea required value={relation.excludingEvidence} onChange={(event) => setRelation({ ...relation, excludingEvidence: event.target.value })} /></label>
          <label>区分理论的证据<textarea required value={relation.distinguishingEvidence} onChange={(event) => setRelation({ ...relation, distinguishingEvidence: event.target.value })} /></label>
        </fieldset>
      ) : null}

      <footer className="decision-actions">
        <button type="submit" disabled={saving.isPending}>
          {saving.isPending ? '正在保存…' : '保存用户决定'}
        </button>
        <button
          type="button"
          disabled={!saved || hasNonFinal || confirmation.isPending || Boolean(confirmed)}
          onClick={() => saved && confirmation.mutate({
            decisionSetId: saved.decisionSetId,
            version: saved.version,
          })}
        >
          {confirmed ? '理论方案已确认' : '确认理论方案'}
        </button>
        {hasNonFinal ? <p>暂缓、补充依据和适用性修订完成后才能确认。</p> : null}
        {saving.isError ? <p role="alert">决定保存失败，页面输入仍然保留。</p> : null}
        {confirmation.isError ? <p role="alert">服务端门禁未通过，请检查采用资格、角色和关系。</p> : null}
        {confirmed ? <p role="status">不可变理论方案已保存，刷新或重新登录后仍可恢复。</p> : null}
        <label>
          整体暂缓理由
          <textarea
            aria-label="整体暂缓理由"
            value={deferredReason}
            onChange={(event) => setDeferredReason(event.target.value)}
            rows={2}
          />
        </label>
        <button
          type="button"
          disabled={!deferredReason.trim() || deferral.isPending}
          onClick={() => deferral.mutate({
            matchRunId: workspace.data.matchRunId,
            matchRunVersion: workspace.data.matchRunVersion,
            reason: deferredReason,
          })}
        >暂缓整个理论方案</button>
        {workspace.data.deferredPlan || deferral.isSuccess ? (
          <p role="status">已暂缓：{deferredReason}</p>
        ) : null}
      </footer>
    </form>
  )
}
