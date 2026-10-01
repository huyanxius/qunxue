import { BrandLoading } from '../../ui/BrandLoading';
import type { FrontierDataset } from './dataset';
import type { FrontierRecord } from './model';
import type { FrontierPeriodData } from './frontierReadingTypes';

// Only a source-backed question/finding pair qualifies for this reading entry.
// This is a reading aid, not an academic-value score.
export function FrontierFocus({ records, onOpenRecord }: { records: readonly FrontierRecord[]; onOpenRecord: (id: string) => void }) {
  const focus = records.filter(record => ['lead_only', 'verified_frontier'].includes(record.verification_status) && record.research_question?.trim() && record.findings.some(text => text.trim())).slice(0, 4);
  return <section className="frontier-reading-focus" aria-labelledby="frontier-focus-title">
    <header className="frontier-reading-section"><h2 id="frontier-focus-title">值得关注</h2><span>从问题进入研究</span></header>
    <div className="frontier-focus-grid">{focus.map(record => <article className="frontier-focus-story" key={record.id}>
      <small>{record.source_name}</small><h3><button type="button" onClick={() => onOpenRecord(record.id)}>{record.research_question}</button></h3>
      <p>{record.findings.find(text => text.trim())?.match(/^.*?[。！？.!?]/)?.[0].trim() || record.findings.find(text => text.trim())}</p>
      <footer><span>{record.published_at_display}</span><button type="button" aria-label={`阅读 ${record.title}`} onClick={() => onOpenRecord(record.id)}>{record.title} <span aria-hidden="true">↗</span></button></footer>
    </article>)}</div>
    {!focus.length ? <p className="frontier-reading-status">当前资料缺少可核对的问题与发现，请从文献列表阅读。</p> : null}
  </section>;
}

export function FrontierTrends({ data, report, topic, onTopicChange, comparisonYear, onComparisonYearChange, loading, error, onRetry, onOpenRecord }: {
  data: FrontierDataset; report?: FrontierPeriodData | null; topic?: string; onTopicChange?: (key: string) => void;
  comparisonYear?: number | null; onComparisonYearChange?: (year: number | null) => void;
  loading?: boolean; error?: string; onRetry?: () => void; onOpenRecord: (id: string) => void;
}) {
  const complete = report?.comparability === 'complete_common_cohort' && report.previous_share !== null && report.current_share !== null && report.delta_pp !== null;
  const choices = data.topics.filter(item => item.stream === 'research' && item.key !== 'uncategorized');
  const sources = report?.cohort_source_ids.map(id => data.sources.find(source => source.id === id)?.name || id).join('、');
  const latestYear = Number(data.asOf.slice(0, 4)) - 1;
  return <section className="frontier-reading-trends" aria-labelledby="frontier-trends-title">
    <header className="frontier-reading-section"><h2 id="frontier-trends-title">研究趋势</h2><span>同期样本比较</span></header>
    <div className="frontier-trend-controls">
      {onTopicChange && choices.length ? <label><span className="knowledge-ui__visually-hidden">趋势议题</span><select aria-label="趋势议题" value={choices.find(item => item.key === topic || item.title === topic)?.key || topic} onChange={event => onTopicChange(event.target.value)}>{choices.map(item => <option key={item.id} value={item.key}>{item.title}</option>)}</select></label> : <strong>{choices.find(item => item.key === topic)?.title || topic || '研究议题'}</strong>}
      {onComparisonYearChange ? <select aria-label="比较时期" value={comparisonYear ?? 'date'} onChange={event => onComparisonYearChange(event.target.value === 'date' ? null : Number(event.target.value))}>{[latestYear, latestYear - 1].map(year => <option key={year} value={year}>{year - 1} / {year} 完整年度</option>)}<option value="date">按阅读日期 · 最近完整月</option></select> : null}
    </div>
    {loading ? <BrandLoading compact message="正在读取同期样本…" /> : error ? <p role="alert" className="frontier-reading-status">趋势暂时无法读取。{onRetry ? <button type="button" onClick={onRetry}>重试</button> : null}</p> : report ? <>
      <p className="frontier-trend-basis">{sources || '已核对来源'} · 所列期次样本份额{report.share_basis === 'fixed_issue_sample_common_sources' ? ' · 各刊词典命中比例的平均值 · 期刊等权' : ''}</p>
      <p className="frontier-trend-window">{report.previous_window.start}—{report.previous_window.end}<br />{report.current_window.start}—{report.current_window.end}</p>
      {complete ? <div className="frontier-share-comparison"><strong>{(report.previous_share! * 100).toFixed(1)}% → {(report.current_share! * 100).toFixed(1)}%</strong><span>{report.delta_pp! > 0 ? '+' : ''}{report.delta_pp!.toFixed(1)} 个百分点</span>
        <div className="frontier-share-bars" role="img" aria-label={`前期${(report.previous_share! * 100).toFixed(1)}%，当期${(report.current_share! * 100).toFixed(1)}%`}><i style={{ width: `${Math.max(0, Math.min(100, report.previous_share! * 100))}%` }} /><i style={{ width: `${Math.max(0, Math.min(100, report.current_share! * 100))}%` }} /></div>
      </div> : <p className="frontier-reading-status">完整同期覆盖不足，暂不判断趋势。</p>}
      <p className="frontier-trend-counts">前期：命中 {report.cohort_previous_count} 篇，样本 {report.previous_denominator} 篇；当期：命中 {report.cohort_current_count} 篇，样本 {report.current_denominator} 篇</p>
      <details className="frontier-trend-scope"><summary>查看样本与测量方法</summary>{report.comparison_issue_keys.length ? <p>{report.comparison_issue_keys.join('、')}</p> : null}<p>题名与出版者关键词词典命中；不作语义主题判定。</p><p>未分类：前期 {report.classification_coverage.previous.uncategorized} 篇，当期 {report.classification_coverage.current.uncategorized} 篇。</p><p>方法版本：{report.method_version} · {report.measurement_version}</p></details>
      <div className="frontier-trend-evidence">{report.evidence_record_ids.flatMap(id => { const record = data.records.find(item => item.id === id); return record && ['lead_only', 'verified_frontier'].includes(record.verification_status) ? [record] : []; }).slice(0, 3).map(record => <button key={record.id} type="button" onClick={() => onOpenRecord(record.id)}>{record.title}</button>)}</div>
    </> : <p className="frontier-reading-status">尚无同期比较数据。</p>}
    <small>发表数量不代表研究价值。</small>
  </section>;
}
