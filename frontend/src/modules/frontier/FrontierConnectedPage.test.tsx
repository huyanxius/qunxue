import { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { FrontierConnectedPage, FrontierPreviewProvider } from './FrontierConnectedPage';
import { readFrontierState, writeFrontierState } from './model';
import { testDataset } from './__fixtures__/catalog';
import * as api from './frontierApi';
import { readRecordInsights } from './readingInsightsApi';
import type { FrontierCalendarData, FrontierPeriodData } from './frontierReadingTypes';
vi.mock('./frontierApi', () => ({ readFrontierSummaries: vi.fn(), readFrontierSources: vi.fn(), readFrontierTopics: vi.fn(), readFrontierRecord: vi.fn(), readFrontierOverview: vi.fn(), readFrontierCalendar: vi.fn(), readFrontierPeriod: vi.fn() }));
vi.mock('./readingInsightsApi', () => ({ readRecordInsights: vi.fn() }));
const calendar: FrontierCalendarData = { as_of: '2026-10-01', year: 2026, timezone: 'Asia/Shanghai', days: [], month_precision: [], issue_precision: [], conflicting_record_ids: [], future_record_ids: [], undated_record_ids: [] };
const dataset = { ...testDataset, topics: [{ id: 'youth-research', key: 'youth', title: '青年研究', stream: 'research' as const, recordIds: testDataset.records.map(r => r.id), sourceIds: [], sourceDistribution: {}, summary: '', counts: { total: 1, dated: 1, undated: 0, days30: 1, days90: 1, days180: 1, previous90: 0 }, trendStatus: 'insufficient_evidence' as const, trendSignals: [], growthBaseline: null, reasons: [] }] };
const report: FrontierPeriodData = { classification_coverage: { previous: { classified: 8, denominator: 10, publisher_keywords_available: 10, title_available: 10, uncategorized: 2 }, current: { classified: 9, denominator: 10, publisher_keywords_available: 10, title_available: 10, uncategorized: 1 } }, measurement_method: 'title_publisher_keywords_phrase_dictionary', measurement_version: 'frontier_topic_measurement_v2', cohort_current_count: 4, cohort_previous_count: 2, comparison_issue_keys: ['s1:1'], coverage_evidence_refs: ['official-contents'], coverage_scope: 'fixed_issue_sample', current_denominator: 10, previous_denominator: 10, current_window: { start: '2025-01-01', end: '2025-12-31' }, previous_window: { start: '2024-01-01', end: '2024-12-31' }, share_basis: 'fixed_issue_sample', as_of: '2026-10-01', cohort_source_ids: [], comparability: 'complete_common_cohort', current_count: 4, previous_count: 2, current_share: .4, previous_share: .2, delta_pp: 20, direction: 'increase', date_basis: 'publication', decline_allowed: false, emerging_allowed: false, hotspot_allowed: false, persistent_allowed: false, semantic_status: 'not_evaluated', evidence_record_ids: [], method_version: 'v1', timezone: 'Asia/Shanghai' };
const rows = Array.from({ length: 24 }, (_, index) => ({ ...testDataset.records[0], id: `record-${index}`, title: `研究 ${index}` }));
const page = { records: rows, total: 50, offset: 0, nextOffset: 24, asOf: '2026-10-01' };
function Harness({ initial = '' }: { initial?: string }) {
  const [state, setState] = useState(readFrontierState(new URLSearchParams(initial)));
  return <><FrontierConnectedPage state={state} onStateChange={setState} onOpenLibrary={vi.fn()} /><output data-testid="reading-url">{writeFrontierState(state).toString()}</output></>;
}
function mount(initial = '', client = new QueryClient()) {
  return { client, ...render(<QueryClientProvider client={client}><Harness initial={initial} /></QueryClientProvider>) };
}
function listCalls() { return vi.mocked(api.readFrontierSummaries).mock.calls.filter(([filters]) => !filters.limit); }
afterEach(cleanup);
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.readFrontierSummaries).mockImplementation(async (filters, offset) => ({ ...page, records: filters.limit ? [] : rows, offset: offset ?? 0, nextOffset: filters.limit ? null : 24, asOf: filters.asOf || page.asOf }));
  vi.mocked(api.readFrontierSources).mockResolvedValue([{ id: 'journal', name: '测试期刊', status: 'ready', lastSuccessAt: null }]);
  vi.mocked(api.readFrontierTopics).mockResolvedValue(dataset.topics);
  vi.mocked(api.readFrontierRecord).mockImplementation(async id => ({ ...rows[0], id }));
  vi.mocked(api.readFrontierCalendar).mockResolvedValue(calendar);
  vi.mocked(api.readFrontierPeriod).mockResolvedValue(report);
  vi.mocked(api.readFrontierOverview).mockResolvedValue({ asOf: page.asOf, status: 'not_configured', overview: null, statistics: { researchCount: 48, practiceCount: 2, sourceDistribution: [], yearDistribution: [], topicDistribution: [], methodDistribution: [], dataDistribution: [] } });
  vi.mocked(readRecordInsights).mockImplementation(async id => ({
    priority: { recordId: id, title: rows[0].title, recordVersion: 1, snapshotHash: 'test', readinessLevel: 'metadata_only', supportedFields: [], missingFields: [], sourceEvidence: [], academic: { status: 'unassessed', value: null, ruleVersion: 'draft-v1', criteria: [] }, limitations: [] },
    links: { recordId: id, recordVersion: 1, snapshotHash: 'test', release: null, state: 'no_release', matches: [], limitations: [] },
  }));
});
it('loads one summary page first and preserves six visible cards while background panels are pending', async () => {
  let resolve!: (value: typeof page) => void;
  vi.mocked(api.readFrontierSummaries).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  vi.mocked(api.readFrontierTopics).mockImplementation(() => new Promise(() => {}));
  vi.mocked(api.readFrontierCalendar).mockImplementation(() => new Promise(() => {}));
  vi.mocked(api.readFrontierOverview).mockImplementation(() => new Promise(() => {}));
  mount();
  expect(screen.getByText('正在读取前沿资料…')).toBeVisible();
  expect(api.readFrontierTopics).not.toHaveBeenCalled();
  expect(api.readFrontierCalendar).not.toHaveBeenCalled();
  await act(async () => resolve(page));
  const list = await screen.findByRole('region', { name: '最新研究' });
  expect(within(list).getAllByRole('article')).toHaveLength(6);
  expect(listCalls()).toHaveLength(1);
  expect(within(list).getByRole('button', { name: '再看 24 条资料' })).toBeVisible();
  expect(api.readFrontierRecord).not.toHaveBeenCalled();
  expect(readRecordInsights).not.toHaveBeenCalled();
  expect(screen.getByRole('complementary', { name: '学术日历与发表热力图' })).toBeVisible();
});
it('loads pages only on demand, deduplicates overlaps, and restores list position and cached detail', async () => {
  vi.mocked(api.readFrontierSummaries).mockResolvedValueOnce(page).mockResolvedValue({ ...page, records: [rows[23], { ...rows[0], id: 'record-24', title: '研究 24' }], offset: 24, nextOffset: null, total: 25 });
  mount('section=papers');
  const list = await screen.findByRole('region', { name: '最新收录' });
  fireEvent.click(within(list).getByRole('button', { name: '再看 24 条资料' }));
  await waitFor(() => expect(within(list).getAllByRole('article')).toHaveLength(25));
  expect(api.readFrontierSummaries).toHaveBeenLastCalledWith(expect.objectContaining({ asOf: page.asOf }), 24, expect.any(AbortSignal));
  const scroll = document.querySelector('.frontier-scroll')!;
  fireEvent.scroll(scroll, { target: { scrollTop: 540 } });
  fireEvent.click(screen.getByRole('button', { name: '查看 研究 24' }));
  await screen.findByText('暂无可用知识发布');
  fireEvent.click(screen.getByRole('button', { name: '返回资料列表' }));
  expect(scroll.scrollTop).toBe(540);
  expect(listCalls()).toHaveLength(2);
  fireEvent.click(screen.getByRole('button', { name: '查看 研究 24' }));
  await screen.findByText('暂无可用知识发布');
  expect(api.readFrontierRecord).toHaveBeenCalledTimes(1);
  expect(readRecordInsights).toHaveBeenCalledTimes(1);
});
it('retains loaded rows after a pagination failure and retries the same page', async () => {
  vi.mocked(api.readFrontierSummaries).mockResolvedValueOnce(page).mockRejectedValueOnce(new Error('failure')).mockResolvedValueOnce({ ...page, records: [{ ...rows[0], id: 'next', title: '下一页' }], offset: 24, nextOffset: null });
  mount('section=papers');
  await screen.findByRole('region', { name: '最新收录' });
  fireEvent.click(screen.getByRole('button', { name: '再看 24 条资料' }));
  await screen.findByText('后续资料暂时无法读取，已加载内容仍可阅读。');
  expect(screen.getByRole('button', { name: '查看 研究 0' })).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: '重试加载更多' }));
  await screen.findByRole('button', { name: '查看 下一页' });
  expect(listCalls().slice(1).map(call => call[1])).toEqual([24, 24]);
});
it('uses server search, stream, source and topic filters without local summary filtering', async () => {
  mount('section=papers');
  await screen.findByRole('region', { name: '最新收录' });
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: '完整正文命中' } }); fireEvent.submit(screen.getByRole('search'));
  await waitFor(() => expect(api.readFrontierSummaries).toHaveBeenLastCalledWith(expect.objectContaining({ query: '完整正文命中' }), 0, expect.any(AbortSignal)));
  await screen.findByRole('button', { name: '查看 研究 0' });
  fireEvent.click(screen.getByRole('button', { name: '学术研究' }));
  await waitFor(() => expect(api.readFrontierSummaries).toHaveBeenLastCalledWith(expect.objectContaining({ stream: 'research' }), 0, expect.any(AbortSignal)));
  await screen.findByLabelText('筛选来源');
  fireEvent.change(screen.getByLabelText('筛选来源'), { target: { value: 'journal' } });
  await waitFor(() => expect(api.readFrontierSummaries).toHaveBeenLastCalledWith(expect.objectContaining({ sourceId: 'journal' }), 0, expect.any(AbortSignal)));
  await screen.findByLabelText('筛选议题');
  fireEvent.change(screen.getByLabelText('筛选议题'), { target: { value: 'youth-research' } });
  await waitFor(() => expect(api.readFrontierSummaries).toHaveBeenLastCalledWith(expect.objectContaining({ topicId: 'youth-research' }), 0, expect.any(AbortSignal)));
  await waitFor(() => expect(api.readFrontierTopics).toHaveBeenCalledWith(page.asOf, 'youth-research', expect.any(AbortSignal)));
});
it('resolves a historical deep link outside the loaded summary page', async () => {
  mount('as_of=2026-09-28&record=off-page');
  await screen.findByText('暂无可用知识发布');
  expect(api.readFrontierRecord).toHaveBeenCalledWith('off-page', '2026-09-28', expect.any(AbortSignal));
  expect(listCalls()).toHaveLength(1);
});
it.each(['2026-02-30', 'not-a-date', '', '9999-12-31'])('preserves and rejects invalid or future reading date %s', date => {
  mount(new URLSearchParams({ as_of: date }).toString());
  expect(screen.getByRole('alert')).toHaveTextContent(/阅读日期/);
  expect(api.readFrontierSummaries).not.toHaveBeenCalled();
  expect(new URLSearchParams(screen.getByTestId('reading-url').textContent!).get('as_of')).toBe(date);
});
it('serializes historical dates, hides stale results after failure and retries the same query', async () => {
  mount('q=养老&section=papers');
  await screen.findByRole('region', { name: '筛选结果' });
  vi.mocked(api.readFrontierSummaries).mockRejectedValueOnce(new Error('private backend error'));
  fireEvent.change(screen.getByLabelText('阅读日期'), { target: { value: '2026-09-28' } });
  await screen.findByText('这个日期的资料暂时无法读取。');
  expect(screen.queryByRole('button', { name: '查看 研究 0' })).not.toBeInTheDocument();
  expect(screen.queryByText('private backend error')).not.toBeInTheDocument();
  expect(new URLSearchParams(screen.getByTestId('reading-url').textContent!).get('as_of')).toBe('2026-09-28');
  fireEvent.click(screen.getByRole('button', { name: '重新加载' }));
  await screen.findByRole('region', { name: '筛选结果' });
  expect(screen.getByRole('searchbox')).toHaveValue('养老');
  expect(api.readFrontierSummaries).toHaveBeenLastCalledWith(expect.objectContaining({ asOf: '2026-09-28', query: '养老' }), 0, expect.any(AbortSignal));
});
it('cancels superseded searches and does not paint their late responses', async () => {
  let resolve!: (value: typeof page) => void;
  let oldSignal: AbortSignal | undefined;
  vi.mocked(api.readFrontierSummaries).mockResolvedValueOnce(page).mockImplementationOnce((_filters, _offset, signal) => { oldSignal = signal; return new Promise(done => { resolve = done; }); }).mockResolvedValueOnce({ ...page, records: [{ ...rows[0], title: '新查询' }], total: 1, nextOffset: null });
  mount('section=papers');
  await screen.findByRole('region', { name: '最新收录' });
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: '旧查询' } }); fireEvent.submit(screen.getByRole('search'));
  await waitFor(() => expect(oldSignal).toBeDefined());
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: '新查询' } }); fireEvent.submit(screen.getByRole('search'));
  await screen.findByRole('button', { name: '查看 新查询' });
  expect(oldSignal?.aborted).toBe(true);
  await act(async () => resolve(page));
  expect(screen.queryByRole('button', { name: '查看 研究 0' })).not.toBeInTheDocument();
});
it('keeps calendar and list usable when automatic trend loading fails', async () => {
  vi.mocked(api.readFrontierPeriod).mockRejectedValue(new Error('period unavailable'));
  mount();
  await screen.findByText(/趋势暂时无法读取/);
  const rail = screen.getByRole('complementary', { name: '学术日历与发表热力图' });
  await waitFor(() => expect(within(rail).getByRole('button', { name: '2026-10-01，0篇资料' })).toBeEnabled());
  expect(screen.getByRole('button', { name: '查看 研究 0' })).toBeVisible();
});
it('retains annual comparison fallback without a duplicate report request', async () => {
  vi.mocked(api.readFrontierPeriod).mockResolvedValueOnce({ ...report, comparability: 'insufficient_coverage', current_share: null, previous_share: null, delta_pp: null }).mockResolvedValue(report);
  mount();
  await screen.findByText('20.0% → 40.0%');
  expect(screen.getByLabelText('比较时期')).toHaveValue('2024');
  expect(api.readFrontierPeriod).toHaveBeenCalledTimes(2);
});
it('keeps explicit previews offline without requiring a QueryClient', () => {
  render(<FrontierPreviewProvider data={testDataset}><FrontierConnectedPage state={readFrontierState(new URLSearchParams())} onStateChange={vi.fn()} onOpenLibrary={vi.fn()} /></FrontierPreviewProvider>);
  expect(screen.getByRole('region', { name: '最新研究' })).toBeVisible();
  expect(api.readFrontierSummaries).not.toHaveBeenCalled();
});

it('restores explicitly requested page limits and scroll after a route remount', async () => {
  vi.mocked(api.readFrontierSummaries).mockImplementation(async (filters, offset = 0) => ({ ...page, records: Array.from({ length: 24 }, (_, index) => ({ ...rows[0], id: `record-${offset + index}`, title: `研究 ${offset + index}` })), offset, nextOffset: offset < 24 ? 24 : null, asOf: filters.asOf || page.asOf }));
  const client = new QueryClient();
  const first = mount('section=papers&limit=30&q=restore', client);
  await waitFor(() => expect(within(screen.getByRole('region', { name: '筛选结果' })).getAllByRole('article')).toHaveLength(30));
  fireEvent.scroll(document.querySelector('.frontier-scroll')!, { target: { scrollTop: 680 } });
  first.unmount();
  mount('section=papers&limit=30&q=restore', client);
  await screen.findByRole('button', { name: '查看 研究 29' });
  expect(document.querySelector('.frontier-scroll')!.scrollTop).toBe(680);
  expect(listCalls()).toHaveLength(2);
});
it('loads off-page calendar labels as summaries only after choosing the day', async () => {
  vi.mocked(api.readFrontierCalendar).mockResolvedValue({ ...calendar, days: [{ date: '2026-10-01', count: 1, record_ids: ['calendar-paper'] }] });
  vi.mocked(api.readFrontierSummaries).mockImplementation(async (filters, offset = 0) => ({ ...page, offset, nextOffset: null, records: filters.recordIds ? [{ ...rows[0], id: 'calendar-paper', title: '日历中的文献' }] : filters.limit ? [] : rows }));
  mount();
  const [day] = await screen.findAllByRole('button', { name: '2026-10-01，1篇资料' }, { timeout: 5000 });
  expect(vi.mocked(api.readFrontierSummaries).mock.calls.some(([filters]) => filters.recordIds)).toBe(false);
  fireEvent.click(day);
  await screen.findByRole('button', { name: '日历中的文献' });
  expect(api.readFrontierRecord).not.toHaveBeenCalled();
  expect(api.readFrontierSummaries).toHaveBeenCalledWith(expect.objectContaining({ recordIds: ['calendar-paper'], asOf: page.asOf }), 0, expect.any(AbortSignal));
});
it('hydrates selected-topic citation titles and only fetches full records flagged with figures', async () => {
  const topic = { ...dataset.topics[0], researchBrief: { headline: '有图表的议题', development: { text: '证据综述', evidenceRecordIds: ['with-figure', 'citation-only'] }, consensus: [], differences: [], methods: [], researchImplication: null, priorityReads: [{ recordId: 'citation-only', reason: '阅读原因' }], evidenceRecordIds: ['with-figure', 'citation-only'], generatedBy: 'test', basisContentHash: 'test', updatedAt: page.asOf } };
  vi.mocked(api.readFrontierTopics).mockResolvedValue([topic]);
  vi.mocked(api.readFrontierSummaries).mockImplementation(async (filters, offset = 0) => ({ ...page, offset, nextOffset: null, records: filters.recordIds ? filters.recordIds.map(id => ({ ...rows[0], id, title: id === 'citation-only' ? '引文标题' : '图表文献', has_media: id === 'with-figure' })) : rows }));
  vi.mocked(api.readFrontierRecord).mockImplementation(async id => ({ ...rows[0], id, media: [{ url: 'https://example.com/figure.png', source_url: 'https://example.com/paper', caption: '研究图表', kind: 'figure' }] }));
  mount('topic=youth-research&view=analysis');
  await screen.findByRole('button', { name: '引文标题' });
  await waitFor(() => expect(api.readFrontierRecord).toHaveBeenCalledWith('with-figure', page.asOf, expect.any(AbortSignal)));
  expect(api.readFrontierRecord).toHaveBeenCalledTimes(1);
  expect(readRecordInsights).not.toHaveBeenCalled();
});
