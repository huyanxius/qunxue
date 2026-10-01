import { createContext, useContext, useEffect, useState, type PropsWithChildren } from 'react';
import { FrontierPage, type FrontierPageProps } from './FrontierPage';
import type { FrontierDataset } from './dataset';
import { readFrontierDataset, readFrontierPeriod, readFrontierCalendar } from './frontierApi';
import type { FrontierCalendarData, FrontierPeriodData } from './frontierReadingTypes';
import { FrontierRecordInsights } from './FrontierRecordInsights';
const PreviewContext = createContext<FrontierDataset | null>(null);

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
  const [data, setData] = useState<FrontierDataset | null>(preview);
  const [dataLoading, setDataLoading] = useState(!preview);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [maxReadingDate, setMaxReadingDate] = useState('');
  const readingDate = props.state.asOf;
  const [calendar, setCalendar] = useState<FrontierCalendarData | null>(null);
  const [report, setReport] = useState<FrontierPeriodData | null>(null);
  const [calendarError, setCalendarError] = useState('');
  const [reportError, setReportError] = useState('');
  const [calendarLoading, setCalendarLoading] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [trendTopic, setTrendTopic] = useState('');
  const [year, setYear] = useState<number | null | undefined>();
  const latestDate = maxReadingDate || shanghaiToday();
  const dateError = readingDateError(readingDate, latestDate);
  const asOf = readingDate || data?.asOf || '';
  const researchTopics = data?.topics.filter(topic => topic.stream === 'research' && topic.key !== 'uncategorized') ?? [];
  const selectedTopic = researchTopics.find(topic => topic.id === props.state.topic);
  const topicKey = trendTopic || selectedTopic?.key || researchTopics[0]?.key || '';
  const comparisonYear = year === null ? null : Math.min(year ?? Number(asOf.slice(0, 4)) - 1, Number(asOf.slice(0, 4)) - 1);
  const reload = () => setRetry(current => current + 1);
  useEffect(() => { setYear(undefined); }, [readingDate]);
  useEffect(() => {
    if (dateError) return;
    if (preview) { setData(preview); setDataLoading(false); return; }
    let cancelled = false;
    setError(''); setDataLoading(true);
    readFrontierDataset(readingDate).then(result => {
      if (!cancelled) { setData(result); if (readingDate === undefined) setMaxReadingDate(result.asOf); setDataLoading(false); }
    }).catch(() => { if (!cancelled) { setError('unavailable'); setDataLoading(false); } });
    return () => { cancelled = true; };
  }, [preview, retry, readingDate, dateError]);
  useEffect(() => {
    setCalendar(null); setCalendarError(''); setCalendarLoading(false);
    if (preview || !asOf || dateError) return;
    let cancelled = false;
    setCalendarLoading(true);
    readFrontierCalendar(asOf).then(value => { if (!cancelled) { setCalendar(value); setCalendarLoading(false); } })
      .catch(() => { if (!cancelled) { setCalendarError('unavailable'); setCalendarLoading(false); } });
    return () => { cancelled = true; };
  }, [preview, asOf, retry, dateError]);
  useEffect(() => {
    setReport(null); setReportError(''); setReportLoading(false);
    if (preview || !asOf || !topicKey || dateError) return;
    let cancelled = false;
    setReportLoading(true);
    const loadReport = async () => {
      const value = await readFrontierPeriod(topicKey, asOf, comparisonYear ?? undefined);
      const complete = (candidate: FrontierPeriodData) => candidate.comparability === 'complete_common_cohort' && candidate.current_share !== null && candidate.previous_share !== null && candidate.delta_pp !== null;
      if (!cancelled && year === undefined && comparisonYear && !complete(value)) {
        try {
          const previous = await readFrontierPeriod(topicKey, asOf, comparisonYear - 1);
          if (!cancelled && complete(previous)) { setYear(comparisonYear - 1); return; }
        } catch { /* Keep the latest report's explicit coverage status. */ }
      }
      if (!cancelled) { setReport(value); setReportLoading(false); }
    };
    loadReport()
      .catch(() => { if (!cancelled) { setReportError('unavailable'); setReportLoading(false); } });
    return () => { cancelled = true; };
  }, [preview, asOf, topicKey, comparisonYear, year, retry, dateError]);
  if (dateError) return <section className="knowledge-surface frontier"><div className="frontier-empty" role="alert"><h1>学术前沿</h1><p>{dateError}</p><button type="button" onClick={props.onOpenLibrary}>返回知识库</button></div></section>;
  if (!data) return <section className="knowledge-surface frontier"><div className="frontier-empty" role={error ? 'alert' : 'status'}><h1>学术前沿</h1><p>{error ? '资料暂时无法读取。' : '正在读取前沿资料…'}</p>{error ? <button type="button" onClick={reload}>重新加载</button> : null}<button type="button" onClick={props.onOpenLibrary}>返回知识库</button></div></section>;
  const insights = props.renderRecordInsights || (preview ? undefined : (id: string) => <FrontierRecordInsights recordId={id} asOf={asOf} />);
  return <FrontierPage {...props} data={data} readingDate={asOf} maxReadingDate={latestDate} onReadingDateChange={preview ? undefined : date => { props.onStateChange({ ...props.state, asOf: date }); }} calendar={calendar} report={report} reportTopic={topicKey} onReportTopicChange={setTrendTopic} comparisonYear={comparisonYear} onComparisonYearChange={setYear} loading={dataLoading || (!error && data.asOf !== asOf)} dataError={error} calendarLoading={calendarLoading} reportLoading={reportLoading} calendarError={calendarError} reportError={reportError} onRetry={reload} renderRecordInsights={insights} />;
}
