import type { ResearchCycleSnapshot } from './researchCycleModel'

const destinationLabels: Record<string, string> = {
  material_screening: '材料筛选',
  sampling: '下一轮取样',
}

const priorityLabels: Record<string, string> = {
  high: '高优先级',
  medium: '中优先级',
  low: '低优先级',
}

const sourceLabels: Record<string, string> = {
  analysis: '分析',
  theory: '理论判断',
}

export function ResearchCyclePanel({ snapshot }: { snapshot: ResearchCycleSnapshot }) {
  const visibleHints = snapshot.reporting_hints.filter((item) => item.status !== 'present')

  return (
    <section className="research-cycle" role="region" aria-label="证据缺口与下一轮材料">
      <header>
        <div>
          <strong>证据缺口与下一轮材料</strong>
          <span>从已确认分析和理论判断回到材料选择</span>
        </div>
        <code title={snapshot.content_hash}>循环 v{snapshot.version}</code>
      </header>

      {snapshot.gaps.length ? (
        <div className="research-cycle__gaps">
          {snapshot.gaps.map((gap) => (
            <article key={gap.gap_id}>
              <div className="research-cycle__tags">
                <span>{destinationLabels[gap.destination] ?? gap.destination}</span>
                <span>{priorityLabels[gap.priority] ?? gap.priority}</span>
              </div>
              <strong>{gap.description}</strong>
              <p>{gap.suggested_action}</p>
              <small>
                依据：{sourceLabels[gap.source_kind] ?? gap.source_kind} {gap.source_id}
                {gap.theory_plan_version ? ` · 理论计划 v${gap.theory_plan_version}` : ''}
                {` · 循环 v${snapshot.version}`}
              </small>
            </article>
          ))}
        </div>
      ) : <p className="research-cycle__empty">当前已确认分析没有形成新的材料缺口。</p>}

      {visibleHints.length ? (
        <details className="research-cycle__reporting">
          <summary>报告覆盖提示（{visibleHints.length}）</summary>
          <p>只提示报告覆盖，不影响理论或方法判断。</p>
          <ul>
            {visibleHints.map((hint) => (
              <li key={`${hint.guideline}:${hint.item_key}`}>
                <strong>{hint.guideline} · {hint.label}</strong>
                <span>{hint.message}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  )
}
