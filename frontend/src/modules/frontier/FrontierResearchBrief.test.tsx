import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { FrontierResearchBrief, FrontierTopicTimeline } from './FrontierResearchBrief'
import type { FrontierTopic } from './dataset'
import { testDataset } from './__fixtures__/catalog'

const records = testDataset.records.slice(0, 2)
const topic: FrontierTopic = {
  id: 'topic', key: 'test', title: '研究议题', stream: 'research', recordIds: records.map((record) => record.id), sourceIds: ['a', 'b'], sourceDistribution: {}, summary: '',
  counts: { total: 2, dated: 2, undated: 0, days30: 1, days90: 2, days180: 2, previous90: 0 }, trendStatus: 'insufficient_evidence', trendSignals: [], growthBaseline: null, reasons: [],
  researchBrief: {
    headline: '制度安排如何改变参与方式', development: { text: '不同场景的参与受制度安排影响。', evidenceRecordIds: [records[0].id] },
    consensus: [], differences: [{ text: '两项研究考察的组织场景不同。', evidenceRecordIds: records.map((record) => record.id) }],
    methods: [{ text: '其中一篇采用实地调查。', evidenceRecordIds: [records[1].id] }],
    researchImplication: { text: '区分参与机会与参与结果。', evidenceRecordIds: records.map((record) => record.id) },
    priorityReads: [{ recordId: records[1].id, reason: '先了解实地调查如何组织材料。' }], evidenceRecordIds: records.map((record) => record.id), generatedBy: 'test', basisContentHash: 'test', updatedAt: '2026-10-01',
  },
}
afterEach(cleanup)
describe('research-first brief', () => {
  it('shows discovery and significance before paper listings, with only real citation relationships', () => {
    const openRecord = vi.fn()
    render(<FrontierResearchBrief topic={topic} records={records} featured onOpenRecord={openRecord} onOpenTopic={vi.fn()} />)
    expect(screen.getByRole('heading', { name: '制度安排如何改变参与方式' })).toBeVisible()
    expect(screen.getByText('区分参与机会与参与结果。')).toBeVisible()
    const matrix = screen.getByRole('table')
    expect(within(matrix).queryByRole('columnheader', { name: '共识' })).not.toBeInTheDocument()
    expect(within(matrix).getAllByRole('cell', { name: '引用本篇' })).toHaveLength(6)
    expect(within(matrix).getAllByRole('cell', { name: '未引用' })).toHaveLength(2)
    fireEvent.click(within(matrix).getByRole('button', { name: records[0].title }))
    expect(openRecord).toHaveBeenCalledWith(records[0].id)
  })
  it('makes disagreements, methods and reasoned reading order visible without inventing consensus', () => {
    render(<FrontierResearchBrief topic={topic} records={records} expanded onOpenRecord={vi.fn()} onOpenTopic={vi.fn()} />)
    expect(screen.getByRole('heading', { name: '差异与讨论' })).toBeVisible()
    expect(screen.getByText('先了解实地调查如何组织材料。')).toBeVisible()
    expect(screen.queryByRole('heading', { name: '共同发现' })).not.toBeInTheDocument()
    expect(screen.queryByText('待生成')).not.toBeInTheDocument()
  })
  it('never draws a trend graphic without dated observations', () => {
    const { rerender } = render(<FrontierTopicTimeline topic={topic} />)
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    rerender(<FrontierTopicTimeline topic={{ ...topic, monthlySeries: [
      { month: '2026-08', recordCount: 1, datedRecordIds: [records[0].id], sourceIds: ['a'], coverageComplete: false, observationBasis: 'sample' },
      { month: '2026-09', recordCount: 1, datedRecordIds: [records[1].id], sourceIds: ['b'], coverageComplete: false, observationBasis: 'sample' },
    ] }} />)
    expect(screen.getByRole('img', { name: '研究议题已收录论文月度分布' })).toBeVisible()
    expect(screen.getByText('2026-08：已收录1篇；2026-09：已收录1篇')).toBeInTheDocument()
  })
})

it('compares only complete issues from the same journal, never pooling unlike source denominators', () => {
  const issue = (id: string, sourceId: string, complete = true) => ({ issueId: id, label: id, sourceId, publicationMonth: id, candidateCount: 10, readableCount: 10, includedCount: 10, denominator: 10, topicRecordCount: 2, share: .2, coverageComplete: complete, evidenceRecordIds: [], denominatorRecordIds: [], issueUrl: 'https://example.org', comparisonGroup: sourceId });
  const { rerender } = render(<FrontierTopicTimeline topic={{ ...topic, issueSeries: [issue('2026-01', 'a'), issue('2026-02', 'b')] }} />);
  expect(screen.queryByRole('img')).not.toBeInTheDocument();
  rerender(<FrontierTopicTimeline topic={{ ...topic, issueSeries: [issue('2026-01', 'a'), issue('2026-02', 'a', false)] }} />);
  expect(screen.queryByRole('img')).not.toBeInTheDocument();
  rerender(<FrontierTopicTimeline topic={{ ...topic, issueSeries: [issue('2026-01', 'a'), issue('2026-02', 'a'), issue('2026-03', 'b')] }} />);
  expect(screen.getByRole('img', { name: '研究议题同刊完整期次的议题占比' })).toBeVisible();
  expect(screen.queryByText('2026-03')).not.toBeInTheDocument();
});

it('shows a source figure only from the featured topic’s cited papers, without image placeholders', () => {
  const sourceMedia = { url: 'https://publisher.example/chart.png', caption: '案例分析图', source_url: 'https://publisher.example/article', kind: 'chart' as const };
  const unrelated = { ...records[0], id: 'unrelated', media: [sourceMedia] };
  const { rerender } = render(<FrontierResearchBrief topic={topic} records={[...records, unrelated]} featured onOpenRecord={vi.fn()} onOpenTopic={vi.fn()} />);
  expect(screen.queryByRole('img')).not.toBeInTheDocument();
  rerender(<FrontierResearchBrief topic={topic} records={[{ ...records[0], media: [sourceMedia] }, records[1], unrelated]} featured onOpenRecord={vi.fn()} onOpenTopic={vi.fn()} />);
  expect(screen.getAllByRole('img')).toHaveLength(1);
  expect(screen.getByRole('img', { name: '案例分析图' })).toHaveAttribute('src', sourceMedia.url);
});
