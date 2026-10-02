import { useState } from 'react'
import type { FrontierCorpusDistribution, FrontierDataset, FrontierEvidenceStatement } from './dataset'
import './frontier-corpus-overview.css'

export function hasCompleteCorpusOverview(data: FrontierDataset): boolean {
  const corpus = data.corpusOverview
  const overview = corpus?.overview
  if (!overview || corpus?.status !== 'ready' || overview.scope.stream !== 'research') return false
  if (data.partialRecords) {
    const covered = new Set(overview.scope.coverageRecordIds);
    return overview.scope.analyzedRecordCount > 0 && covered.size === overview.scope.analyzedRecordCount && corpus.statistics.researchCount === covered.size;
  }
  const ids = new Set(data.records.filter((record) => record.verification_status !== 'practice_signal' && record.verification_status !== 'review_queue').map((record) => record.id))
  const covered = new Set(overview.scope.coverageRecordIds)
  return ids.size > 0 && overview.scope.analyzedRecordCount === ids.size && corpus.statistics.researchCount === ids.size && covered.size === ids.size && [...ids].every((id) => covered.has(id))
}

function EvidenceStatement({ statement, numbers, data, onOpenRecord }: {
  statement: FrontierEvidenceStatement; numbers: Map<string, number>; data: FrontierDataset; onOpenRecord: (id: string) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const records = statement.evidenceRecordIds.flatMap((id) => {
    if (!numbers.has(id)) return []
    const record = data.records.find((item) => item.id === id)
    return record ? [record] : data.partialRecords ? [{ id, title: `查看文献 ${numbers.get(id) ?? id}`, source_name: '', published_at_display: '' }] : []
  })
  return <div className="frontier-corpus-statement"><p>{statement.text}<span className="frontier-inline-citations">{records.slice(0, 3).map((record) => <button key={record.id} type="button" aria-label={`阅读文献 ${numbers.get(record.id)}`} title={record.title} onClick={() => onOpenRecord(record.id)}>{numbers.get(record.id)}</button>)}{records.length > 3 ? <button type="button" aria-expanded={expanded} aria-label={`查看这条结论的全部 ${records.length} 篇依据`} onClick={() => setExpanded(!expanded)}>查看{records.length}篇依据</button> : null}</span></p>
    {expanded ? <ol className="frontier-corpus-evidence">{records.map((record) => <li key={record.id}><button type="button" onClick={() => onOpenRecord(record.id)}>{record.title}</button><small>{record.source_name} · {record.published_at_display}</small></li>)}</ol> : null}
  </div>
}

function Distribution({ title, items, data, onOpenRecord, onRequestRecords }: { title: string; items: FrontierCorpusDistribution[]; data: FrontierDataset; onOpenRecord: (id: string) => void; onRequestRecords?: (ids: string[]) => void }) {
  const rows = items.filter((item) => item.count > 0)
  if (!rows.length) return null
  const max = Math.max(...rows.map((row) => row.count))
  return <section className="frontier-corpus-distribution"><h3>{title}</h3>{rows.slice(0, 8).map((row) => <details key={row.key} onToggle={event => { if (event.currentTarget.open) onRequestRecords?.(row.recordIds); }}><summary><span>{row.label}</span><i style={{ width: `${row.count / max * 100}%` }} /><b>{row.count}</b></summary>
    <ol className="frontier-corpus-evidence">{row.recordIds.flatMap((id) => { const record = data.records.find((item) => item.id === id); return record ? [record] : data.partialRecords ? [{ id, title: `查看文献 ${id}` }] : [] }).map((record) => <li key={record.id}><button type="button" onClick={() => onOpenRecord(record.id)}>{record.title}</button></li>)}</ol>
  </details>)}</section>
}

export function FrontierCorpusOverview({ data, onOpenRecord, onRequestRecords }: { data: FrontierDataset; onOpenRecord: (id: string) => void; onRequestRecords?: (ids: string[]) => void }) {
  if (!hasCompleteCorpusOverview(data)) return null
  const corpus = data.corpusOverview!
  const overview = corpus.overview!
  const covered = new Set(overview.scope.coverageRecordIds)
  const citedIds = [...new Set(overview.sections.flatMap((section) => section.statements.flatMap((statement) => statement.evidenceRecordIds)))].filter((id) => covered.has(id))
  const numbers = new Map(citedIds.map((id, index) => [id, index + 1]))
  const stats = corpus.statistics
  const years = stats.yearDistribution.map((item) => item.label).filter((label) => /^\d{4}$/.test(label)).sort()
  const sectionLabels: Record<string, string> = { shared_focus: '共同关切', change: '问题演变', methods: '研究方法', differences: '关键差异', research_opportunities: '研究机会' }
  return <section className="frontier-corpus" aria-labelledby="frontier-corpus-title">
    <h2 id="frontier-corpus-title" className="knowledge-ui__visually-hidden">研究总览</h2>
    <header className="frontier-corpus-heading"><div><h3>{overview.headline}</h3><p>{overview.scope.analyzedRecordCount} 篇研究 · {overview.scope.sourceCount} 种来源{years.length ? ` · ${years[0]}—${years.at(-1)}` : ''}</p></div></header>
    <p className="frontier-corpus-summary">{overview.summary}</p>
    <nav className="frontier-corpus-nav qx-selection-control" aria-label="总览章节">{overview.sections.filter((section) => section.statements.length).map((section) => <button key={section.id} type="button" onClick={() => {
      const target = document.getElementById(`corpus-${section.id}`);
      const scroller = target?.closest<HTMLElement>('.frontier-scroll');
      if (target && scroller) scroller.scrollTo({ top: scroller.scrollTop + target.getBoundingClientRect().top - scroller.getBoundingClientRect().top - 16 });
    }}>{sectionLabels[section.id] || section.title}</button>)}</nav>
    <div className="frontier-corpus-layout">
      <article className="frontier-corpus-report">
        {overview.sections.filter((section) => section.statements.length).map((section) => <section className="frontier-corpus-section" key={section.id} aria-labelledby={`corpus-${section.id}`}><h4 id={`corpus-${section.id}`}>{section.title}</h4>{section.statements.map((statement, index) => <EvidenceStatement key={index} statement={statement} numbers={numbers} data={data} onOpenRecord={onOpenRecord} />)}</section>)}
      </article>
      <aside className="frontier-corpus-statistics" aria-label="研究构成">
        <Distribution title="主要议题" items={stats.topicDistribution.filter((item) => !["uncategorized", "unclassified"].includes(item.key))} data={data} onOpenRecord={onOpenRecord} onRequestRecords={onRequestRecords} />
        <Distribution title="发表年份" items={stats.yearDistribution.toSorted((a, b) => a.label.localeCompare(b.label, undefined, { numeric: true }))} data={data} onOpenRecord={onOpenRecord} onRequestRecords={onRequestRecords} />
        <Distribution title="文献来源" items={stats.sourceDistribution} data={data} onOpenRecord={onOpenRecord} onRequestRecords={onRequestRecords} />
        {stats.practiceCount > 0 ? <p className="frontier-corpus-practice">另收录 {stats.practiceCount} 篇实践观察</p> : null}
      </aside>
    </div>
  </section>
}
