import { FrontierSourceFigure } from './FrontierSourceFigure'
import { ArrowRightIcon } from '@phosphor-icons/react'
import type { FrontierEvidenceStatement, FrontierTopic, FrontierIssue, FrontierResearchBrief as ResearchBrief } from './dataset'
import type { FrontierRecord } from './model'

interface BriefProps {
  topic: FrontierTopic
  records: readonly FrontierRecord[]
  featured?: boolean
  expanded?: boolean
  onOpenTopic: (topicId: string) => void
  onOpenRecord: (recordId: string) => void
}

function EvidenceLinks({ ids, records, onOpenRecord }: {
  ids: readonly string[]
  records: readonly FrontierRecord[]
  onOpenRecord: (recordId: string) => void
}) {
  const evidence = ids.flatMap((id) => {
    const record = records.find((item) => item.id === id)
    return record ? [record] : []
  })
  if (!evidence.length) return null
  return <ul className="frontier-brief-sources">{evidence.map((record) => (
    <li key={record.id}><span>{record.source_name}</span><button type="button" onClick={() => onOpenRecord(record.id)}>{record.title}</button></li>
  ))}</ul>
}

function EvidenceMatrix({ brief, records, onOpenRecord }: {
  brief: ResearchBrief
  records: readonly FrontierRecord[]
  onOpenRecord: (recordId: string) => void
}) {
  const columns = [
    { label: '进展', statements: brief.development ? [brief.development] : [] },
    { label: '共识', statements: brief.consensus },
    { label: '差异', statements: brief.differences },
    { label: '方法', statements: brief.methods },
    { label: '启发', statements: brief.researchImplication ? [brief.researchImplication] : [] },
  ].filter((column) => column.statements.length)
  const papers = brief.evidenceRecordIds.flatMap((id) => {
    const record = records.find((item) => item.id === id)
    return record ? [record] : []
  }).slice(0, 5)
  if (!columns.length || !papers.length) return null
  return <figure className="frontier-evidence-map">
    <figcaption>论点与文献</figcaption>
    <table><thead><tr><th scope="col">关联研究</th>{columns.map((column) => <th key={column.label} scope="col">{column.label}</th>)}</tr></thead>
      <tbody>{papers.map((record) => <tr key={record.id}><th scope="row"><button type="button" onClick={() => onOpenRecord(record.id)}>{record.title}</button><small>{record.source_name}</small></th>{columns.map((column) => {
        const cited = column.statements.some((statement) => statement.evidenceRecordIds.includes(record.id))
        return <td key={column.label} aria-label={cited ? '引用本篇' : '未引用'}>{cited ? <span className="frontier-evidence-dot" aria-hidden="true" /> : null}</td>
      })}</tr>)}</tbody>
    </table>
    <p>圆点表示该项解读引用了这篇文献</p>
  </figure>
}

export function FrontierResearchBrief({ topic, records, featured = false, expanded = false, onOpenTopic, onOpenRecord }: BriefProps) {
  const brief = topic.researchBrief
  const editorial = topic.editorialBrief
  if (!brief && !editorial) return null
  const headline = brief?.headline || editorial!.title
  const development = brief?.development?.text || editorial?.summary
  const implication = brief?.researchImplication?.text || editorial?.whyItMatters
  const ids = brief?.evidenceRecordIds || editorial?.evidenceRecordIds || []
  const availableIds = ids.filter((id) => records.some((record) => record.id === id))
  const sourceImage = featured ? availableIds.flatMap((id) => records.find((record) => record.id === id)?.media ?? [])[0] : undefined
  const Heading = featured || expanded ? 'h2' : 'h3'
  function statements(title: string, items: FrontierEvidenceStatement[] | undefined) {
    if (!items?.length) return null
    return <section className="frontier-brief-section"><h3>{title}</h3>{items.map((item, index) => (
      <div key={`${title}-${index}`}><p>{item.text}</p><EvidenceLinks ids={item.evidenceRecordIds} records={records} onOpenRecord={onOpenRecord} /></div>
    ))}</section>
  }
  return (
    <article className="frontier-brief" data-featured={featured} data-expanded={expanded} data-evidence-map={featured && Boolean(brief)} data-source-image={Boolean(sourceImage)}>
      <div className="frontier-section-meta"><span>{topic.title}</span><span>{topic.stream === 'practice' ? '实践观察' : '研究进展'}</span><span>{availableIds.length} 篇关联文献</span></div>
      <Heading>{expanded ? headline : <button type="button" onClick={() => onOpenTopic(topic.id)}>{headline}</button>}</Heading>
      {development ? <p className="frontier-brief-development">{development}</p> : null}
      {implication ? <div className="frontier-brief-implication"><h3>研究价值</h3><p>{implication}</p></div> : null}
      {sourceImage ? <FrontierSourceFigure media={sourceImage} /> : null}
      {featured && brief ? <EvidenceMatrix brief={brief} records={records} onOpenRecord={onOpenRecord} /> : null}
      {expanded ? <>
        {statements('共同发现', brief?.consensus)}
        {statements('差异与讨论', brief?.differences)}
        {statements('方法与材料', brief?.methods)}
        {brief?.priorityReads.length ? <section className="frontier-brief-section"><h3>接下来读什么</h3><ol className="frontier-priority-reads">{brief.priorityReads.map((read) => {
          const record = records.find((item) => item.id === read.recordId)
          return record ? <li key={read.recordId}><button type="button" onClick={() => onOpenRecord(read.recordId)}>{record.title}</button><p>{read.reason}</p><small>{record.source_name}</small></li> : null
        })}</ol></section> : null}
        <details className="frontier-brief-evidence"><summary>全部关联文献 · {availableIds.length} 篇</summary><EvidenceLinks ids={availableIds} records={records} onOpenRecord={onOpenRecord} /></details>
      </> : <>
        {featured && brief ? null : <EvidenceLinks ids={availableIds.slice(0, featured ? 3 : 2)} records={records} onOpenRecord={onOpenRecord} />}
        <button className="frontier-topic-link" type="button" onClick={() => onOpenTopic(topic.id)}>读懂这一议题 <ArrowRightIcon size={13} aria-hidden="true" /></button>
      </>}
    </article>
  )
}

export function FrontierTopicTimeline({ topic, sources = [], compact = false }: { topic: FrontierTopic; sources?: readonly { id: string; name: string }[]; compact?: boolean }) {
  const groups = new Map<string, FrontierIssue[]>()
  for (const issue of topic.issueSeries ?? []) {
    if (!issue.coverageComplete || issue.share === null || issue.denominator <= 0) continue
    groups.set(issue.comparisonGroup, [...(groups.get(issue.comparisonGroup) ?? []), issue])
  }
  const comparable = [...groups.values()].filter((issues) => issues.length >= 2).toSorted((a, b) => b.length - a.length)[0]?.toSorted((a, b) => a.publicationMonth.localeCompare(b.publicationMonth)).slice(-8)
  if (comparable) {
    const width = comparable.length * 24
    return <figure className="frontier-timeline frontier-issue-timeline">
      <svg viewBox={`0 0 ${width} 44`} role="img" aria-label={`${topic.title}同刊完整期次的议题占比`}>
        <title>{comparable.map((issue) => `${issue.label}：${issue.topicRecordCount}/${issue.denominator}篇，${Math.round(issue.share! * 100)}%`).join('；')}</title>
        {comparable.map((issue, index) => <rect key={issue.issueId} x={index * 24 + 4} y={42 - issue.share! * 38} width={16} height={issue.share! * 38} rx={1} />)}
        <line x1={0} y1={43} x2={width} y2={43} />
      </svg>
      <figcaption>{compact ? <><span>{comparable[0].publicationMonth}—{comparable.at(-1)!.publicationMonth}</span><span>同刊期次占比</span></> : <><span>{comparable[0].label}</span><span>{comparable.at(-1)!.label}</span></>}</figcaption>
      <small>{sources.find((source) => source.id === comparable[0].sourceId)?.name} · 同刊期次占比 · {Math.round(comparable[0].share! * 100)}% → {Math.round(comparable.at(-1)!.share! * 100)}%</small>
    </figure>
  }
  const months = topic.monthlySeries?.slice(-12) ?? []
  if (!months.length || !months.some((month) => month.recordCount)) return null
  const max = Math.max(...months.map((month) => month.recordCount), 1)
  const width = months.length * 18
  return <figure className="frontier-timeline">
    <svg viewBox={`0 0 ${width} 44`} role="img" aria-label={`${topic.title}已收录论文月度分布`}>
      <title>{months.map((month) => `${month.month}${month.isPartialMonth ? "（本月未完）" : ""}：已收录${month.recordCount}篇`).join('；')}</title>
      {months.map((month, index) => <rect key={month.month} x={index * 18 + 2} y={42 - month.recordCount / max * 38} width={12} height={month.recordCount / max * 38} rx={1} />)}
      <line x1={0} y1={43} x2={width} y2={43} />
    </svg>
    <figcaption>{compact ? <><span>{months[0].month}—{months.at(-1)!.month}</span><span>按发表月收录</span></> : <><span>{months[0].month}</span><span>{months.at(-1)!.month}{months.at(-1)!.isPartialMonth ? " · 月内" : ""}</span></>}</figcaption>
  </figure>
}
