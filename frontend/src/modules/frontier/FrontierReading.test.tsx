import { useState } from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { FrontierPage } from './FrontierPage';
import { testDataset } from './__fixtures__/catalog';
import { readFrontierState } from './model';
import type { FrontierCalendarData, FrontierPeriodData } from './frontierReadingTypes';

const record = { ...testDataset.records[0], id: 'care', title: '照护网络研究', research_question: '谁承担家庭之外的照护？', findings: ['邻里关系参与照护。后续长解释。'], summary: '完整的长摘要只进入论文详情。' };
const dataset = { ...testDataset, records: [record, { ...testDataset.records[1], id: 'newspaper', verification_status: 'practice_signal', research_question: '报道不应混入精选研究' }] };
const calendar: FrontierCalendarData = { as_of: '2026-10-01', year: 2026, timezone: 'Asia/Shanghai', days: [{ date: '2026-10-01', count: 1, record_ids: ['care'] }], month_precision: [{ month: '2026-09', count: 2, record_ids: [] }], issue_precision: [{ issue_id: 'issue-1', publication_year: 2026, source_id: 's1', count: 3, record_ids: [] }], conflicting_record_ids: [], future_record_ids: [], undated_record_ids: [] };
const report: FrontierPeriodData = { classification_coverage: { previous: { classified: 8, denominator: 10, publisher_keywords_available: 10, title_available: 10, uncategorized: 2 }, current: { classified: 9, denominator: 10, publisher_keywords_available: 10, title_available: 10, uncategorized: 1 } }, measurement_method: 'title_publisher_keywords_phrase_dictionary', measurement_version: 'frontier_topic_measurement_v2', cohort_current_count: 4, cohort_previous_count: 2, comparison_issue_keys: ['s1:1'], coverage_evidence_refs: ['official-contents'], coverage_scope: 'fixed_issue_sample', current_denominator: 10, previous_denominator: 10, current_window: { start: '2025-01-01', end: '2025-12-31' }, previous_window: { start: '2024-01-01', end: '2024-12-31' }, share_basis: 'fixed_issue_sample_common_sources', as_of: '2026-10-01', cohort_source_ids: ['s1'], comparability: 'complete_common_cohort', current_count: 4, previous_count: 2, current_share: .4, previous_share: .2, delta_pp: 20, direction: 'increase', date_basis: 'publication', decline_allowed: false, emerging_allowed: false, hotspot_allowed: false, persistent_allowed: false, semantic_status: 'not_evaluated', evidence_record_ids: ['care'], method_version: 'v1', timezone: 'Asia/Shanghai' };
function Harness({ comparison = report }: { comparison?: FrontierPeriodData | null }) {
  const [state, setState] = useState(readFrontierState(new URLSearchParams()));
  const [date, setDate] = useState('2026-10-01');
  return <FrontierPage data={dataset} state={state} onStateChange={setState} onOpenLibrary={vi.fn()} readingDate={date} maxReadingDate="2026-10-01" onReadingDateChange={setDate} calendar={calendar} report={comparison} reportTopic="照护研究" />;
}
afterEach(cleanup);
it('shows research questions and one finding with a representative article; returns from detail with search intact', () => {
  render(<Harness />);
  const focus = screen.getByRole('region', { name: '值得关注' });
  expect(within(focus).getByRole('heading', { name: '谁承担家庭之外的照护？' })).toBeVisible();
  expect(within(focus).getByText('邻里关系参与照护。')).toBeVisible();
  expect(within(focus).queryByText(record.summary)).not.toBeInTheDocument();
  expect(within(focus).queryByText('报道不应混入精选研究')).not.toBeInTheDocument();
  fireEvent.click(within(focus).getByRole('button', { name: '阅读 照护网络研究' }));
  expect(screen.getByText(record.summary)).toBeVisible();
  expect(screen.getByRole('complementary', { name: '学术日历与发表热力图' })).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: '返回资料列表' }));
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: '照护' } });
  fireEvent.submit(screen.getByRole('search'));
  fireEvent.click(screen.getByRole('button', { name: '查看 照护网络研究' }));
  fireEvent.click(screen.getByRole('button', { name: '返回资料列表' }));
  expect(screen.getByRole('searchbox')).toHaveValue('照护');
  expect(screen.getByRole('region', { name: '筛选结果' })).toBeVisible();
});
it('navigates reading dates, limits future days and opens the selected calendar day without changing reading cutoff', () => {
  render(<Harness />);
  expect(screen.getByRole('heading', { level: 1, name: '10月1日' })).toBeVisible();
  expect(screen.getByRole('button', { name: '后一天' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: '前一天' }));
  expect(screen.getByLabelText('阅读日期')).toHaveValue('2026-09-30');
  fireEvent.click(screen.getByRole('button', { name: '后一天' }));
  fireEvent.click(within(screen.getByRole('region', { name: '学术日历' })).getByRole('button', { name: '2026-10-01，1篇资料' }));
  const results = screen.getByRole('region', { name: '2026-10-01 发表记录' });
  expect(within(results).getByRole('button', { name: '照护网络研究' })).toBeVisible();
  expect(screen.getByLabelText('阅读日期')).toHaveValue('2026-10-01');
  fireEvent.click(screen.getByText('期刊与日期范围'));
  expect(screen.getByText(/2 篇月精度.*3 篇期号精度/)).toBeVisible();
});
it('uses report shares only for complete comparisons and never turns publication quantity into scholarly value', () => {
  const { unmount } = render(<Harness />);
  const trends = screen.getByRole('region', { name: '研究趋势' });
  expect(within(trends).getByText('20.0% → 40.0%')).toBeVisible();
  expect(within(trends).getByText(/期刊等权/)).toBeVisible();
  fireEvent.click(within(trends).getByRole('button', { name: '照护网络研究' }));
  expect(screen.getByRole('heading', { level: 1, name: '照护网络研究' })).toBeVisible();
  unmount();
  render(<Harness comparison={{ ...report, comparability: 'insufficient_coverage', delta_pp: 99 }} />);
  expect(screen.getByText('完整同期覆盖不足，暂不判断趋势。')).toBeVisible();
  expect(screen.queryByText(/99.0/)).not.toBeInTheDocument();
  expect(screen.getByText('发表数量不代表研究价值。')).toBeVisible();
});
it('keeps journal-weighted shares and their delta separate from pooled sample counts', () => {
  // Journal A: 8/10; journal B: 10/100. Their mean is 45%, while
  // the pooled share is 18/110. Previous shares are 10% in both journals.
  render(<Harness comparison={{ ...report, previous_share: .1, current_share: .45, delta_pp: 35, cohort_previous_count: 11, cohort_current_count: 18, previous_denominator: 110, current_denominator: 110, classification_coverage: { previous: { classified: 100, denominator: 110, publisher_keywords_available: 90, title_available: 110, uncategorized: 10 }, current: { classified: 105, denominator: 110, publisher_keywords_available: 100, title_available: 110, uncategorized: 5 } } }} />);
  const trends = screen.getByRole('region', { name: '研究趋势' });
  expect(within(trends).getByText('10.0% → 45.0%')).toBeVisible();
  expect(within(trends).getByText('+35.0 个百分点')).toBeVisible();
  expect(within(trends).getByText(/各刊词典命中比例的平均值 · 期刊等权/)).toBeVisible();
  expect(within(trends).getByText(/前期：命中 11 篇，样本 110 篇/)).toBeVisible();
  expect(within(trends).getByText(/当期：命中 18 篇，样本 110 篇/)).toBeVisible();
  fireEvent.click(within(trends).getByText('查看样本与测量方法'));
  expect(within(trends).getByText('未分类：前期 10 篇，当期 5 篇。')).toBeVisible();
  expect(within(trends).getByText(/frontier_topic_measurement_v2/)).toBeVisible();
});
