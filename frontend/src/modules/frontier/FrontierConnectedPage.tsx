import { BrandLoading } from '../../ui/BrandLoading';
import { createContext, useCallback, useContext, useEffect, useRef, useState, type PropsWithChildren } from 'react';
import { useInfiniteQuery, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { FrontierPage, type FrontierPageProps } from './FrontierPage';
import type { FrontierDataset } from './dataset';
import {
  readFrontierSummaries, readFrontierSources, readFrontierTopics, readFrontierRecord,
  readFrontierOverview, readFrontierPeriod, readFrontierCalendar,
} from './frontierApi';
import type { FrontierPeriodData } from './frontierReadingTypes';
import { FrontierRecordInsights } from './FrontierRecordInsights';
const PreviewContext = createContext<FrontierDataset | null>(null);
const cacheOptions = { staleTime: 5 * 60_000, gcTime: 30 * 60_000, retry: false, refetchOnWindowFocus: false } as const;

function shanghaiToday() {
  const parts = new Intl.DateTimeFormat('en', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  return ['year', 'month', 'day'].map(type => parts.find(part => part.type === type)!.value).join('-');
}
function readingDateError(date: string | undefined, latest: string) {
  if (date === undefined) return '';
  const parsed = new Date(`${date}T12:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== date) return '阅读日期无效，请修改地址中的 as_of。';
  return date > latest ? '阅读日期晚于可读取日期，请修改地址中的 as_of。' : '';
}

// Explicit snapshot injection is limited to review/tests. Service failures never
// fall back to a seed or prototype corpus in production.
export function FrontierPreviewProvider({ data, children }: PropsWithChildren<{ data: FrontierDataset }>) {
  return <PreviewContext.Provider value={data}>{children}</PreviewContext.Provider>;
}
export function FrontierConnectedPage(props: Omit<FrontierPageProps, 'data'>) {
  const preview = useContext(PreviewContext);
  return preview ? <FrontierPage {...props} data={preview} /> : <LiveFrontierPage {...props} />;
}
function LiveFrontierPage(props: Omit<FrontierPageProps, 'data'>) {
  const client = useQueryClient();
  const [maxReadingDate, setMaxReadingDate] = useState('');
  const [references, setReferences] = useState<{ asOf: string; batches: string[][] }>({ asOf: '', batches: [] });
  const [trendTopic, setTrendTopic] = useState('');
  const [year, setYear] = useState<number | null | undefined>();
  const lastAsOf = useRef('');
  const readingDate = props.state.asOf;
  const latestDate = maxReadingDate || shanghaiToday();
  const dateError = readingDateError(readingDate, latestDate);
  const [metadataReady, setMetadataReady] = useState(false);
  const sources = useQuery({ ...cacheOptions, queryKey: ['frontier', 'sources'], queryFn: ({ signal }) => readFrontierSources(signal), enabled: !dateError && (metadataReady || Boolean(props.state.source)) });
  const selectedSource = sources.data?.find(source => source.id === props.state.source || source.name === props.state.source);
  const overviewLanding = !props.state.topic && (props.state.landingView ?? 'overview') === 'overview' && props.state.kind === 'all';
  const filters = {
    asOf: readingDate, query: props.state.query, stream: overviewLanding ? 'research' as const : props.state.kind === 'all' ? undefined : props.state.kind,
    sourceId: selectedSource?.id, sourceName: !selectedSource ? props.state.source : undefined, topicId: props.state.topic,
  };
  const list = useInfiniteQuery({
    ...cacheOptions, queryKey: ['frontier', 'summaries', filters],
    initialPageParam: { offset: 0, asOf: readingDate },
    queryFn: ({ pageParam, signal }) => readFrontierSummaries({ ...filters, asOf: pageParam.asOf }, pageParam.offset, signal),
    getNextPageParam: last => last.nextOffset === null ? undefined : { offset: last.nextOffset, asOf: last.asOf },
    enabled: !dateError && (!props.state.source || sources.isSuccess),
  });
  const page = list.data?.pages[0];
  const asOf = readingDate || page?.asOf || lastAsOf.current;
  useEffect(() => {
    if (!page) return;
    lastAsOf.current = page.asOf;
    const timer = window.setTimeout(() => setMetadataReady(true), 0);
    if (readingDate === undefined) setMaxReadingDate(page.asOf);
    return () => window.clearTimeout(timer);
  }, [page, readingDate]);
  useEffect(() => { setYear(undefined); }, [readingDate]);
  const ready = Boolean(page && asOf && !dateError);
  const backgroundReady = ready && metadataReady;
  const topics = useQuery({ ...cacheOptions, queryKey: ['frontier', 'topics', asOf], queryFn: ({ signal }) => readFrontierTopics(asOf, undefined, signal), enabled: backgroundReady });
  const topicDetail = useQuery({ ...cacheOptions, queryKey: ['frontier', 'topic', asOf, props.state.topic], queryFn: ({ signal }) => readFrontierTopics(asOf, props.state.topic, signal), enabled: ready && Boolean(props.state.topic) && !props.state.record });
  const detail = useQuery({ ...cacheOptions, queryKey: ['frontier', 'record', asOf, props.state.record], queryFn: ({ signal }) => readFrontierRecord(props.state.record, asOf, signal), enabled: ready && Boolean(props.state.record) });
  const calendar = useQuery({ ...cacheOptions, queryKey: ['frontier', 'calendar', asOf], queryFn: ({ signal }) => readFrontierCalendar(asOf, signal), enabled: backgroundReady });
  const overview = useQuery({ ...cacheOptions, queryKey: ['frontier', 'overview', asOf], queryFn: ({ signal }) => readFrontierOverview(asOf, signal), enabled: backgroundReady });
  const practice = useQuery({ ...cacheOptions, queryKey: ['frontier', 'practice', asOf, filters.query, filters.sourceId, filters.sourceName], queryFn: ({ signal }) => readFrontierSummaries({ ...filters, asOf, stream: 'practice', limit: 3 }, 0, signal), enabled: backgroundReady && overviewLanding });
  const focus = useQuery({ ...cacheOptions, queryKey: ['frontier', 'focus', asOf, filters.query, filters.sourceId, filters.sourceName], queryFn: ({ signal }) => readFrontierSummaries({ ...filters, asOf, stream: 'research', focus: true, limit: 4 }, 0, signal), enabled: backgroundReady && overviewLanding });
  const researchTopics = topics.data?.filter(topic => topic.stream === 'research' && topic.key !== 'uncategorized') ?? [];
  const topicKey = trendTopic || researchTopics.find(topic => topic.id === props.state.topic)?.key || researchTopics[0]?.key || '';
  const comparisonYear = year === null ? null : Math.min(year ?? Number(asOf.slice(0, 4)) - 1, Number(asOf.slice(0, 4)) - 1);
  const report = useQuery({ ...cacheOptions, queryKey: ['frontier', 'period', asOf, topicKey, comparisonYear, year === undefined], enabled: backgroundReady && overviewLanding && Boolean(topicKey), queryFn: async ({ signal }) => {
    const value = await readFrontierPeriod(topicKey, asOf, comparisonYear ?? undefined, signal);
    const complete = (candidate: FrontierPeriodData) => candidate.comparability === 'complete_common_cohort' && candidate.current_share !== null && candidate.previous_share !== null && candidate.delta_pp !== null;
    if (year === undefined && comparisonYear && !complete(value)) {
      try {
        const previous = await readFrontierPeriod(topicKey, asOf, comparisonYear - 1, signal);
        if (complete(previous)) return { value: previous, comparisonYear: comparisonYear - 1 };
      } catch (error) { if (signal.aborted) throw error; /* Preserve explicit coverage status. */ }
    }
    return { value, comparisonYear };
  } });
  const referenceBatches = references.asOf === asOf ? references.batches : [];
  const referenceQueries = useQueries({ queries: referenceBatches.map(ids => ({ ...cacheOptions,
    queryKey: ['frontier', 'references', asOf, ids],
    queryFn: ({ signal }: { signal: AbortSignal }) => readFrontierSummaries({ asOf, recordIds: ids }, 0, signal), enabled: ready,
  })) });
  const requestRecords = useCallback((ids: string[]) => {
    const loaded = new Set(list.data?.pages.flatMap(item => item.records.map(record => record.id)) ?? []);
    setReferences(previous => {
      const batches = previous.asOf === asOf ? previous.batches : [];
      const existing = new Set(batches.flat());
      const needed = [...new Set(ids)].filter(id => !loaded.has(id) && !existing.has(id)).slice(0, 100);
      if (!needed.length) return previous;
      const added = Array.from({ length: Math.ceil(needed.length / 24) }, (_, index) => needed.slice(index * 24, index * 24 + 24));
      return { asOf, batches: [...batches, ...added] };
    });
  }, [asOf, list.data]);
  useEffect(() => {
    const topic = topicDetail.data?.[0];
    requestRecords([...(report.data?.value.evidence_record_ids.slice(0, 3) ?? []), ...(topic?.researchBrief?.evidenceRecordIds ?? topic?.editorialBrief?.evidenceRecordIds ?? []), ...(topic?.researchBrief?.priorityReads.map(read => read.recordId) ?? [])]);
  }, [topicDetail.data, report.data, requestRecords]);
  const selectedTopicEvidence = topicDetail.data?.[0]?.researchBrief?.evidenceRecordIds ?? topicDetail.data?.[0]?.editorialBrief?.evidenceRecordIds ?? [];
  const mediaSummaryRecords = [...(list.data?.pages.flatMap(item => item.records) ?? []), ...referenceQueries.flatMap(query => query.data?.records ?? [])];
  const mediaRecordIds = selectedTopicEvidence.filter(id => mediaSummaryRecords.some(record => record.id === id && record.has_media)).slice(0, 2);
  const mediaQueries = useQueries({ queries: mediaRecordIds.map(id => ({ ...cacheOptions,
    queryKey: ['frontier', 'record', asOf, id], queryFn: ({ signal }: { signal: AbortSignal }) => readFrontierRecord(id, asOf, signal),
    enabled: ready && Boolean(props.state.topic) && !props.state.record,
  })) });
  const loadedCount = list.data?.pages.reduce((count, item) => count + item.records.length, 0) ?? 0;
  const { hasNextPage, isFetching, isFetchNextPageError, fetchNextPage } = list;
  // A restored URL explicitly requests these pages; ordinary visits remain one page.
  useEffect(() => {
    if (ready && !props.state.record && loadedCount < props.state.limit && hasNextPage && !isFetching && !isFetchNextPageError)
      void fetchNextPage({ cancelRefetch: false });
  }, [ready, props.state.record, props.state.limit, loadedCount, hasNextPage, isFetching, isFetchNextPageError, fetchNextPage]);
  const reload = () => { void client.invalidateQueries({ queryKey: ['frontier'], refetchType: 'active' }); };
  if (dateError) return <section className="knowledge-surface frontier"><div className="frontier-empty" role="alert"><h1>学术前沿</h1><p>{dateError}</p><button type="button" onClick={props.onOpenLibrary}>返回知识库</button></div></section>;
  const listError = list.isError && !list.data || sources.isError && Boolean(props.state.source);
  if (!asOf) return <section className="knowledge-surface frontier"><div className="frontier-empty" role={listError ? 'alert' : undefined}><h1>学术前沿</h1>{listError ? <p>资料暂时无法读取。</p> : <BrandLoading message="正在读取前沿资料…" />}{listError ? <button type="button" onClick={reload}>重新加载</button> : null}<button type="button" onClick={props.onOpenLibrary}>返回知识库</button></div></section>;
  const records = [...new Map(list.data?.pages.flatMap(item => item.records).map(record => [record.id, record]) ?? []).values()];
  const lightTopics = topics.data ?? [];
  const selectedTopic = topicDetail.data?.[0];
  const data: FrontierDataset = {
    records: [...new Map([...records, ...(overviewLanding ? [...(practice.data?.records ?? []), ...(focus.data?.records ?? [])] : []), ...referenceQueries.flatMap(query => query.data?.records ?? []), ...mediaQueries.flatMap(query => query.data ? [query.data] : [])].map(record => [record.id, record])).values()], partialRecords: true, asOf, modelStatus: 'not_requested', sources: sources.data ?? [],
    topics: selectedTopic ? [...lightTopics.filter(topic => topic.id !== selectedTopic.id), selectedTopic] : lightTopics,
    corpusOverview: overview.data,
  };
  const visibleLimit = props.state.limit;
  const loadMore = () => {
    if (list.isFetchingNextPage) return;
    if (list.isFetchNextPageError) { void list.fetchNextPage({ cancelRefetch: false }); return; }
    const nextLimit = Math.min(page?.total ?? visibleLimit, visibleLimit + 24);
    props.onStateChange({ ...props.state, limit: nextLimit });
  };
  return <FrontierPage {...props} data={data} readingDate={asOf} maxReadingDate={latestDate}
    onReadingDateChange={date => props.onStateChange({ ...props.state, asOf: date })}
    onRequestRecords={requestRecords}
    listRecords={records} focusRecords={focus.data?.records}
    pagination={{ total: page?.total ?? 0, hasNextPage: list.hasNextPage, loading: list.isFetchingNextPage, error: list.isFetchNextPageError, onLoadMore: loadMore }}
    selectedRecord={detail.data} detailLoading={Boolean(props.state.record) && detail.isPending} detailError={detail.isError} onRetryDetail={() => void detail.refetch()}
    topicLoading={Boolean(props.state.topic) && topicDetail.isPending} topicError={topicDetail.isError} onRetryTopic={() => void topicDetail.refetch()}
    statisticsError={overview.isError}
    metadataError={topics.isError || sources.isError} onRetryMetadata={() => { void topics.refetch(); void sources.refetch(); }}
    calendar={calendar.data} report={report.data?.value} reportTopic={topicKey} onReportTopicChange={setTrendTopic}
    comparisonYear={report.data?.comparisonYear ?? comparisonYear} onComparisonYearChange={setYear}
    loading={list.isPending && !listError} dataError={listError ? 'unavailable' : ''}
    calendarLoading={calendar.isPending} reportLoading={report.isPending && (topics.isPending || Boolean(topicKey))}
    calendarError={calendar.isError ? 'unavailable' : ''} reportError={report.isError ? 'unavailable' : ''} onRetry={reload}
    renderRecordInsights={props.renderRecordInsights || (id => <FrontierRecordInsights recordId={id} asOf={asOf} />)} />;
}
