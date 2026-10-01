import { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { readRecordInsights } from './readingInsightsApi';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { FrontierConnectedPage } from './FrontierConnectedPage';
import { readFrontierState, writeFrontierState } from './model';
import { testDataset } from './__fixtures__/catalog';
import { readFrontierDataset, readFrontierCalendar, readFrontierPeriod } from './frontierApi';
import type { FrontierCalendarData, FrontierPeriodData } from './frontierReadingTypes';
vi.mock('./frontierApi', () => ({ readFrontierDataset: vi.fn(), readFrontierCalendar: vi.fn(), readFrontierPeriod: vi.fn() }));
vi.mock('./readingInsightsApi', () => ({ readRecordInsights: vi.fn() }));
const calendar: FrontierCalendarData = { as_of: '2026-10-01', year: 2026, timezone: 'Asia/Shanghai', days: [], month_precision: [], issue_precision: [], conflicting_record_ids: [], future_record_ids: [], undated_record_ids: [] };
const dataset = { ...testDataset, topics: [{ id: 'youth-research', key: 'youth', title: '青年研究', stream: 'research' as const, recordIds: testDataset.records.map(r => r.id), sourceIds: [], sourceDistribution: {}, summary: '', counts: { total: 1, dated: 1, undated: 0, days30: 1, days90: 1, days180: 1, previous90: 0 }, trendStatus: 'insufficient_evidence' as const, trendSignals: [], growthBaseline: null, reasons: [] }] };
const report: FrontierPeriodData = { classification_coverage: { previous: { classified: 8, denominator: 10, publisher_keywords_available: 10, title_available: 10, uncategorized: 2 }, current: { classified: 9, denominator: 10, publisher_keywords_available: 10, title_available: 10, uncategorized: 1 } }, measurement_method: 'title_publisher_keywords_phrase_dictionary', measurement_version: 'frontier_topic_measurement_v2', cohort_current_count: 4, cohort_previous_count: 2, comparison_issue_keys: ['s1:1'], coverage_evidence_refs: ['official-contents'], coverage_scope: 'fixed_issue_sample', current_denominator: 10, previous_denominator: 10, current_window: { start: '2025-01-01', end: '2025-12-31' }, previous_window: { start: '2024-01-01', end: '2024-12-31' }, share_basis: 'fixed_issue_sample', as_of: '2026-10-01', cohort_source_ids: [], comparability: 'complete_common_cohort', current_count: 4, previous_count: 2, current_share: .4, previous_share: .2, delta_pp: 20, direction: 'increase', date_basis: 'publication', decline_allowed: false, emerging_allowed: false, hotspot_allowed: false, persistent_allowed: false, semantic_status: 'not_evaluated', evidence_record_ids: [], method_version: 'v1', timezone: 'Asia/Shanghai' };
function Harness() { const [state, setState] = useState(readFrontierState(new URLSearchParams())); const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false } } })); return <QueryClientProvider client={client}><FrontierConnectedPage state={state} onStateChange={setState} onOpenLibrary={vi.fn()} /></QueryClientProvider>; }
afterEach(cleanup);
function UrlHarness({ initial = '' }: { initial?: string }) {
  const [state, setState] = useState(readFrontierState(new URLSearchParams(initial)));
  return <><FrontierConnectedPage state={state} onStateChange={setState} onOpenLibrary={vi.fn()} /><output data-testid="reading-url">{writeFrontierState(state).toString()}</output></>;
}
it('serializes a selected historical date and rebuilds the same page after refresh', async () => {
  const mounted = render(<UrlHarness initial="q=养老" />);
  await screen.findByRole('heading', { name: '10月1日', level: 1 });
  fireEvent.change(screen.getByLabelText('阅读日期'), { target: { value: '2026-09-28' } });
  await waitFor(() => expect(readFrontierDataset).toHaveBeenLastCalledWith('2026-09-28'));
  const serialized = screen.getByTestId('reading-url').textContent!;
  expect(new URLSearchParams(serialized).get('as_of')).toBe('2026-09-28');
  expect(new URLSearchParams(serialized).get('q')).toBe('养老');
  mounted.unmount();
  vi.mocked(readFrontierDataset).mockClear();
  render(<UrlHarness initial={serialized} />);
  await screen.findByRole('heading', { name: '9月28日', level: 1 });
  expect(screen.getByLabelText('阅读日期')).toHaveValue('2026-09-28');
  expect(readFrontierDataset).toHaveBeenCalledTimes(1);
  expect(readFrontierDataset).toHaveBeenLastCalledWith('2026-09-28');
});
it('requests the controlled historical date again when browser history updates props', async () => {
  const props = { onStateChange: vi.fn(), onOpenLibrary: vi.fn() };
  const state = (date: string) => readFrontierState(new URLSearchParams(`as_of=${date}&q=养老`));
  const mounted = render(<FrontierConnectedPage {...props} state={state('2026-09-28')} />);
  await screen.findByRole('heading', { name: '9月28日', level: 1 });
  mounted.rerender(<FrontierConnectedPage {...props} state={state('2026-09-27')} />);
  await waitFor(() => expect(readFrontierDataset).toHaveBeenLastCalledWith('2026-09-27'));
  await screen.findByRole('heading', { name: '9月27日', level: 1 });
  expect(readFrontierCalendar).toHaveBeenLastCalledWith('2026-09-27');
  await waitFor(() => expect(readFrontierPeriod).toHaveBeenLastCalledWith('youth', '2026-09-27', 2025));
  mounted.rerender(<FrontierConnectedPage {...props} state={state('2026-09-28')} />);
  await waitFor(() => expect(readFrontierDataset).toHaveBeenLastCalledWith('2026-09-28'));
  expect(props.onStateChange).not.toHaveBeenCalled();
});
it.each(['2026-02-30', 'not-a-date', '', '9999-12-31'])('reports invalid or future URL date %s without loading another date', date => {
  const params = new URLSearchParams({ as_of: date });
  render(<UrlHarness initial={params.toString()} />);
  expect(screen.getByRole('alert')).toHaveTextContent(/阅读日期/);
  expect(readFrontierDataset).not.toHaveBeenCalled();
  expect(readFrontierCalendar).not.toHaveBeenCalled();
  expect(readFrontierPeriod).not.toHaveBeenCalled();
  expect(new URLSearchParams(screen.getByTestId('reading-url').textContent!).get('as_of')).toBe(date);
});
it('hides an already loaded historical page when history moves to an impossible date', async () => {
  const props = { onStateChange: vi.fn(), onOpenLibrary: vi.fn() };
  const mounted = render(<FrontierConnectedPage {...props} state={readFrontierState(new URLSearchParams('as_of=2026-09-28'))} />);
  await screen.findByRole('heading', { name: '9月28日', level: 1 });
  vi.mocked(readFrontierDataset).mockClear();
  mounted.rerender(<FrontierConnectedPage {...props} state={readFrontierState(new URLSearchParams('as_of=2026-02-30'))} />);
  expect(screen.getByRole('alert')).toHaveTextContent('阅读日期无效');
  expect(screen.queryByRole('heading', { name: '9月28日' })).not.toBeInTheDocument();
  expect(readFrontierDataset).not.toHaveBeenCalled();
});
beforeEach(() => { vi.resetAllMocks(); vi.mocked(readFrontierDataset).mockImplementation(async date => ({ ...dataset, asOf: date || dataset.asOf })); vi.mocked(readFrontierCalendar).mockResolvedValue(calendar); vi.mocked(readFrontierPeriod).mockResolvedValue(report); });
it('uses the latest complete year and changes to the requested comparison without mixing news', async () => {
  render(<Harness />);
  await screen.findByRole('heading', { name: '10月1日', level: 1 });
  await waitFor(() => expect(screen.getByText('20.0% → 40.0%')).toBeVisible());
  expect(readFrontierPeriod).toHaveBeenCalledWith('youth', '2026-10-01', 2025);
  fireEvent.change(screen.getByLabelText('比较时期'), { target: { value: '2024' } });
  await waitFor(() => expect(readFrontierPeriod).toHaveBeenLastCalledWith('youth', '2026-10-01', 2024));
});
it('hides stale records after a failed date change, retries and keeps the query', async () => {
  render(<Harness />);
  await screen.findByRole('heading', { name: '10月1日', level: 1 });
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: '养老' } });
  fireEvent.submit(screen.getByRole('search'));
  vi.mocked(readFrontierDataset).mockRejectedValueOnce(new Error('private backend error'));
  fireEvent.click(screen.getByRole('button', { name: '前一天' }));
  await screen.findByText('这个日期的资料暂时无法读取。');
  expect(screen.queryByText('private backend error')).not.toBeInTheDocument();
  expect(screen.queryByRole('region', { name: '筛选结果' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '重新加载' }));
  await screen.findByRole('region', { name: '筛选结果' });
  expect(screen.getByRole('searchbox')).toHaveValue('养老');
  expect(screen.getByLabelText('阅读日期')).toHaveValue('2026-09-30');
});
it('keeps calendar available when the period request fails', async () => {
  vi.mocked(readFrontierPeriod).mockRejectedValue(new Error('period unavailable'));
  render(<Harness />);
  await screen.findByText(/趋势暂时无法读取/);
  const rail = screen.getByRole('complementary', { name: '学术日历与发表热力图' });
  await waitFor(() => expect(within(rail).getByRole('button', { name: '2026-10-01，0篇资料' })).toBeEnabled());
  expect(screen.queryByText('日历暂时无法读取。')).not.toBeInTheDocument();
});

it('selects the newest available complete cohort when the latest year has insufficient coverage', async () => {
  vi.mocked(readFrontierPeriod).mockResolvedValueOnce({ ...report, comparability: 'insufficient_coverage', current_share: null, previous_share: null, delta_pp: null }).mockResolvedValue(report);
  render(<Harness />);
  await screen.findByText('20.0% → 40.0%');
  expect(screen.getByLabelText('比较时期')).toHaveValue('2024');
});

it('loads real insight components only for the selected article, retries failures and returns to the same scroll position', async () => {
  const id = dataset.records[0].id;
  vi.mocked(readRecordInsights).mockRejectedValueOnce(new Error('unavailable')).mockResolvedValue({
    priority: { recordId: id, title: dataset.records[0].title, recordVersion: 1, snapshotHash: 'test', readinessLevel: 'metadata_only', supportedFields: [], missingFields: [], sourceEvidence: [], academic: { status: 'unassessed', value: null, ruleVersion: 'draft-v1', criteria: [] }, limitations: [] },
    links: { recordId: id, recordVersion: 1, snapshotHash: 'test', release: null, state: 'no_release', matches: [], limitations: [] },
  });
  render(<Harness />);
  await screen.findByRole('region', { name: '最新研究' });
  expect(readRecordInsights).not.toHaveBeenCalled();
  const scroll = document.querySelector('.frontier-scroll')!;
  fireEvent.scroll(scroll, { target: { scrollTop: 540 } });
  fireEvent.click(screen.getByRole('button', { name: `查看 ${dataset.records[0].title}` }));
  await screen.findByText(/阅读依据暂时无法读取/);
  fireEvent.click(within(screen.getByRole('alert')).getByRole('button', { name: '重试' }));
  await screen.findByText('学术价值未评估');
  expect(screen.getByText('暂无可用知识发布')).toBeVisible();
  expect(readRecordInsights).toHaveBeenLastCalledWith(id, '2026-10-01');
  fireEvent.click(screen.getByRole('button', { name: '返回资料列表' }));
  expect(scroll.scrollTop).toBe(540);
});
