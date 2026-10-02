import { BrandLoading } from '../../ui/BrandLoading';
import "../../styles/selection-controls.css";
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  ArrowUpRightIcon,
  MagnifyingGlassIcon,
} from "@phosphor-icons/react";
import {
  filterFrontier,
  sourceDate,
  type FrontierRecord,
  type FrontierState,
} from "./model";
import { FrontierCorpusOverview, hasCompleteCorpusOverview } from "./FrontierCorpusOverview";
import { FrontierSourceFigure } from "./FrontierSourceFigure";
import { FrontierTopicPanel, FrontierTopicRows, FrontierRecordResults, type FrontierPagination } from "./FrontierTopicPanel";
import type { FrontierDataset } from "./dataset";
import "../../styles/knowledge-library.css";
import "./frontier.css";
import "./frontier-reading.css";
import { FrontierFocus, FrontierTrends } from "./FrontierReadingHome";
import { FrontierCalendar } from "./FrontierCalendar";
import type { FrontierCalendarData, FrontierPeriodData } from "./frontierReadingTypes";

// Keep list positions across route unmounts while this browser session is open.
const liveScrollPositions = new Map<string, number>();

export interface FrontierPageProps {
  data: FrontierDataset;
  state: FrontierState;
  onStateChange: (state: FrontierState) => void;
  onOpenLibrary: () => void;
  readingDate?: string;
  maxReadingDate?: string;
  onReadingDateChange?: (date: string) => void;
  calendar?: FrontierCalendarData | null;
  report?: FrontierPeriodData | null;
  reportTopic?: string;
  onReportTopicChange?: (key: string) => void;
  comparisonYear?: number | null;
  onComparisonYearChange?: (year: number | null) => void;
  loading?: boolean;
  calendarLoading?: boolean;
  reportLoading?: boolean;
  calendarError?: string;
  reportError?: string;
  dataError?: string;
  onRetry?: () => void;
  renderRecordInsights?: (id: string) => ReactNode;
  onRequestRecords?: (ids: string[]) => void;
  pagination?: FrontierPagination;
  listRecords?: readonly FrontierRecord[];
  focusRecords?: readonly FrontierRecord[];
  selectedRecord?: FrontierRecord | null;
  detailLoading?: boolean;
  detailError?: boolean;
  onRetryDetail?: () => void;
  topicLoading?: boolean;
  topicError?: boolean;
  onRetryTopic?: () => void;
  statisticsError?: boolean;
  metadataError?: boolean;
  onRetryMetadata?: () => void;

}
function landingRecords(records: FrontierRecord[], landing: FrontierState['landingView'], kind: FrontierState['kind']) {
  return (landing ?? 'overview') === 'overview' && kind === 'all' ? records.filter(record => ['lead_only', 'verified_frontier'].includes(record.verification_status)) : records;
}
const kinds = [
  { key: "all", label: "全部资料" },
  { key: "research", label: "学术研究" },
  { key: "practice", label: "实践观察" },
] as const;
function SourceLink({ record }: { record: FrontierRecord }) {
  return (
    <a
      className="frontier-source-link"
      href={record.url}
      target="_blank"
      rel="noopener noreferrer"
    >
      阅读原始来源 <ArrowUpRightIcon size={14} aria-hidden="true" />
    </a>
  );
}
function RecordDetail({
  record,
  onBack,
}: {
  record: FrontierRecord;
  onBack: () => void;
}) {
  const methods = Array.isArray(record.methods)
    ? record.methods.join("、")
    : record.methods;
  return (
    <article
      className="frontier-detail"
      aria-labelledby="frontier-detail-title"
    >
      <button className="knowledge-library__results-back" type="button" onClick={onBack}>
        <ArrowLeftIcon size={16} />
        返回资料列表
      </button>
      <div className="frontier-meta">
        <span>{record.source_name}</span>
        <span>{record.published_at_display}</span>
      </div>
      <h1 id="frontier-detail-title">{record.title}</h1>
      <p className="frontier-byline">
        {record.authors?.join("、") || record.source_publisher}
      </p>
      {record.summary.trim() ? <section className="frontier-abstract" aria-labelledby="frontier-abstract-title">
        <h2 id="frontier-abstract-title">摘要</h2>
        <p className="frontier-detail__summary">{record.summary}</p>
      </section> : null}
      <div className="frontier-detail__source">
        <div>
          <strong>{record.source_publisher}</strong>
          <small>{sourceDate(record)}</small>
        </div>
        <SourceLink record={record} />
      </div>
      {record.media?.slice(0, 2).map((media) => <FrontierSourceFigure key={media.url} media={media} />)}
      {record.why_read ? <section><h2>为什么读这篇</h2><p>{record.why_read}</p></section> : null}
      {record.research_question ? (
        <section>
          <h2>研究问题</h2>
          <p>{record.research_question}</p>
        </section>
      ) : null}
      {record.findings.some((finding) => finding.trim()) ? <section>
        <h2>
          {record.verification_status === "practice_signal"
            ? "实践内容"
            : "主要发现"}
        </h2>
        {record.findings.map((finding) => (
          <p key={finding}>{finding}</p>
        ))}
      </section> : null}
      {methods || record.data ? (
        <section>
          <h2>研究材料与方法</h2>
          {methods ? <p>{methods}</p> : null}
          {record.data ? <p>{record.data}</p> : null}
        </section>
      ) : null}
      <details className="frontier-detail__evidence">
        <summary>来源信息</summary>
        <p>{record.source_publisher} · {record.published_at_display}</p>
        <p>{record.verification_status === "practice_signal" ? "内容依据：实践报道" : record.verification_status === "lead_only" ? "内容依据：摘要或官方研究简介" : "内容依据：原始研究材料"}</p>
        {record.source_published_at && record.source_published_at !== record.published_at ? <p>来源网页更新于 {record.source_published_at}</p> : null}
        <SourceLink record={record} />
      </details>

    </article>
  );
}

export function FrontierPage({ state, onStateChange, data, readingDate = data.asOf, maxReadingDate = data.asOf, onReadingDateChange, calendar, report, reportTopic, onReportTopicChange, comparisonYear, onComparisonYearChange, loading, calendarLoading, reportLoading, calendarError, reportError, dataError, onRetry, renderRecordInsights, onRequestRecords, pagination, listRecords, focusRecords, selectedRecord, detailLoading, detailError, onRetryDetail, topicLoading, topicError, onRetryTopic, statisticsError, metadataError, onRetryMetadata }: FrontierPageProps) {
  const [input, setInput] = useState(state.query);
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollPositions = useRef(data.partialRecords ? liveScrollPositions : new Map<string, number>());
  const listKey = [readingDate, state.query, state.kind, state.source, state.topic, state.landingView, state.topicView].join("|");
  useLayoutEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = state.record ? 0 : (scrollPositions.current.get(listKey) ?? 0);
  }, [listKey, state.record, loading, pagination?.loading, data.records.length]);
  useLayoutEffect(() => setInput(state.query), [state.query]);
  const allRecords = data.records;
  const allSources = pagination ? data.sources.map(source => ({ value: source.id, label: source.name })) : [...new Set(allRecords.map(record => record.source_name))].map(name => ({ value: name, label: name }));
  const topic = data.topics.find((item) => item.id === state.topic);
  const eligible = topic ? allRecords.filter((record) => topic.recordIds.includes(record.id)) : allRecords;
  const records = pagination ? [...(listRecords ?? allRecords)] : filterFrontier(eligible, topic ? { ...state, topic: "" } : state);
  const homeRecords = landingRecords(records, state.landingView, state.kind);
  const corpusReady = hasCompleteCorpusOverview(data);
  const landing = state.landingView ?? "overview";
  const selected = pagination ? selectedRecord : allRecords.find((record) => record.id === state.record);
  const changeFilter = (patch: Partial<FrontierState>) => onStateChange({ ...state, ...patch, record: "", limit: 6 });
  const topics = data.topics.filter((item) => item.counts.total > 0 && item.key !== "uncategorized" && (state.kind === "all" || item.stream === state.kind)).toSorted((a, b) => Number(Boolean(b.researchBrief || b.editorialBrief)) - Number(Boolean(a.researchBrief || a.editorialBrief)) || b.counts.total - a.counts.total);
  const hasFilters = Boolean(state.query || state.source || state.kind !== "all");
  const openRecord = (record: string) => onStateChange({ ...state, record });
  const shiftDate = (delta: number) => {
    const date = new Date(`${readingDate}T12:00:00Z`);
    date.setUTCDate(date.getUTCDate() + delta);
    const next = date.toISOString().slice(0, 10);
    if (next <= maxReadingDate) onReadingDateChange?.(next);
  };
  const date = new Date(`${readingDate}T12:00:00Z`);
  return <section className="knowledge-surface knowledge-library frontier frontier-feedly" data-dimension-tone="ontology">
    <main className="knowledge-library__main">
      <header className="knowledge-library__topbar"><p><span>知识库</span><b>/</b>学术前沿</p>
        <form className="knowledge-library__search frontier-search" role="search" aria-label="搜索学术前沿" onSubmit={(event) => { event.preventDefault(); changeFilter({ query: input, topicView: "sources", landingView: "papers" }); }}>
          <MagnifyingGlassIcon size={15} aria-hidden="true" /><label htmlFor="frontier-search-input" className="knowledge-ui__visually-hidden">关键词、主题或作者</label><input id="frontier-search-input" type="search" value={input} onChange={(event) => setInput(event.target.value)} placeholder="搜索论文、议题、作者" maxLength={200} /><button type="submit" aria-label="提交搜索"><ArrowRightIcon size={14} aria-hidden="true" /></button>
        </form>
      </header>
      <div className="knowledge-library__content frontier-scroll" ref={scrollRef} data-topic-open={Boolean(topic && !state.record)} onScroll={(event) => { if (!state.record && !loading && !pagination?.loading) { scrollPositions.current.set(listKey, event.currentTarget.scrollTop); if (scrollPositions.current.size > 100) scrollPositions.current.delete(scrollPositions.current.keys().next().value!); } }}>
        <header className="frontier-reading-date"><div><small>{date.getUTCFullYear()}年 · {new Intl.DateTimeFormat('zh-CN', { weekday: 'long', timeZone: 'UTC' }).format(date)}</small><h1>{date.getUTCMonth() + 1}月{date.getUTCDate()}日</h1></div><div className="frontier-date-actions"><button type="button" aria-label="前一天" disabled={!onReadingDateChange} onClick={() => shiftDate(-1)}>‹</button><label><span className="knowledge-ui__visually-hidden">阅读日期</span><input aria-label="阅读日期" type="date" value={readingDate} max={maxReadingDate} disabled={!onReadingDateChange} onChange={event => { if (/^\d{4}-\d{2}-\d{2}$/.test(event.target.value) && event.target.value <= maxReadingDate) onReadingDateChange?.(event.target.value); }} /></label><button type="button" aria-label="后一天" disabled={!onReadingDateChange || readingDate >= maxReadingDate} onClick={() => shiftDate(1)}>›</button></div></header>
        <div className="frontier-reading-layout"><div className="frontier-reading-primary">
        {loading ? <BrandLoading message="正在读取这个日期的资料…" /> : dataError ? <div className="frontier-reading-status" role="alert"><p>这个日期的资料暂时无法读取。</p><button type="button" onClick={onRetry}>重新加载</button></div> : state.record && detailLoading ? <BrandLoading message="正在读取文献详情…" /> : state.record && detailError ? <div role="alert"><p>文献详情暂时无法读取。</p><button type="button" onClick={onRetryDetail}>重试</button><button type="button" onClick={() => onStateChange({ ...state, record: "" })}>返回资料列表</button></div> : selected ? <><RecordDetail record={selected} onBack={() => onStateChange({ ...state, record: "" })} />{renderRecordInsights?.(selected.id)}</> : state.record ? <div className="frontier-empty"><h1>未找到这条资料</h1><button type="button" onClick={() => onStateChange({ ...state, record: "" })}>返回资料列表</button></div> : <div className="frontier-workspace" data-topic-open={Boolean(topic)}>
          <div className="frontier-index">
            <p className="frontier-reading-scope">{data.corpusOverview ? <>{data.corpusOverview.statistics.researchCount} 篇研究 · {data.corpusOverview.statistics.practiceCount} 篇新闻与实践观察</> : pagination ? statisticsError ? <>资料统计暂时无法读取。<button type="button" onClick={onRetry}>重试统计</button></> : "正在读取资料统计…" : <>{allRecords.filter(record => ["lead_only", "verified_frontier"].includes(record.verification_status)).length} 篇研究 · {allRecords.filter(record => record.verification_status === "practice_signal").length} 篇新闻与实践观察</>}</p>
            {!topic ? <div className="frontier-home-controls qx-selection-control" role="group" aria-label="学术前沿视图">{([{ id: "overview", label: "值得关注" }, { id: "topics", label: "研究议题" }, { id: "papers", label: "全部文献" }] as const).map((item) => <button key={item.id} type="button" aria-pressed={landing === item.id} onClick={() => onStateChange({ ...state, landingView: item.id, topic: "", record: "", kind: item.id === "overview" ? "all" : state.kind, limit: 6 })}>{item.label}</button>)}</div> : null}
            {!topic && landing === "overview" ? <><FrontierFocus records={focusRecords ?? records} onOpenRecord={openRecord} /><FrontierTrends data={data} report={report} topic={reportTopic} onTopicChange={onReportTopicChange} comparisonYear={comparisonYear} onComparisonYearChange={onComparisonYearChange} loading={reportLoading} error={reportError} onRetry={onRetry} onOpenRecord={openRecord} />{corpusReady ? <details className="frontier-long-review" onToggle={event => { if (event.currentTarget.open) onRequestRecords?.(data.corpusOverview?.overview?.sections.flatMap(section => section.statements.flatMap(statement => statement.evidenceRecordIds)) ?? []); }}><summary>阅读完整研究综述</summary><FrontierCorpusOverview data={data} onOpenRecord={openRecord} onRequestRecords={onRequestRecords} /></details> : null}</> : null}
            {topic || landing !== "overview" || !corpusReady ? <div className="frontier-filterbar"><div className="frontier-kind-controls qx-selection-control" aria-label="资料类型">{kinds.map((kind) => <button type="button" key={kind.key} aria-label={kind.label} aria-pressed={state.kind === kind.key} onClick={() => changeFilter({ kind: kind.key, topic: "", topicView: "overview" })}>{kind.label}</button>)}</div>
              {!topic ? <div className="frontier-selects"><select aria-label="筛选议题" value={state.topic} onChange={(event) => changeFilter({ topic: event.target.value, topicView: "overview" })}><option value="">全部议题</option>{topics.map((item) => <option key={item.id} value={item.id}>{item.title}{state.kind === "all" ? ` · ${item.stream === "research" ? "研究" : "实践"}` : ""}</option>)}</select><select aria-label="筛选来源" value={pagination ? data.sources.find(source => source.id === state.source || source.name === state.source)?.id || state.source : state.source} onChange={(event) => changeFilter({ source: event.target.value, topicView: "sources" })}><option value="">全部来源</option>{allSources.map(source => <option key={source.value} value={source.value}>{source.label}</option>)}</select></div> : null}
            </div> : null}
            {(topic || landing === "topics") && topics.length ? <section className="frontier-topic-overview"><header><h2>研究议题</h2><span>{topics.length} 个议题</span></header><FrontierTopicRows topics={topics} data={data} selected={state.topic} onSelect={(id) => changeFilter({ topic: id, topicView: "overview" })} /></section> : null}
            {!topic && (landing === "overview" || landing === "papers" || !corpusReady) ? <>
              {hasFilters ? <div className="knowledge-library__filters frontier-active-filter"><span>{[state.query, data.sources.find(source => source.id === state.source)?.name || state.source, state.kind !== "all" ? kinds.find((kind) => kind.key === state.kind)?.label : ""].filter(Boolean).join(" · ")}</span><button type="button" onClick={() => changeFilter({ query: "", source: "", kind: "all" })}>清除筛选</button></div> : null}
              <div aria-live="polite" className="knowledge-ui__visually-hidden">找到 {pagination?.total ?? records.length} 条资料</div>
              <FrontierRecordResults records={homeRecords} state={state} title={hasFilters ? "筛选结果" : landing === "overview" ? "最新研究" : "最新收录"} pagination={pagination} onStateChange={onStateChange} onOpenRecord={openRecord} />
            </> : null}
            {!topic && landing === "overview" && state.kind === "all" && allRecords.some(record => record.verification_status === "practice_signal") ? <section className="frontier-practice-reading" aria-label="新闻与实践观察"><header className="frontier-reading-section"><h2>新闻与实践观察</h2><span>{data.corpusOverview?.statistics.practiceCount ?? allRecords.filter(record => record.verification_status === "practice_signal").length} 篇</span></header><ul>{allRecords.filter(record => record.verification_status === "practice_signal").slice(0, 3).map(record => <li key={record.id}><small>{record.source_name} · {record.published_at_display}</small><button type="button" onClick={() => openRecord(record.id)}>{record.title}</button></li>)}</ul><button type="button" onClick={() => changeFilter({ kind: "practice", landingView: "papers" })}>浏览新闻与实践观察</button></section> : null}
            {metadataError ? <p role="alert">议题或来源暂时无法读取。<button type="button" onClick={onRetryMetadata}>重试筛选项</button></p> : null}
          </div>
          {state.topic && topicLoading ? <BrandLoading message="正在读取议题分析…" /> : state.topic && topicError ? <div role="alert"><p>议题分析暂时无法读取。</p><button type="button" onClick={onRetryTopic}>重试议题</button></div> : topic ? <FrontierTopicPanel topic={topic} data={data} records={records} state={state} onStateChange={onStateChange} onOpenRecord={openRecord} onClose={() => changeFilter({ topic: "", topicView: "overview" })} pagination={pagination} /> : null}
        </div>}
        </div><FrontierCalendar onRequestRecords={onRequestRecords} data={data} calendar={calendar} readingDate={readingDate} onOpenRecord={openRecord} loading={calendarLoading || loading} error={calendarError} onRetry={onRetry} /></div>
      </div>
    </main>
  </section>;
}
