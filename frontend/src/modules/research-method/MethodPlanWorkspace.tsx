import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  confirmMethodPlan, createMethodPlan, getCurrentMethodPlan, listMethodPlanVersions,
  getMethodPlanPrerequisites,
  resolveMethodPlanReview, reviewMethodPlan, restoreMethodPlan, updateMethodPlan,
  type MethodKind, type MethodPlan,
} from './researchMethodApi'
import './research-method.css'

const METHOD_LABELS: Record<MethodKind, string> = {
  undecided: '暂缓决定',
  qualitative: '质性研究',
  quantitative: '定量研究',
  mixed: '混合研究',
}

const METHOD_DESCRIPTIONS: Record<MethodKind, string> = {
  undecided: '保留路径比较与下一次决定所需信息，暂不把方法选择写成既定事实。',
  qualitative: '围绕材料、编码、备忘、跨案例比较与理论检验建立解释性设计。',
  quantitative: '把理论概念落实为变量、测量、样本与可检验的统计分析计划。',
  mixed: '说明两类证据为何结合、如何排序整合，以及冲突时共同结论的边界。',
}

const STATUS_LABELS: Record<MethodPlan['status'], string> = {
  draft: '草案',
  under_review: '审校中',
  confirmed: '已确认',
  stale: '依据已变化',
}

const REQUIRED_SECTIONS: Record<MethodKind, string[]> = {
  undecided: ['decision'],
  qualitative: ['design', 'research_object', 'sampling', 'material_acquisition', 'analysis', 'credibility', 'reflexivity', 'ethics'],
  quantitative: ['design', 'operationalization', 'variables_indicators', 'hypotheses', 'measurement', 'sampling', 'analysis_plan', 'conditions', 'limitations', 'ethics'],
  mixed: ['design', 'rationale', 'sequence', 'weight', 'integration', 'conflict_handling', 'common_conclusions', 'ethics'],
}

function errorMessage(cause: unknown, fallback: string) {
  return cause instanceof Error ? cause.message : fallback
}

export function MethodPlanWorkspace({ taskId }: { taskId: string }) {
  const [plan, setPlan] = useState<MethodPlan | null>(null)
  const [versions, setVersions] = useState<MethodPlan[]>([])
  const [kind, setKind] = useState<MethodKind>('undecided')
  const [rationale, setRationale] = useState('')
  const [sections, setSections] = useState<MethodPlan['sections']>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [reviewNote, setReviewNote] = useState('')
  const [reviewBlocking, setReviewBlocking] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const current = await getCurrentMethodPlan(taskId)
      setPlan(current)
      if (current) {
        setKind(current.method_kind)
        setRationale(current.rationale)
        setSections(current.sections)
        setVersions(await listMethodPlanVersions(current.plan_id))
      } else {
        setVersions([])
      }
    } catch (cause) {
      setError(errorMessage(cause, '方法计划加载失败。'))
    } finally {
      setLoading(false)
    }
  }, [taskId])

  useEffect(() => { void load() }, [load])

  async function create() {
    setBusy(true)
    setError(null)
    try {
      const prerequisites = await getMethodPlanPrerequisites(taskId)
      const created = await createMethodPlan(taskId, {
        framework_id: prerequisites.frameworkId,
        theory_plan_id: prerequisites.theoryPlanId,
        method_kind: kind,
      })
      setPlan(created)
      setKind(created.method_kind)
      setRationale(created.rationale)
      setSections(created.sections)
      setVersions([created])
    } catch (cause) {
      setError(errorMessage(cause, '方法计划创建失败。'))
    } finally {
      setBusy(false)
    }
  }

  async function save() {
    if (!plan) return
    setBusy(true)
    setError(null)
    try {
      const updated = await updateMethodPlan(plan.plan_id, {
        expected_version: plan.version,
        method_kind: kind,
        rationale,
        change_summary: '用户编辑方法计划',
        sections,
      })
      setPlan(updated)
      setKind(updated.method_kind)
      setRationale(updated.rationale)
      setSections(updated.sections)
      setVersions((items) => [updated, ...items.filter((item) => item.version !== updated.version)])
    } catch (cause) {
      setError(errorMessage(cause, '方法计划保存失败。'))
    } finally {
      setBusy(false)
    }
  }

  async function act(action: () => Promise<MethodPlan>) {
    setBusy(true)
    setError(null)
    try {
      const updated = await action()
      setPlan(updated)
      setSections(updated.sections)
      setKind(updated.method_kind)
      setRationale(updated.rationale)
      setVersions((items) => [updated, ...items.filter((item) => item.version !== updated.version)])
    } catch (cause) {
      setError(errorMessage(cause, '方法计划操作失败。'))
    } finally {
      setBusy(false)
    }
  }

  const userDecisionCount = useMemo(
    () => sections.filter((section) => section.source === 'user').length,
    [sections],
  )
  const pendingReviewCount = plan?.reviews.filter((review) => review.blocking && !review.resolved_at).length ?? 0
  const missingDecisionCount = REQUIRED_SECTIONS[kind].filter((key) => {
    const section = sections.find((item) => item.key === key)
    return !section || section.source !== 'user'
  }).length
  const canConfirm = Boolean(plan && plan.status !== 'confirmed' && plan.status !== 'stale' && missingDecisionCount === 0 && pendingReviewCount === 0)

  if (loading) {
    return (
      <section className="research-method" aria-label="研究方法计划">
        <p className="research-method__muted" role="status">正在恢复方法计划…</p>
      </section>
    )
  }

  if (!plan && error) {
    return (
      <section className="research-method" aria-label="研究方法计划">
        <p className="research-method__error qx-notice-surface" role="alert">{error}</p>
        <button className="qx-button" type="button" onClick={() => void load()}>重新加载</button>
      </section>
    )
  }

  if (!plan) {
    return (
      <section className="research-method" aria-label="研究方法计划">
        <header className="research-method__intro">
          <p className="research-method__eyebrow">研究设计</p>
          <h1>方法设计</h1>
          <p>在已确认的研究框架与理论方案基础上，选择质性、定量、混合，或暂缓决定。</p>
        </header>
        <div className="research-method__create-card">
          <label>
            先选一个路径
            <select value={kind} disabled={busy} onChange={(event) => setKind(event.target.value as MethodKind)}>
              {(Object.keys(METHOD_LABELS) as MethodKind[]).map((value) => <option key={value} value={value}>{METHOD_LABELS[value]}</option>)}
            </select>
          </label>
          <p>{METHOD_DESCRIPTIONS[kind]}</p>
          <button className="qx-button qx-button--primary" type="button" disabled={busy} onClick={() => void create()}>
            建立方法计划草案
          </button>
        </div>
        {error ? <p className="research-method__error qx-notice-surface" role="alert">{error}</p> : null}
      </section>
    )
  }

  const isLocked = plan.status === 'confirmed' || plan.status === 'stale' || busy
  return (
    <section className="research-method" aria-label="研究方法计划">
      <header className="research-method__header">
        <div className="research-method__intro">
          <p className="research-method__eyebrow">研究设计</p>
          <h1>方法设计</h1>
          <p>{plan.research_question}</p>
        </div>
        <div className={`research-method__status research-method__status--${plan.status}`}>
          <span>版本 v{plan.version}</span>
          <strong>{STATUS_LABELS[plan.status]}</strong>
          <small>{plan.decision_source === 'user_decision' ? '用户决定' : '系统建议'}</small>
        </div>
      </header>

      {plan.status === 'stale' ? (
        <section className="research-method__stale-banner qx-notice-surface" role="status">
          <div><strong>这份计划所依据的框架或理论已经变化。</strong><p>{plan.stale_reason || '旧版本仍可在历史中查看，但不能继续确认或编辑。'}</p></div>
          <button className="qx-button qx-button--primary" type="button" disabled={busy} onClick={() => void create()}>根据当前依据重新建立计划</button>
        </section>
      ) : null}

      <div className="research-method__layout">
        <main className="research-method__main">
          <section className="research-method__card" aria-labelledby="research-method-choice">
            <div className="research-method__card-heading">
              <div><p className="research-method__eyebrow">01 · 路径决定</p><h2 id="research-method-choice">研究路径</h2></div>
              <span className="research-method__source-chip">{plan.decision_source === 'user_decision' ? '用户决定' : '系统建议'}</span>
            </div>
            <label>
              选择研究路径
              <select value={kind} disabled={isLocked} onChange={(event) => setKind(event.target.value as MethodKind)}>
                {(Object.keys(METHOD_LABELS) as MethodKind[]).map((value) => <option key={value} value={value}>{METHOD_LABELS[value]}</option>)}
              </select>
            </label>
            <p className="research-method__hint">{METHOD_DESCRIPTIONS[kind]}</p>
            <label>
              方法理由
              <textarea value={rationale} disabled={isLocked} onChange={(event) => setRationale(event.target.value)} />
            </label>
          </section>

          <section className="research-method__card" aria-labelledby="research-method-sections">
            <div className="research-method__card-heading">
              <div><p className="research-method__eyebrow">02 · 研究设计</p><h2 id="research-method-sections">计划章节</h2></div>
              <span className="research-method__progress">{userDecisionCount}/{sections.length} 已由用户决定</span>
            </div>
            <p className="research-method__hint">系统建议只作为草案提示；每个章节都需要用户编辑并留下“用户决定”标记，才能进入确认。</p>
            <fieldset disabled={isLocked} className="research-method__sections">
              <legend className="sr-only">方法计划章节</legend>
              {sections.map((section, index) => (
                <label className="research-method__section" key={section.key}>
                  <span className="research-method__section-title">
                    <span>{section.title}</span>
                    <small className={section.source === 'user' ? 'is-user' : 'is-system'}>
                      {section.source === 'user' ? '用户决定' : '系统建议'}
                    </small>
                  </span>
                  <textarea
                    aria-label={section.title}
                    value={section.content}
                    onChange={(event) => setSections((items) => items.map((item, itemIndex) => itemIndex === index
                      ? { ...item, content: event.target.value, source: 'user' }
                      : item))}
                  />
                </label>
              ))}
            </fieldset>
            <div className="research-method__actions">
              <button className="qx-button qx-button--primary" type="button" disabled={isLocked} onClick={() => void save()}>保存新版本</button>
              <button className="qx-button" type="button" disabled={!canConfirm || busy} onClick={() => void act(() => confirmMethodPlan(plan.plan_id, { expected_version: plan.version, reason: '用户确认方法计划' }))}>确认计划</button>
            </div>
          </section>

          <section className="research-method__card" aria-labelledby="research-method-context">
            <div className="research-method__card-heading"><div><p className="research-method__eyebrow">03 · 共同依据</p><h2 id="research-method-context">理论、证据与约束</h2></div></div>
            <dl className="research-method__context">
              <div><dt>理论摘要</dt><dd>{plan.theory_summary}</dd></div>
              <div><dt>理论概念</dt><dd>{plan.theory_concepts.join('；') || '当前框架未列出'}</dd></div>
              <div><dt>证据引用</dt><dd>{plan.evidence_ref_ids.join('、') || '当前框架未列出'}</dd></div>
              <div><dt>材料约束</dt><dd>{plan.material_constraints.join('；') || '未记录'}</dd></div>
              <div><dt>伦理约束</dt><dd>{plan.ethical_constraints.join('；') || '未记录'}</dd></div>
              <div><dt>知识发布版本</dt><dd>{plan.knowledge_release_id || '未记录'}</dd></div>
            </dl>
            {plan.shared_context?.length ? (
              <div className="research-method__shared-context" aria-label="已固定的上游依据">
                <h3>已固定的上游依据</h3>
                {plan.shared_context.map((item) => (
                  <article key={item.key}>
                    <strong>{item.title}</strong>
                    <p>{item.content}</p>
                    {item.evidence_refs.length ? (
                      <small>证据定位：{item.evidence_refs.map((ref) => ref.evidence_ref_id).join('、')}</small>
                    ) : null}
                  </article>
                ))}
              </div>
            ) : null}
          </section>
        </main>

        <aside className="research-method__aside">
          <section className="research-method__card research-method__readiness" aria-labelledby="research-method-readiness">
            <p className="research-method__eyebrow">CHECK · 确认门槛</p>
            <h2 id="research-method-readiness">确认前检查</h2>
            <ul>
              <li className={missingDecisionCount === 0 ? 'is-ready' : ''}>{missingDecisionCount === 0 ? '所有章节已由用户决定' : `还有 ${missingDecisionCount} 个章节保留为系统建议`}</li>
              <li className={pendingReviewCount === 0 ? 'is-ready' : ''}>{pendingReviewCount === 0 ? '没有未处理的阻断审校' : `有 ${pendingReviewCount} 条阻断审校待处理`}</li>
              <li className={plan.status === 'stale' ? 'is-warning' : 'is-ready'}>{plan.status === 'stale' ? (plan.stale_reason || '依据版本已变化，请重新建立计划') : '理论与材料依据已固定'}</li>
            </ul>
          </section>

          <section className="research-method__card" aria-labelledby="research-method-reviews">
            <div className="research-method__card-heading"><div><p className="research-method__eyebrow">REVIEW · 审校</p><h2 id="research-method-reviews">审校记录</h2></div></div>
            <label>
              审校意见
              <textarea value={reviewNote} disabled={isLocked} onChange={(event) => setReviewNote(event.target.value)} />
            </label>
            <label className="research-method__review-blocking">
              <input type="checkbox" checked={reviewBlocking} disabled={isLocked} onChange={(event) => setReviewBlocking(event.target.checked)} />
              阻断确认
            </label>
            <button
              className="qx-button"
              type="button"
              disabled={isLocked || reviewNote.trim().length === 0}
              onClick={() => void act(async () => {
                const updated = await reviewMethodPlan(plan.plan_id, {
                  expected_version: plan.version,
                  note: reviewNote.trim(),
                  blocking: reviewBlocking,
                })
                setReviewNote('')
                setReviewBlocking(false)
                return updated
              })}
            >提交审校</button>
            {plan.reviews.length === 0 ? <p className="research-method__muted">尚无审校意见。</p> : plan.reviews.map((review) => (
              <article className="research-method__review" key={review.review_id}>
                <strong>{review.blocking ? '阻断审校' : '建议'}</strong>
                <p>{review.note}</p>
                {review.resolved_at
                  ? <small>已处理</small>
                  : <button className="qx-button" type="button" disabled={busy || plan.status === 'stale'} onClick={() => void act(() => resolveMethodPlanReview(plan.plan_id, review.review_id, { expected_version: plan.version, reason: '已处理审校意见' }))}>标记已处理</button>}
              </article>
            ))}
          </section>

          <section className="research-method__card" aria-labelledby="research-method-history">
            <div className="research-method__card-heading"><div><p className="research-method__eyebrow">HISTORY · 版本</p><h2 id="research-method-history">历史版本</h2></div></div>
            <ol className="research-method__history">
              {versions.map((item) => (
                <li key={`${item.plan_id}-${item.version}`}>
                  <div><strong>v{item.version}</strong><span>{item.change_summary}</span><small>{item.actor === 'user' ? '用户决定' : '系统记录'}</small></div>
                  {item.version !== plan.version ? <button className="qx-button" type="button" disabled={busy || plan.status === 'stale'} onClick={() => void act(() => restoreMethodPlan(plan.plan_id, { source_version: item.version, expected_version: plan.version, reason: `恢复版本 ${item.version}` }))}>恢复</button> : null}
                </li>
              ))}
            </ol>
          </section>
        </aside>
      </div>
      {error ? <p className="research-method__error qx-notice-surface" role="alert">{error}</p> : null}
    </section>
  )
}
