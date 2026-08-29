import type { M5ResearchAnalysisBasis as M5ResearchAnalysisBasisData } from '../../api/m5ResearchDelivery'

export function M5ResearchAnalysisBasis({
  basis,
}: {
  basis: M5ResearchAnalysisBasisData | null
}) {
  const version = basis?.contentHash.replace(/^sha256:/, '').slice(0, 12)

  return (
    <section className="m5-analysis-basis" role="region" aria-label="本版材料分析依据">
      <header>
        <strong>材料分析依据</strong>
        {basis ? (
          <span>{basis.codes.length} 个编码 · {basis.memos.length} 则备忘 · {basis.comparisons.length} 项案例比较</span>
        ) : null}
      </header>

      {!basis ? <p>本版尚未纳入已确认的个人材料分析。</p> : (
        <>
          <div className="m5-analysis-basis__items">
            {basis.codes.map((code) => (
              <div key={code.id}>
                <span>编码</span>
                <strong>{code.label}</strong>
                <p>{code.definition}</p>
              </div>
            ))}
            {basis.memos.map((memo) => (
              <div key={memo.id}>
                <span>{memo.kindLabel}</span>
                <strong>{memo.title}</strong>
              </div>
            ))}
            {basis.comparisons.map((comparison) => (
              <div key={comparison.id}>
                <span>案例比较</span>
                <strong>{comparison.title}</strong>
                <p>{comparison.theoryImplication}</p>
              </div>
            ))}
          </div>
          <footer>
            {basis.unavailableAnnotationCount > 0 ? (
              <span>{basis.unavailableAnnotationCount} 处原文已删除，仅保留来源记录</span>
            ) : <span>原文位置均可追溯</span>}
            {version ? <span>依据版本 {version}</span> : null}
          </footer>
        </>
      )}
    </section>
  )
}
