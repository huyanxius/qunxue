import { useEffect, useState } from 'react';
import type { FrontierCalendarData } from './frontierReadingTypes';
import type { FrontierDataset } from './dataset';

export function FrontierCalendar({ data, calendar, readingDate, onOpenRecord, loading, error, onRetry }: {
  data: FrontierDataset; calendar?: FrontierCalendarData | null; readingDate: string; onOpenRecord: (id: string) => void; loading?: boolean; error?: string; onRetry?: () => void;
}) {
  const [month, setMonth] = useState(readingDate.slice(0, 7));
  const [selected, setSelected] = useState('');
  useEffect(() => { setMonth(readingDate.slice(0, 7)); setSelected(''); }, [readingDate]);
  const counts = new Map((calendar?.days ?? []).map(day => [day.date, day]));
  const year = Number(month.slice(0, 4));
  const m = Number(month.slice(5, 7));
  const daysInMonth = new Date(Date.UTC(year, m, 0)).getUTCDate();
  const offset = (new Date(Date.UTC(year, m - 1, 1)).getUTCDay() + 6) % 7;
  const iso = (day: number) => `${month}-${String(day).padStart(2, '0')}`;
  const heatYear = Number(readingDate.slice(0, 4));
  const heatStart = Date.UTC(heatYear, 0, 1);
  const heatDays = Math.round((Date.UTC(heatYear + 1, 0, 1) - heatStart) / 86400000);
  const moveMonth = (delta: number) => { setMonth(new Date(Date.UTC(year, m - 1 + delta, 1)).toISOString().slice(0, 7)); setSelected(''); };
  const openDay = (date: string) => { setMonth(date.slice(0, 7)); setSelected(date); };
  const evidence = (ids: string[]) => ids.flatMap(id => { const record = data.records.find(item => item.id === id); return record && record.verification_status !== 'review_queue' ? [record] : []; }).map(record => <button type="button" key={record.id} onClick={() => onOpenRecord(record.id)}>{record.title}</button>);
  const dayButton = (date: string, heat = false) => { const count = counts.get(date)?.count ?? 0; if (heat && (!calendar || count === 0 || date > readingDate)) return <span key={date} data-level="0" title={`${date} · 暂无资料`} aria-hidden="true" />; return <button key={date} type="button" aria-label={`${date}，${count}篇资料`} aria-pressed={selected === date} disabled={!calendar || loading || date > readingDate} data-level={count === 0 ? 0 : count < 3 ? 1 : count < 8 ? 2 : 3} title={`${date} · ${count} 篇资料`} onClick={() => openDay(date)}>{heat ? null : Number(date.slice(8))}</button>; };
  return <aside className="frontier-calendar-rail" aria-label="学术日历与发表热力图">
    <section aria-labelledby="frontier-calendar-title">
      <header className="frontier-reading-section"><h2 id="frontier-calendar-title">学术日历</h2><span>发表日期</span></header>
      <div className="frontier-calendar-month"><button type="button" aria-label="上个月" disabled={year !== heatYear || m === 1} onClick={() => moveMonth(-1)}>‹</button><strong>{year}年{m}月</strong><button type="button" aria-label="下个月" disabled={month >= readingDate.slice(0, 7)} onClick={() => moveMonth(1)}>›</button></div>
      {loading ? <p role="status">正在读取日历…</p> : error ? <p role="alert">日历暂时无法读取。{onRetry ? <button type="button" onClick={onRetry}>重试</button> : null}</p> : !calendar ? <p className="frontier-reading-status">日历暂无数据。</p> : null}
      <div className="frontier-calendar-grid"><div className="frontier-calendar-week" aria-hidden="true">{'一二三四五六日'.split('').map(day => <span key={day}>{day}</span>)}</div><div className="frontier-calendar-days">{Array.from({ length: offset }, (_, i) => <span key={`blank-${i}`} />)}{Array.from({ length: daysInMonth }, (_, i) => dayButton(iso(i + 1)))}</div></div>
      {selected ? <section className="frontier-calendar-results" aria-label={`${selected} 发表记录`}><h3>{selected} 发表记录</h3>{evidence(counts.get(selected)?.record_ids ?? []).length ? evidence(counts.get(selected)?.record_ids ?? []) : <p>当天暂无可读资料。</p>}</section> : null}
    </section>
    <section aria-labelledby="frontier-heat-title"><header className="frontier-reading-section"><h2 id="frontier-heat-title">发表热力图</h2><span>{heatYear}年</span></header><div className="frontier-heat-months" aria-hidden="true"><span>1月</span><span>4月</span><span>7月</span><span>10月</span></div><div className="frontier-heatmap">{Array.from({ length: (new Date(heatStart).getUTCDay() + 6) % 7 }, (_, i) => <span key={`pad-${i}`} />)}{Array.from({ length: heatDays }, (_, i) => dayButton(new Date(heatStart + i * 86400000).toISOString().slice(0, 10), true))}</div><p className="frontier-reading-status">深浅表示已收录资料的发表数量。</p></section>
    {calendar ? <details className="frontier-calendar-precision"><summary>期刊与日期范围</summary><p>{calendar.month_precision.reduce((n, item) => n + item.count, 0)} 篇月精度 · {calendar.issue_precision.reduce((n, item) => n + item.count, 0)} 篇期号精度，未分配到具体日。</p>{calendar.month_precision.map(item => <details key={item.month}><summary>{item.month} · {item.count} 篇</summary>{evidence(item.record_ids)}</details>)}{calendar.issue_precision.map(item => <details key={item.issue_id}><summary>{data.sources.find(source => source.id === item.source_id)?.name || item.source_id} · {item.issue_id} · {item.count} 篇</summary>{evidence(item.record_ids)}</details>)}{calendar.undated_record_ids.length ? <p>{calendar.undated_record_ids.length} 篇日期未明。</p> : null}</details> : null}
  </aside>;
}
