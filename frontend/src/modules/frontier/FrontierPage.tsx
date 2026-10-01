import "../../styles/selection-controls.css";
import { useLayoutEffect, useRef, useState } from "react";
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
import { FrontierTopicPanel, FrontierTopicRows, FrontierRecordResults } from "./FrontierTopicPanel";
import type { FrontierDataset } from "./dataset";
import "../../styles/knowledge-library.css";
import "./frontier.css";

export interface FrontierPageProps {
  data: FrontierDataset;
  state: FrontierState;
  onStateChange: (state: FrontierState) => void;
  onOpenLibrary: () => void;
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

export function FrontierPage({ state, onStateChange, data }: FrontierPageProps) {
  const [input, setInput] = useState(state.query);
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollPositions = useRef(new Map<string, number>());
  const listKey = [state.query, state.kind, state.source, state.topic].join("|");
  useLayoutEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = state.record ? 0 : (scrollPositions.current.get(listKey) ?? 0);
  }, [listKey, state.record]);
  useLayoutEffect(() => setInput(state.query), [state.query]);
  const allRecords = data.records;
  const allSources = [...new Set(allRecords.map((record) => record.source_name))];
  const topic = data.topics.find((item) => item.id === state.topic);
  const eligible = topic ? allRecords.filter((record) => topic.recordIds.includes(record.id)) : allRecords;
  const records = filterFrontier(eligible, topic ? { ...state, topic: "" } : state);
  const corpusReady = hasCompleteCorpusOverview(data);
  const requestedLanding = state.landingView ?? "overview";
  const landing = requestedLanding === "overview" && !corpusReady ? "topics" : requestedLanding;
  const selected = allRecords.find((record) => record.id === state.record);
  const changeFilter = (patch: Partial<FrontierState>) => onStateChange({ ...state, ...patch, record: "", limit: 6 });
  const topics = data.topics.filter((item) => item.counts.total > 0 && item.key !== "uncategorized" && (state.kind === "all" || item.stream === state.kind)).toSorted((a, b) => Number(Boolean(b.researchBrief || b.editorialBrief)) - Number(Boolean(a.researchBrief || a.editorialBrief)) || b.counts.total - a.counts.total);
  const hasFilters = Boolean(state.query || state.source || state.kind !== "all");
  const openRecord = (record: string) => onStateChange({ ...state, record });
  return <section className="knowledge-surface knowledge-library frontier frontier-feedly" data-dimension-tone="ontology">
    <main className="knowledge-library__main">
      <header className="knowledge-library__topbar"><p><span>知识库</span><b>/</b>学术前沿</p>
        <form className="knowledge-library__search frontier-search" role="search" aria-label="搜索学术前沿" onSubmit={(event) => { event.preventDefault(); changeFilter({ query: input, topicView: "sources", landingView: "papers" }); }}>
          <MagnifyingGlassIcon size={15} aria-hidden="true" /><label htmlFor="frontier-search-input" className="knowledge-ui__visually-hidden">关键词、主题或作者</label><input id="frontier-search-input" type="search" value={input} onChange={(event) => setInput(event.target.value)} placeholder="搜索论文、议题、作者" maxLength={200} /><button type="submit" aria-label="提交搜索"><ArrowRightIcon size={14} aria-hidden="true" /></button>
        </form>
      </header>
      <div className="knowledge-library__content frontier-scroll" ref={scrollRef} data-topic-open={Boolean(topic && !state.record)} onScroll={(event) => { if (!state.record) scrollPositions.current.set(listKey, event.currentTarget.scrollTop); }}>
        {selected ? <RecordDetail record={selected} onBack={() => onStateChange({ ...state, record: "" })} /> : state.record ? <div className="frontier-empty"><h1>未找到这条资料</h1><button type="button" onClick={() => onStateChange({ ...state, record: "" })}>返回资料列表</button></div> : <div className="frontier-workspace" data-topic-open={Boolean(topic)}>
          <div className="frontier-index">
            <header className="frontier-index-heading"><div><h1>学术前沿</h1>{landing !== "overview" || topic ? <p>{allRecords.length} 篇文献 · {allSources.length} 种来源</p> : null}</div><span>{data.asOf}</span></header>
            {!topic ? <div className="frontier-home-controls qx-selection-control" role="group" aria-label="学术前沿视图">{([{ id: "overview", label: "研究总览" }, { id: "topics", label: "研究议题" }, { id: "papers", label: "全部文献" }] as const).map((item) => <button key={item.id} type="button" aria-pressed={landing === item.id} onClick={() => onStateChange({ ...state, landingView: item.id, topic: "", record: "", query: "", source: "", kind: item.id === "overview" ? "all" : state.kind, limit: 6 })}>{item.label}</button>)}</div> : null}
            {!topic && landing === "overview" ? <FrontierCorpusOverview data={data} onOpenRecord={openRecord} /> : null}
            {topic || landing !== "overview" ? <div className="frontier-filterbar"><div className="frontier-kind-controls qx-selection-control" aria-label="资料类型">{kinds.map((kind) => <button type="button" key={kind.key} aria-label={kind.label} aria-pressed={state.kind === kind.key} onClick={() => changeFilter({ kind: kind.key, topic: "", topicView: "overview" })}>{kind.label}</button>)}</div>
              {!topic ? <div className="frontier-selects"><select aria-label="筛选议题" value={state.topic} onChange={(event) => changeFilter({ topic: event.target.value, topicView: "overview" })}><option value="">全部议题</option>{topics.map((item) => <option key={item.id} value={item.id}>{item.title}{state.kind === "all" ? ` · ${item.stream === "research" ? "研究" : "实践"}` : ""}</option>)}</select><select aria-label="筛选来源" value={state.source} onChange={(event) => changeFilter({ source: event.target.value, topicView: "sources" })}><option value="">全部来源</option>{allSources.map((source) => <option key={source}>{source}</option>)}</select></div> : null}
            </div> : null}
            {(topic || landing === "topics") && topics.length ? <section className="frontier-topic-overview"><header><h2>研究议题</h2><span>{topics.length} 个议题</span></header><FrontierTopicRows topics={topics} data={data} selected={state.topic} onSelect={(id) => changeFilter({ topic: id, topicView: "overview" })} /></section> : null}
            {!topic && (landing === "papers" || (landing === "topics" && !corpusReady)) ? <>
              {hasFilters ? <div className="knowledge-library__filters frontier-active-filter"><span>{[state.query, state.source, state.kind !== "all" ? kinds.find((kind) => kind.key === state.kind)?.label : ""].filter(Boolean).join(" · ")}</span><button type="button" onClick={() => changeFilter({ query: "", source: "", kind: "all" })}>清除筛选</button></div> : null}
              <div aria-live="polite" className="knowledge-ui__visually-hidden">找到 {records.length} 条资料</div>
              <FrontierRecordResults records={records} state={state} title={hasFilters ? "筛选结果" : "最新收录"} onStateChange={onStateChange} onOpenRecord={openRecord} />
            </> : null}
          </div>
          {topic ? <FrontierTopicPanel topic={topic} data={data} records={records} state={state} onStateChange={onStateChange} onOpenRecord={openRecord} onClose={() => changeFilter({ topic: "", topicView: "overview" })} /> : null}
        </div>}
      </div>
    </main>
  </section>;
}
