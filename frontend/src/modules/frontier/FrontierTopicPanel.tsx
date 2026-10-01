import "../../styles/selection-controls.css";
import { ArrowLeftIcon, XIcon } from '@phosphor-icons/react'
import type { ReactNode } from 'react'
import type { FrontierDataset, FrontierEvidenceStatement, FrontierTopic } from './dataset'
import type { FrontierRecord, FrontierState } from './model'
import { FrontierSourceFigure } from './FrontierSourceFigure'
import { FrontierTopicTimeline } from './FrontierResearchBrief'

export function TopicHeadline({ topic }: { topic: FrontierTopic }) {
  return <>{topic.researchBrief?.headline || topic.editorialBrief?.title || topic.title}</>
}

export function FrontierTopicRows({ topics, data, selected, onSelect }: {
  topics: readonly FrontierTopic[]; data: FrontierDataset; selected: string; onSelect: (id: string) => void
}) {
  return <div className="frontier-topic-rows" aria-label="研究议题">
    {topics.map((topic) => <button key={topic.id} type="button" className="frontier-topic-row" aria-label={`分析 ${topic.title}${topic.stream === 'practice' ? ' · 实践' : ''}`} aria-current={selected === topic.id ? 'page' : undefined} onClick={() => onSelect(topic.id)}>
      <div className="frontier-topic-row-copy"><span className="frontier-topic-eyebrow">{topic.title} · {topic.stream === 'practice' ? '实践观察' : '学术研究'}</span><h3><TopicHeadline topic={topic} /></h3>
        <p>{topic.researchBrief?.development?.text || topic.editorialBrief?.summary || data.records.find((record) => topic.recordIds.includes(record.id))?.research_question || data.records.find((record) => topic.recordIds.includes(record.id))?.summary}</p>
        <small>{topic.counts.total} 篇文献 · {topic.sourceIds.length} 种来源</small>
      </div>
      <div className="frontier-topic-row-trend"><FrontierTopicTimeline topic={topic} sources={data.sources} compact /></div>
    </button>)}
  </div>
}

export function FrontierRecordResults({ records, state, title, onStateChange, onOpenRecord }: {
  records: readonly FrontierRecord[]; state: FrontierState; title: string; onStateChange: (state: FrontierState) => void; onOpenRecord: (id: string) => void
}) {
  return <section className="frontier-latest" aria-labelledby="frontier-latest-title">
    <header className="knowledge-explorer__results-heading"><h2 id="frontier-latest-title">{title}</h2><span>{records.length} 篇</span></header>
    {records.length ? <ol className="knowledge-explorer__result-list frontier-record-list">{records.slice(0, state.limit).map((record, index) => <li key={record.id}>
      <span className="knowledge-explorer__result-index" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
      <article className="frontier-record"><span className="frontier-section-meta">{record.source_name} · {record.published_at_display}</span><h3><button className="knowledge-explorer__result-main" type="button" onClick={() => onOpenRecord(record.id)}><strong>{record.title}</strong></button></h3><p>{record.summary}</p>
        <footer className="knowledge-explorer__result-meta"><small>{record.verification_status === 'practice_signal' ? '实践观察' : '学术研究'}{record.within_preferred_window === false ? ' · 旧刊补充' : ''}</small><button type="button" aria-label={`查看 ${record.title}`} onClick={() => onOpenRecord(record.id)}>详情与来源</button></footer>
      </article>
    </li>)}</ol> : <div className="frontier-empty"><h2>没有匹配的资料</h2><p>试试其他关键词，或清除筛选查看全部内容。</p><button type="button" onClick={() => onStateChange({ ...state, query: '', source: '', topic: '', kind: 'all', record: '', topicView: 'overview', limit: 6 })}>查看全部</button></div>}
    {records.length > state.limit ? <button className="knowledge-explorer__load-more" type="button" onClick={() => onStateChange({ ...state, limit: Math.min(records.length, state.limit + 24) })}>再看 {Math.min(24, records.length - state.limit)} 条资料</button> : null}
  </section>
}

function TopicChart({ topic, sources }: { topic: FrontierTopic; sources: FrontierDataset['sources'] }) {
  const groups = new Map<string, NonNullable<FrontierTopic['issueSeries']>>()
  for (const issue of topic.issueSeries ?? []) {
    if (!issue.coverageComplete || issue.share === null || issue.denominator <= 0) continue
    groups.set(issue.comparisonGroup, [...(groups.get(issue.comparisonGroup) ?? []), issue])
  }
  const issues = [...groups.values()].filter((items) => items.length >= 2).toSorted((a, b) => b.length - a.length)[0]?.toSorted((a, b) => a.publicationMonth.localeCompare(b.publicationMonth))
  const months = topic.monthlySeries?.slice(-12) ?? []
  const points = issues ? issues.map((issue) => ({ label: issue.label, value: issue.share! * 100 })) : months.map((month) => ({ label: month.month, value: month.recordCount }))
  if (!points.length || (!issues && !points.some((point) => point.value))) return null
  const max = issues ? 100 : Math.max(...points.map((point) => point.value), 1)
  const x = (i: number) => 42 + i * 542 / Math.max(1, points.length - 1)
  const y = (value: number) => 158 - value / max * 130
  const path = points.map((point, index) => `${index ? 'L' : 'M'}${x(index)},${y(point.value)}`).join(' ')
  return <section className="frontier-analysis-chart"><header><h3>{issues ? '同刊期次的议题占比' : '文献收录变化'}</h3><span>{issues ? sources.find((source) => source.id === issues[0].sourceId)?.name : '按发表月统计'}</span></header>
    <svg viewBox="0 0 610 192" role="img" aria-label={`${topic.title}${issues ? '同刊期次占比' : '文献收录变化'}`}>
      <title>{points.map((point) => `${point.label}：${issues ? point.value.toFixed(1) + '%' : point.value + '篇'}`).join('；')}</title>
      {[0, .5, 1].map((scale) => <g key={scale}><line x1="42" y1={y(max * scale)} x2="584" y2={y(max * scale)} /><text x="32" y={y(max * scale) + 4} textAnchor="end">{Math.round(max * scale)}{issues ? '%' : ''}</text></g>)}
      <path d={path} fill="none" />{points.map((point, i) => <circle key={`${point.label}-${i}`} cx={x(i)} cy={y(point.value)} r="3"><title>{point.label} · {issues ? `${point.value.toFixed(1)}%` : `${point.value}篇`}</title></circle>)}
      {[0, Math.floor((points.length - 1) / 2), points.length - 1].filter((n, i, all) => all.indexOf(n) === i).map((i) => <text key={i} x={x(i)} y="182" textAnchor={i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle'}>{points[i].label}</text>)}
    </svg>
  </section>
}

export function FrontierTopicPanel({ topic, data, records, state, onStateChange, onOpenRecord, onClose }: {
  topic: FrontierTopic; data: FrontierDataset; records: readonly FrontierRecord[]; state: FrontierState; onStateChange: (state: FrontierState) => void; onOpenRecord: (id: string) => void; onClose: () => void
}) {
  const hasSynthesis = Boolean(topic.researchBrief || topic.editorialBrief)
  const view = state.topicView === 'analysis' && !hasSynthesis ? 'sources' : state.topicView ?? 'overview'
  const brief = topic.researchBrief
  const editorial = topic.editorialBrief
  const ids = [...new Set([...(brief?.evidenceRecordIds ?? editorial?.evidenceRecordIds ?? []), ...topic.recordIds])].filter((id) => data.records.some((record) => record.id === id))
  const number = new Map(ids.map((id, index) => [id, index + 1]))
  const development = brief?.development ?? (editorial ? { text: editorial.summary, evidenceRecordIds: editorial.evidenceRecordIds } : null)
  const implication = brief?.researchImplication ?? (editorial ? { text: editorial.whyItMatters, evidenceRecordIds: editorial.evidenceRecordIds } : null)
  const sourceCounts = [...new Set(records.map((record) => record.source_name))].map((name) => ({ name, count: records.filter((record) => record.source_name === name).length })).toSorted((a, b) => b.count - a.count)
  const media = (brief?.evidenceRecordIds ?? editorial?.evidenceRecordIds ?? []).flatMap((id) => data.records.find((record) => record.id === id)?.media ?? []).slice(0, 2)
  const tabs = ([{ id: 'overview', label: '概览' }, { id: 'analysis', label: '综合解读' }, { id: 'sources', label: '文献' }] as const).filter((tab) => tab.id !== 'analysis' || hasSynthesis)
  function statement(item: FrontierEvidenceStatement) {
    return <p>{item.text}<span className="frontier-inline-citations">{item.evidenceRecordIds.filter((id) => number.has(id)).map((id) => <button key={id} type="button" aria-label={`阅读文献 ${number.get(id)}`} title={data.records.find((record) => record.id === id)?.title} onClick={() => onOpenRecord(id)}>{number.get(id)}</button>)}</span></p>
  }
  function section(title: string, items: FrontierEvidenceStatement[] | undefined): ReactNode {
    return items?.length ? <section className="frontier-analysis-section"><h3>{title}</h3>{items.map((item, i) => <div key={i}>{statement(item)}</div>)}</section> : null
  }
  return <section className="frontier-analysis-panel" aria-label={`${topic.title}分析`}>
    <header className="frontier-panel-top"><button type="button" className="frontier-panel-back" onClick={onClose}><ArrowLeftIcon size={15} />全部议题</button><span>{topic.stream === 'practice' ? '实践观察' : '学术研究'}</span><button type="button" aria-label="关闭议题分析" onClick={onClose}><XIcon size={17} /></button></header>
    <div className="frontier-panel-heading"><small>{topic.title}</small><h1><TopicHeadline topic={topic} /></h1><p>{topic.counts.total} 篇文献 · {topic.sourceIds.length} 种来源</p></div>
    <div role="tablist" aria-label="议题分析视图" className="frontier-view-controls qx-selection-control">{tabs.map((tab, index) => <button key={tab.id} type="button" role="tab" id={`frontier-tab-${tab.id}`} aria-selected={view === tab.id} aria-controls="frontier-topic-content" tabIndex={view === tab.id ? 0 : -1} onClick={() => onStateChange({ ...state, topicView: tab.id })} onKeyDown={(event) => { if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return; event.preventDefault(); const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length; onStateChange({ ...state, topicView: tabs[next].id }); event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('button')[next]?.focus() }}>{tab.label}</button>)}</div>
    <div id="frontier-topic-content" role="tabpanel" aria-labelledby={`frontier-tab-${view}`} className="frontier-panel-content" key={`${topic.id}:${view}`}>
      {view === 'overview' ? <>
        {development ? <div className="frontier-panel-summary">{statement(development)}</div> : null}
        <TopicChart topic={topic} sources={data.sources} />
        <div className="frontier-overview-columns"><section className="frontier-source-distribution"><h3>文献来源</h3>{sourceCounts.slice(0, 6).map((source) => <div key={source.name}><span>{source.name}</span><i style={{ width: `${source.count / Math.max(sourceCounts[0].count, 1) * 100}%` }} /><b>{source.count}</b></div>)}</section>
          {implication ? <section className="frontier-overview-implication"><h3>研究启发</h3>{statement(implication)}</section> : null}</div>
        {section('共同发现', brief?.consensus)}
        {hasSynthesis ? <button type="button" className="frontier-analysis-open" onClick={() => onStateChange({ ...state, topicView: 'analysis' })}>阅读综合解读</button> : null}
        {media.length ? <section className="frontier-research-figures"><h3>研究中的图表</h3>{media.map((item) => <FrontierSourceFigure key={item.url} media={item} />)}</section> : null}
      </> : view === 'analysis' ? <article className="frontier-synthesis">
        {section('研究进展', development ? [development] : [])}{section('共同发现', brief?.consensus)}{section('差异与讨论', brief?.differences)}{section('方法与材料', brief?.methods)}{section('研究启发', implication ? [implication] : [])}
        {brief?.priorityReads.length ? <section className="frontier-analysis-section"><h3>建议阅读顺序</h3><ol className="frontier-priority-reads">{brief.priorityReads.map((read) => { const record = data.records.find((item) => item.id === read.recordId); return record ? <li key={record.id}><button type="button" onClick={() => onOpenRecord(record.id)}>{record.title}</button><p>{read.reason}</p></li> : null })}</ol></section> : null}
        {!development && !implication ? <FrontierRecordResults records={records} state={state} title="相关研究" onStateChange={onStateChange} onOpenRecord={onOpenRecord} /> : null}
      </article> : <><div className="frontier-panel-source-filter"><select aria-label="筛选来源" value={state.source} onChange={(event) => onStateChange({ ...state, source: event.target.value, limit: 6 })}><option value="">全部来源</option>{[...new Set(data.records.filter((record) => topic.recordIds.includes(record.id)).map((record) => record.source_name))].map((name) => <option key={name}>{name}</option>)}</select>{state.query || state.source ? <button type="button" onClick={() => onStateChange({ ...state, query: "", source: "", limit: 6 })}>清除筛选</button> : null}</div><FrontierRecordResults records={records} state={state} title="筛选结果" onStateChange={onStateChange} onOpenRecord={onOpenRecord} /></>}
    </div>
  </section>
}
