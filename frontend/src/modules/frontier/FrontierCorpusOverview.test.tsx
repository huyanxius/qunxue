import { useState } from 'react'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { FrontierPage } from './FrontierPage'
import { hasCompleteCorpusOverview } from './FrontierCorpusOverview'
import { testDataset } from './__fixtures__/catalog'
import type { FrontierCorpusOverview as Corpus, FrontierDataset } from './dataset'
import { readFrontierState } from './model'
const research = testDataset.records.filter((record) => record.verification_status !== 'practice_signal')
const ids = research.map((record) => record.id)
const corpus: Corpus = {
  asOf: '2026-10-01', status: 'ready', overview: {
    headline: '研究共同转向关系与制度的交互机制', summary: '这些研究从组织安排、行动条件和关系过程解释社会现象，而非把技术或个人特征单独作为原因。',
    sections: [{ id: 'shared_focus', title: '共同关注', statements: [{ text: '参与角色、责任分配和支持条件构成跨议题的问题线索。', evidenceRecordIds: ids.slice(0, 2) }] }, { id: 'methods', title: '研究方法的特点', statements: [{ text: '实地调查与调查数据承担不同的解释任务。', evidenceRecordIds: ids.slice(2, 4) }] }],
    scope: { stream: 'research', coverageRecordIds: ids, analyzedRecordCount: ids.length, sourceCount: 3, systematicReviewMethod: '全量逐篇分析' }, generatedBy: 'editorial', basisContentHash: 'test', sourceHashes: ids.map((recordId) => ({ recordId, contentHash: recordId })), updatedAt: '2026-10-01',
  },
  statistics: { researchCount: ids.length, practiceCount: 3, sourceDistribution: [], yearDistribution: [{ key: '2026', label: '2026', count: ids.length, recordIds: ids }], topicDistribution: [], methodDistribution: [{ key: 'field', label: '实地调查', count: 2, recordIds: ids.slice(0, 2) }], dataDistribution: [] },
}
const data: FrontierDataset = { ...testDataset, corpusOverview: corpus }
function Harness() {
  const [state, setState] = useState(readFrontierState(new URLSearchParams()))
  return <FrontierPage data={data} state={state} onStateChange={setState} onOpenLibrary={() => {}} />
}
afterEach(cleanup)
it('defaults to a substantive corpus overview, with practice separated and citations readable', () => {
  render(<Harness />)
  expect(screen.getByRole('heading', { name: '研究总览' })).toBeVisible()
  expect(screen.getByText(corpus.overview!.summary)).toBeVisible()
  expect(screen.getByRole('heading', { name: '研究方法的特点' })).toBeVisible()
  expect(screen.getByText('另收录 3 篇实践观察')).toBeVisible()
  expect(screen.queryByRole('region', { name: '最新收录' })).not.toBeInTheDocument()
  const controls = screen.getByRole('group', { name: '学术前沿视图' })
  expect(controls).toHaveClass('qx-selection-control')
  expect(within(controls).getByRole('button', { name: '研究总览' })).toHaveAttribute('aria-pressed', 'true')
  fireEvent.click(screen.getByRole('button', { name: '阅读文献 1' }))
  expect(screen.getByRole('heading', { name: research[0].title, level: 1 })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: '返回资料列表' }))
  expect(screen.getByRole('heading', { name: '研究总览' })).toBeVisible()
  fireEvent.click(within(screen.getByRole('group', { name: '学术前沿视图' })).getByRole('button', { name: '全部文献' }))
  expect(screen.getByRole('region', { name: '最新收录' })).toBeVisible()
})
it('does not label selected topic summaries or a partial/stale corpus as a complete overview', () => {
  expect(hasCompleteCorpusOverview(data)).toBe(true)
  expect(hasCompleteCorpusOverview({ ...data, corpusOverview: undefined })).toBe(false)
  expect(hasCompleteCorpusOverview({ ...data, corpusOverview: { ...corpus, status: 'stale' } })).toBe(false)
  expect(hasCompleteCorpusOverview({ ...data, corpusOverview: { ...corpus, overview: { ...corpus.overview!, scope: { ...corpus.overview!.scope, coverageRecordIds: ids.slice(0, 3) } } } })).toBe(false)
  render(<FrontierPage data={{ ...data, corpusOverview: { ...corpus, status: 'stale' } }} state={readFrontierState(new URLSearchParams())} onStateChange={() => {}} onOpenLibrary={() => {}} />)
  expect(screen.queryByRole('heading', { name: '研究总览' })).not.toBeInTheDocument()
  expect(screen.queryByText(corpus.overview!.headline)).not.toBeInTheDocument()
})

it('keeps large evidence sets expandable instead of flooding the overview with citation chips', () => {
  const enlarged = { ...corpus, overview: { ...corpus.overview!, sections: [{ id: 'methods', title: '方法综合', statements: [{ text: '全量方法分析。', evidenceRecordIds: ids }] }] } };
  render(<FrontierPage data={{ ...data, corpusOverview: enlarged }} state={readFrontierState(new URLSearchParams())} onStateChange={() => {}} onOpenLibrary={() => {}} />);
  expect(screen.getAllByRole('button', { name: /^阅读文献 / })).toHaveLength(3);
  const expand = screen.getByRole('button', { name: `查看这条结论的全部 ${ids.length} 篇依据` });
  expect(expand).toHaveTextContent(`查看${ids.length}篇依据`);
  fireEvent.click(expand);
  expect(within(screen.getByRole('article')).getByRole('button', { name: research.at(-1)!.title })).toBeVisible();
  expect(screen.getByRole('navigation', { name: '总览章节' })).toBeVisible();
});

it('does not present unclassified records or missing extraction fields as research characteristics', () => {
  const missing = { key: 'unknown', label: '未知数据字段', count: 244, recordIds: ids };
  const stats = { ...corpus.statistics, topicDistribution: [{ key: 'uncategorized', label: '待归类的研究线索', count: 112, recordIds: ids }], methodDistribution: [missing], dataDistribution: [missing] };
  render(<FrontierPage data={{ ...data, corpusOverview: { ...corpus, statistics: stats } }} state={readFrontierState(new URLSearchParams())} onStateChange={() => {}} onOpenLibrary={() => {}} />);
  expect(screen.queryByText('未知数据字段')).not.toBeInTheDocument();
  expect(screen.queryByText('待归类的研究线索')).not.toBeInTheDocument();
  expect(screen.getByRole('heading', { name: '发表年份' })).toBeVisible();
});

it('numbers cited papers by first appearance while preserving the full coverage set and sorts years chronologically', () => {
  const onChange = vi.fn();
  const overview = { ...corpus.overview!, sections: [
    { id: 'shared_focus', title: '共同关注', statements: [{ text: '首先引用较后的馆藏记录。', evidenceRecordIds: [ids.at(-1)!, ids[2], ids[0]] }] },
    { id: 'methods', title: '研究方法', statements: [{ text: '随后复用同一篇依据。', evidenceRecordIds: [ids[2]] }] },
  ] };
  const stats = { ...corpus.statistics, yearDistribution: [2025, 2026, 2024, 2023, 2022].map((year) => ({ key: String(year), label: String(year), count: 1, recordIds: [ids[0]] })) };
  render(<FrontierPage data={{ ...data, corpusOverview: { ...corpus, overview, statistics: stats } }} state={readFrontierState(new URLSearchParams())} onStateChange={onChange} onOpenLibrary={() => {}} />);
  fireEvent.click(screen.getByRole('button', { name: '阅读文献 1' }));
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ record: ids.at(-1) }));
  expect(screen.getAllByRole('button', { name: '阅读文献 2' })).toHaveLength(2);
  expect(screen.getByRole('heading', { name: '研究总览' })).toBeInTheDocument();
  const years = screen.getByRole('heading', { name: '发表年份' }).closest('section')!;
  expect([...years.querySelectorAll('summary > span')].map((element) => element.textContent)).toEqual(['2022', '2023', '2024', '2025', '2026']);
});
