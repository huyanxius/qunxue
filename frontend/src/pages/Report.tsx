import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { CODEBOOK, CODED_SEGMENTS, TRANSCRIPT_TITLE } from '../data/demo'
import { clearDecisions, finalLabel, useDecisions } from '../store/decisions'
import { cohenKappa, kappaLevel } from '../lib/kappa'

export default function Report() {
  const decisions = useDecisions()

  const rows = useMemo(
    () =>
      CODED_SEGMENTS.map((s) => ({
        seg: s,
        decision: decisions[s.id],
        final: finalLabel(s.proposal!.label, decisions[s.id]),
      })),
    [decisions],
  )

  const decided = rows.filter((r) => r.decision)
  const pairs = rows
    .filter((r) => r.final)
    .map((r) => [r.seg.proposal!.label, r.final!] as [string, string])
  const kappa = cohenKappa(pairs)
  const disagreements = rows.filter((r) => r.decision && r.decision.kind !== 'accept')

  const codebookRows = CODEBOOK.map((c) => {
    const hits = rows.filter((r) => r.final === c.label)
    return { ...c, count: hits.length, example: hits[0]?.seg.proposal?.quote ?? '—' }
  })

  if (decided.length === 0) {
    return (
      <main className="page-narrow report-empty">
        <p className="kicker">编码报告</p>
        <h1 className="serif page-title">还没有可报告的裁决。</h1>
        <p>先到工作台对 AI 初编码逐条采纳或驳回,报告会在这里实时生成。</p>
        <Link to="/workbench" className="btn btn-solid">去工作台</Link>
      </main>
    )
  }

  const exportMd = () => {
    const lines = [
      `# 编码报告 · ${TRANSCRIPT_TITLE}`,
      '',
      `- 编码建议:${rows.length} 条;已裁决:${decided.length} 条;分歧:${disagreements.length} 条`,
      `- Cohen's Kappa:${kappa.kappa === null ? '不可计算' : kappa.kappa.toFixed(3)}(Po=${kappa.po.toFixed(3)},Pe=${kappa.pe.toFixed(3)},n=${kappa.n})`,
      '',
      '## 编码簿',
      '',
      '| 标签 | 定义 | 频次 |',
      '| --- | --- | --- |',
      ...codebookRows.map((c) => `| ${c.label} | ${c.definition} | ${c.count} |`),
      '',
      '## 分歧记录',
      '',
      ...disagreements.map((r) => {
        const d = r.decision!
        const verdict = d.kind === 'revise' ? `改判为「${d.newLabel}」` : `驳回(${d.kind === 'reject' ? d.reason : ''})`
        return `- 段 ${r.seg.id}:AI 初编「${r.seg.proposal!.label}」→ ${verdict}`
      }),
      '',
      '> 本报告由"群学致知·第二编码者"演示环境生成,访谈材料为虚构。AI 初编码均已由人工逐条裁决。',
    ]
    const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'coding-report.md'
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <main className="page-wide report">
      <div className="report-head">
        <div>
          <p className="kicker">编码报告</p>
          <h1 className="serif page-title">{TRANSCRIPT_TITLE}</h1>
        </div>
        <div className="report-head-actions">
          <button className="btn" onClick={exportMd}>导出 Markdown</button>
          <button className="btn btn-quiet" onClick={clearDecisions}>重置演示</button>
        </div>
      </div>

      {/* 一致性 */}
      <section className="panel">
        <h2>人机一致性 · Cohen&rsquo;s Kappa</h2>
        <div className="kappa-grid">
          <div className="kappa-main">
            <b className="num">{kappa.kappa === null ? '—' : kappa.kappa.toFixed(2)}</b>
            <span>{kappa.kappa === null ? '类目单一,κ 不可计算' : kappaLevel(kappa.kappa)}</span>
          </div>
          <dl className="kappa-detail">
            <div><dt>有效编码对 n</dt><dd className="num">{kappa.n}</dd></div>
            <div><dt>观察一致率 Po</dt><dd className="num">{kappa.po.toFixed(3)}</dd></div>
            <div><dt>期望一致率 Pe</dt><dd className="num">{kappa.pe.toFixed(3)}</dd></div>
            <div><dt>κ = (Po−Pe)/(1−Pe)</dt><dd>过程完整,可写进论文方法节</dd></div>
          </dl>
        </div>
        <p className="panel-note">
          驳回的条目不计入编码对;κ 低不等于失败——它标出这批材料诠释空间大的位置,见下方分歧记录。
        </p>
      </section>

      {/* 编码簿 */}
      <section className="panel">
        <h2>编码簿(终裁后)</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>标签</th><th>定义</th><th className="th-num">频次</th><th>例句</th></tr>
            </thead>
            <tbody>
              {codebookRows.map((c) => (
                <tr key={c.label} className={c.count === 0 ? 'row-dim' : ''}>
                  <td className="td-label">{c.label}</td>
                  <td>{c.definition}</td>
                  <td className="num th-num">{c.count}</td>
                  <td className="serif td-quote">{c.example === '—' ? '—' : `“${c.example}”`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* 分歧 */}
      <section className="panel">
        <h2>分歧记录 <b className="num panel-count">{disagreements.length}</b></h2>
        {disagreements.length === 0 ? (
          <p className="panel-note">目前没有分歧——全部初编码被采纳。分歧出现时,这里会逐条记录人机各自的判断与理由。</p>
        ) : (
          <ol className="dis-list">
            {disagreements.map((r) => {
              const d = r.decision!
              return (
                <li key={r.seg.id}>
                  <span className="dis-seg num">段 {String(r.seg.id).padStart(2, '0')}</span>
                  <p className="serif dis-quote">“{r.seg.proposal!.quote}”</p>
                  <p className="dis-verdict">
                    <span className="ai-mark">AI 初编</span> {r.seg.proposal!.label}
                    <b className="dis-arrow">→</b>
                    {d.kind === 'revise' ? (
                      <>人工改判 <b>{d.newLabel}</b></>
                    ) : (
                      <>人工驳回<i>(理由:{d.kind === 'reject' ? d.reason : ''})</i></>
                    )}
                  </p>
                </li>
              )
            })}
          </ol>
        )}
      </section>

      <p className="report-footnote">
        演示环境 · 访谈材料为虚构 · AI 生成内容均带「AI 初编」标识,最终编码以人工裁决为准。
      </p>
    </main>
  )
}
