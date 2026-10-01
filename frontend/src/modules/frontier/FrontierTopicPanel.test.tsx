import { useState } from 'react'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { FrontierPage } from './FrontierPage'
import type { FrontierTopic } from './dataset'
import { readFrontierState, writeFrontierState, type FrontierState } from './model'
import { testDataset } from './__fixtures__/catalog'

const papers = testDataset.records.slice(0, 2)
const topic: FrontierTopic = {
  id: 'care', key: 'care', title: '照护关系', stream: 'research', recordIds: papers.map((record) => record.id), sourceIds: ['a', 'b'], sourceDistribution: {}, summary: '不应出现在正文中的采集过程',
  counts: { total: 2, dated: 1, undated: 1, days30: 1, days90: 1, days180: 1, previous90: 0 }, trendStatus: 'insufficient_evidence', trendSignals: [], growthBaseline: null, reasons: [],
  researchBrief: { headline: '照护角色在互动中形成', development: { text: '两项研究把照护参与放进组织关系中理解。', evidenceRecordIds: [papers[0].id] }, consensus: [{ text: '参与角色受到制度安排影响。', evidenceRecordIds: papers.map((paper) => paper.id) }], differences: [{ text: '技术参与和家属探访考察不同互动情境。', evidenceRecordIds: [papers[1].id] }], methods: [{ text: '其中一项研究采用机构实地调查。', evidenceRecordIds: [papers[1].id] }], researchImplication: { text: '区分参与资格、责任与行动条件。', evidenceRecordIds: [papers[0].id] }, priorityReads: [{ recordId: papers[0].id, reason: '先理解组织安排如何进入照护关系。' }], evidenceRecordIds: papers.map((paper) => paper.id), generatedBy: 'test', basisContentHash: 'test', updatedAt: '2026-10-01' },
  monthlySeries: [{ month: '2026-08', recordCount: 1, datedRecordIds: [papers[0].id], sourceIds: ['a'], coverageComplete: false, observationBasis: 'sample' }],
}
function Harness({ initial }: { initial?: Partial<FrontierState> }) {
  const [state, setState] = useState({ ...readFrontierState(new URLSearchParams()), ...initial })
  return <><FrontierPage data={{ ...testDataset, topics: [topic] }} state={state} onStateChange={setState} onOpenLibrary={() => {}} /><output data-testid="url-state">{writeFrontierState(state).toString()}</output></>
}
afterEach(cleanup)

it('opens a full analysis pane from a dense topic row and closes without duplicating the application navigation', () => {
  render(<Harness />)
  fireEvent.click(screen.getByRole('button', { name: '研究议题' }))
  const row = screen.getByRole('button', { name: '分析 照护关系' })
  expect(within(row).getByText(topic.researchBrief!.development!.text)).toBeVisible()
  expect(within(row).getByText('2026-08—2026-08')).toBeVisible()
  expect(within(row).queryByText(/近90天/)).not.toBeInTheDocument()
  expect(document.querySelector('.frontier .knowledge-library__shader')).not.toBeInTheDocument()
  fireEvent.click(row)
  const panel = screen.getByRole('region', { name: '照护关系分析' })
  expect(within(panel).getByRole('heading', { name: '照护角色在互动中形成', level: 1 })).toBeVisible()
  expect(within(panel).getByRole('tab', { name: '概览' })).toHaveAttribute('aria-selected', 'true')
  expect(within(panel).getByRole('img', { name: '照护关系文献收录变化' })).toBeVisible()
  expect(screen.queryByRole('textbox', { name: /AI/ })).not.toBeInTheDocument()
  expect(screen.queryByText(topic.summary)).not.toBeInTheDocument()
  fireEvent.click(within(panel).getByRole('button', { name: '关闭议题分析' }))
  expect(screen.queryByRole('region', { name: '照护关系分析' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '分析 照护关系' }))
  expect(screen.getAllByRole('region', { name: '照护关系分析' })).toHaveLength(1)
})

it('switches analysis tabs with the keyboard and preserves analysis state across citation reading', () => {
  render(<Harness initial={{ topic: topic.id }} />)
  const overview = screen.getByRole('tab', { name: '概览' })
  fireEvent.keyDown(overview, { key: 'ArrowRight' })
  expect(screen.getByRole('tab', { name: '综合解读' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByTestId('url-state')).toHaveTextContent('view=analysis')
  const content = screen.getByRole('tabpanel')
  expect(within(content).getByRole('heading', { name: '差异与讨论' })).toBeVisible()
  expect(within(content).getByText('先理解组织安排如何进入照护关系。')).toBeVisible()
  fireEvent.click(within(content).getAllByRole('button', { name: '阅读文献 1' })[0])
  expect(screen.getByRole('heading', { name: papers[0].title, level: 1 })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: '返回资料列表' }))
  expect(screen.getByRole('tab', { name: '综合解读' })).toHaveAttribute('aria-selected', 'true')
  fireEvent.keyDown(screen.getByRole('tab', { name: '综合解读' }), { key: 'End' })
  expect(screen.getByRole('tab', { name: '文献' })).toHaveAttribute('aria-selected', 'true')
  expect(within(screen.getByRole('region', { name: '筛选结果' })).getAllByRole('article')).toHaveLength(2)
})

it('restores the selected view from a direct URL and rejects unknown view values', () => {
  const state = readFrontierState(new URLSearchParams('scope=frontier&topic=care&view=analysis'))
  expect(state.topicView).toBe('analysis')
  expect(readFrontierState(writeFrontierState(state))).toEqual(state)
  expect(readFrontierState(new URLSearchParams('view=missing')).topicView).toBeUndefined()
})
