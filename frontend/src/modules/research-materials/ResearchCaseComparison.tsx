import { useMemo, useState } from 'react'

import type {
  AnalysisAnnotation,
  AnalysisRecordStatus,
  CaseComparison,
  ComparisonFinding,
  CreateCaseComparisonInput,
} from './researchAnalysisModel'

export type CaseComparisonDecision = Exclude<AnalysisRecordStatus, 'candidate'>

type ComparisonUnit = {
  id: string
  label: string
  timeLabel: string | null
}

type ResearchCaseComparisonProps = {
  readonly annotations: AnalysisAnnotation[]
  readonly comparisons: CaseComparison[]
  readonly materialNames?: Readonly<Record<string, string>>
  readonly onCreate?: (body: CreateCaseComparisonInput) => void | Promise<void>
  readonly onDecide?: (
    comparisonId: string,
    decision: CaseComparisonDecision,
    reason: string,
    expectedVersion: number,
  ) => void | Promise<void>
}

const findingLabels: Record<ComparisonFinding['kind'], string> = {
  support: '支持证据',
  counterexample: '反例',
  contradict: '矛盾材料',
  competing_explanation: '竞争解释',
  evidence_gap: '证据缺口',
}

const nextStepLabels: Record<string, string> = {
  interview: '访谈',
  observation: '观察',
  material_collection: '补充材料',
  research_question: '修订研究问题',
}

function distinct(values: string[]): string[] {
  return [...new Set(values.map((value) => value.trim()).filter(Boolean))]
}

function comparisonUnits(
  annotations: AnalysisAnnotation[],
  materialNames: Readonly<Record<string, string>>,
): ComparisonUnit[] {
  const units = new Map<string, ComparisonUnit>()
  for (const annotation of annotations) {
    if (annotation.case_label) {
      const label = `案例：${annotation.case_label}`
      units.set(`case:${annotation.case_label}`, { id: `case:${annotation.case_label}`, label, timeLabel: null })
    }
  }
  for (const annotation of annotations) {
    if (annotation.observed_at) {
      const label = `时间：${annotation.observed_at}`
      units.set(`time:${annotation.observed_at}`, { id: `time:${annotation.observed_at}`, label, timeLabel: annotation.observed_at })
    }
  }
  for (const annotation of annotations) {
    const name = materialNames[annotation.material_id] ?? annotation.material_id
    const label = `材料：${name}`
    units.set(`material:${annotation.material_id}`, { id: `material:${annotation.material_id}`, label, timeLabel: null })
  }
  return [...units.values()]
}

function ComparisonDiagnostics({ comparison }: { comparison: CaseComparison }) {
  const grouped = comparison.findings.reduce<Record<string, string[]>>((current, finding) => {
    current[finding.kind] = [...(current[finding.kind] ?? []), finding.statement]
    return current
  }, {})
  const competing = distinct([
    ...(grouped.competing_explanation ?? []),
    ...comparison.competing_explanations,
  ])
  const gaps = distinct([...(grouped.evidence_gap ?? []), ...comparison.evidence_gaps])

  return (
    <div className="research-comparison__diagnostics">
      {(['support', 'counterexample', 'contradict'] as const).map((kind) => (
        grouped[kind]?.length ? (
          <section key={kind}>
            <h5>{findingLabels[kind]}</h5>
            {grouped[kind].map((statement) => <p key={statement}>{statement}</p>)}
          </section>
        ) : null
      ))}
      {competing.length ? <section><h5>竞争解释</h5>{competing.map((item) => <p key={item}>{item}</p>)}</section> : null}
      {gaps.length ? <section><h5>证据缺口</h5>{gaps.map((item) => <p key={item}>{item}</p>)}</section> : null}
      {comparison.next_steps.length ? (
        <section>
          <h5>下一步行动</h5>
          {comparison.next_steps.map((step) => (
            <p key={`${step.kind}:${step.action}`}><span>{nextStepLabels[step.kind] ?? step.kind}</span>{step.action}</p>
          ))}
        </section>
      ) : null}
      <section className="research-comparison__theory"><h5>理论含义</h5><p>{comparison.theory_implication}</p></section>
    </div>
  )
}

function CandidateComparison({
  comparison,
  onDecide,
}: {
  comparison: CaseComparison
  onDecide?: ResearchCaseComparisonProps['onDecide']
}) {
  const [reason, setReason] = useState('')
  const [pending, setPending] = useState<CaseComparisonDecision | null>(null)
  const [error, setError] = useState<string | null>(null)
  const normalizedReason = reason.trim()

  async function decide(decision: CaseComparisonDecision) {
    if (!onDecide || !normalizedReason || pending) return
    setPending(decision)
    setError(null)
    try {
      await onDecide(comparison.comparison_id, decision, normalizedReason, comparison.version)
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : '案例比较判断未保存。')
    } finally {
      setPending(null)
    }
  }

  return (
    <article className="research-comparison research-comparison--candidate" aria-label={`案例比较候选：${comparison.title}`}>
      <header><span>Agent 建议 · 待确认</span><small>{comparison.case_labels.join(' · ')}</small></header>
      <strong>{comparison.title}</strong>
      <p className="research-comparison__question">{comparison.question}</p>
      <ComparisonDiagnostics comparison={comparison} />
      {onDecide ? (
        <>
          <label>
            <span>判断依据</span>
            <textarea aria-label="案例比较判断依据" value={reason} disabled={pending !== null} onChange={(event) => setReason(event.target.value)} rows={2} />
          </label>
          {error ? <p role="alert" className="research-analysis-candidate__error">{error}</p> : null}
          <footer>
            <button type="button" disabled={!normalizedReason || pending !== null} onClick={() => { void decide('rejected') }}>拒绝案例比较</button>
            <button type="button" disabled={!normalizedReason || pending !== null} onClick={() => { void decide('confirmed') }}>确认案例比较</button>
          </footer>
        </>
      ) : null}
    </article>
  )
}

function ConfirmedComparison({ comparison }: { comparison: CaseComparison }) {
  return (
    <article className="research-comparison" aria-label={`已确认案例比较：${comparison.title}`}>
      <header><span>研究者确认 · 案例比较</span><small>{comparison.case_labels.join(' · ')}</small></header>
      <strong>{comparison.title}</strong>
      <p className="research-comparison__question">{comparison.question}</p>
      <ComparisonDiagnostics comparison={comparison} />
    </article>
  )
}

export function ResearchCaseComparison({
  annotations,
  comparisons,
  materialNames = {},
  onCreate,
  onDecide,
}: ResearchCaseComparisonProps) {
  const units = useMemo(() => comparisonUnits(annotations, materialNames), [annotations, materialNames])
  const [composerOpen, setComposerOpen] = useState(false)
  const [selectedUnitIds, setSelectedUnitIds] = useState<string[]>([])
  const [selectedAnnotationIds, setSelectedAnnotationIds] = useState<string[]>([])
  const [title, setTitle] = useState('')
  const [question, setQuestion] = useState('')
  const [support, setSupport] = useState('')
  const [counterexample, setCounterexample] = useState('')
  const [contradiction, setContradiction] = useState('')
  const [competingExplanation, setCompetingExplanation] = useState('')
  const [evidenceGap, setEvidenceGap] = useState('')
  const [theoryImplication, setTheoryImplication] = useState('')
  const [nextStepKind, setNextStepKind] = useState('interview')
  const [nextStepAction, setNextStepAction] = useState('')
  const [nextStepPriority, setNextStepPriority] = useState('medium')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const candidates = comparisons.filter((item) => item.source === 'agent' && item.status === 'candidate')
  const confirmed = comparisons.filter((item) => item.status === 'confirmed')
  const hasFinding = Boolean(support.trim() || counterexample.trim() || contradiction.trim())
  const canSubmit = Boolean(
    selectedUnitIds.length >= 2
    && selectedAnnotationIds.length
    && title.trim()
    && question.trim()
    && hasFinding
    && theoryImplication.trim(),
  )

  function toggle(values: string[], value: string, update: (next: string[]) => void) {
    update(values.includes(value) ? values.filter((item) => item !== value) : [...values, value])
  }

  function resetComposer() {
    setComposerOpen(false)
    setSelectedUnitIds([])
    setSelectedAnnotationIds([])
    setTitle('')
    setQuestion('')
    setSupport('')
    setCounterexample('')
    setContradiction('')
    setCompetingExplanation('')
    setEvidenceGap('')
    setTheoryImplication('')
    setNextStepKind('interview')
    setNextStepAction('')
    setNextStepPriority('medium')
    setError(null)
  }

  async function submit() {
    if (!onCreate || !canSubmit || pending) return
    const selectedUnits = units.filter((unit) => selectedUnitIds.includes(unit.id))
    const annotationIds = selectedAnnotationIds
    const findings: ComparisonFinding[] = [
      ['support', support],
      ['counterexample', counterexample],
      ['contradict', contradiction],
    ].flatMap(([kind, statement]) => statement.trim() ? [{ kind: kind as ComparisonFinding['kind'], statement: statement.trim(), annotation_ids: annotationIds }] : [])
    setPending(true)
    setError(null)
    try {
      await onCreate({
        title: title.trim(),
        question: question.trim(),
        case_labels: selectedUnits.map((unit) => unit.label),
        time_labels: distinct(selectedUnits.flatMap((unit) => unit.timeLabel ? [unit.timeLabel] : [])),
        findings,
        competing_explanations: competingExplanation.trim() ? [competingExplanation.trim()] : [],
        evidence_gaps: evidenceGap.trim() ? [evidenceGap.trim()] : [],
        next_steps: nextStepAction.trim() ? [{ kind: nextStepKind, action: nextStepAction.trim(), priority: nextStepPriority }] : [],
        theory_implication: theoryImplication.trim(),
      })
      resetComposer()
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : '案例比较未保存。')
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="research-comparisons" aria-label="案例比较">
      {candidates.length ? <div className="research-comparisons__list"><h4>待你判断的比较</h4>{candidates.map((comparison) => <CandidateComparison key={comparison.comparison_id} comparison={comparison} onDecide={onDecide} />)}</div> : null}
      {confirmed.length ? <div className="research-comparisons__list"><h4>已确认的比较</h4>{confirmed.map((comparison) => <ConfirmedComparison key={comparison.comparison_id} comparison={comparison} />)}</div> : null}
      {onCreate ? <button className="research-comparisons__create" type="button" onClick={() => setComposerOpen(true)}>建立案例比较</button> : null}
      {composerOpen ? (
        <form className="research-comparison-form" aria-label="建立案例比较" onSubmit={(event) => { event.preventDefault(); void submit() }}>
          <fieldset>
            <legend>比较单元 <small>至少选择两个材料、案例或时间点</small></legend>
            {units.map((unit) => <label key={unit.id}><input type="checkbox" checked={selectedUnitIds.includes(unit.id)} onChange={() => toggle(selectedUnitIds, unit.id, setSelectedUnitIds)} /><span>{unit.label}</span></label>)}
          </fieldset>
          <fieldset>
            <legend>原文证据</legend>
            {annotations.map((annotation) => <label key={annotation.annotation_id}><input type="checkbox" checked={selectedAnnotationIds.includes(annotation.annotation_id)} onChange={() => toggle(selectedAnnotationIds, annotation.annotation_id, setSelectedAnnotationIds)} /><span>{annotation.quote}</span></label>)}
          </fieldset>
          <label><span>比较标题</span><input aria-label="比较标题" value={title} onChange={(event) => setTitle(event.target.value)} /></label>
          <label><span>比较问题</span><textarea aria-label="比较问题" value={question} onChange={(event) => setQuestion(event.target.value)} rows={2} /></label>
          <label><span>支持证据</span><textarea aria-label="支持证据" value={support} onChange={(event) => setSupport(event.target.value)} rows={2} /></label>
          <label><span>反例</span><textarea aria-label="反例" value={counterexample} onChange={(event) => setCounterexample(event.target.value)} rows={2} /></label>
          <label><span>矛盾材料</span><textarea aria-label="矛盾材料" value={contradiction} onChange={(event) => setContradiction(event.target.value)} rows={2} /></label>
          <label><span>竞争解释</span><textarea aria-label="竞争解释" value={competingExplanation} onChange={(event) => setCompetingExplanation(event.target.value)} rows={2} /></label>
          <label><span>证据缺口</span><textarea aria-label="证据缺口" value={evidenceGap} onChange={(event) => setEvidenceGap(event.target.value)} rows={2} /></label>
          <label><span>理论含义</span><textarea aria-label="理论含义" value={theoryImplication} onChange={(event) => setTheoryImplication(event.target.value)} rows={3} /></label>
          <div className="research-comparison-form__next-step">
            <label><span>行动类型</span><select aria-label="行动类型" value={nextStepKind} onChange={(event) => setNextStepKind(event.target.value)}>{Object.entries(nextStepLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label><span>优先级</span><select aria-label="优先级" value={nextStepPriority} onChange={(event) => setNextStepPriority(event.target.value)}><option value="high">高</option><option value="medium">中</option><option value="low">低</option></select></label>
          </div>
          <label><span>下一步行动</span><textarea aria-label="下一步行动" value={nextStepAction} onChange={(event) => setNextStepAction(event.target.value)} rows={2} /></label>
          {error ? <p role="alert">{error}</p> : null}
          <footer><button type="button" onClick={resetComposer}>取消</button><button type="submit" disabled={!canSubmit || pending}>{pending ? '正在保存' : '保存案例比较'}</button></footer>
        </form>
      ) : null}
    </section>
  )
}

export type { ResearchCaseComparisonProps }
