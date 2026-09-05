import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { StrictMode, useState } from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { FullscreenKnowledgeGraphPage, type FullscreenKnowledgeGraphState } from './FullscreenKnowledgeGraphPage'
const api = vi.hoisted(() => ({
  readCurrentKnowledgeGraphRelease: vi.fn(), readKnowledgeGraphFocusEntry: vi.fn(),
  readStructuralConnectionPage: vi.fn(), readIncidentRelationPage: vi.fn(),
  readIncidentCandidatePage: vi.fn(), searchKnowledgeGraphEntries: vi.fn(),
}))
vi.mock('./knowledgeGraphApi', () => api)
vi.mock('./ExplorationCanvas', () => ({ ExplorationCanvas: ({ onSelect }: { onSelect: (id: string) => void }) =>
  <button onClick={() => onSelect('b')}>图中选择另一概念</button> }))
const entry = (id: string) => ({ knowledgeId: id, title: id === 'a' ? '社会资本' : '互惠规范',
  reviewStatus: 'reviewed', directoryPath: [], content: '## 概念\n\n可以阅读的原文释义。', sources: [] })
let releaseNumber = 0
function Harness() {
  const [state, setState] = useState<FullscreenKnowledgeGraphState>({ releaseId: `r${releaseNumber}`, centerId: 'a' })
  return <><button onClick={() => setState((old) => ({ ...old, centerId: "b" }))}>选择下一中心</button><output aria-label="路由中心">{state.centerId}</output><FullscreenKnowledgeGraphPage state={state}
    onStateChange={(change) => setState((old) => ({ ...old, ...change }))} renderEntryLink={(id, label) => <a href={`/knowledge/${id}`}>{label}</a>} /></>
}
beforeEach(() => {
  releaseNumber++
  vi.resetAllMocks()
  api.readKnowledgeGraphFocusEntry.mockImplementation(async ({ knowledgeId }) => entry(knowledgeId))
  api.readStructuralConnectionPage.mockResolvedValue({ connections: [], nextCursor: undefined })
  api.readIncidentRelationPage.mockResolvedValue({ relations: [{ relation_id: 'ab', source_knowledge_id: 'a', target_knowledge_id: 'b', relation_type: '支持', direction: 'directed', description: '关系的依据', evidence_source_ids: [], content_version: 1 }], totalCount: 1 })
  api.readIncidentCandidatePage.mockResolvedValue({ candidates: [], totalCount: 0 })
  api.searchKnowledgeGraphEntries.mockResolvedValue({ entries: [entry('a')] })
})
afterEach(cleanup)
it('selects a node for reading without changing the network center', async () => {
  render(<Harness />)
  await screen.findByText('可以阅读的原文释义。')
  fireEvent.click(screen.getByText('图中选择另一概念'))
  await screen.findByRole('heading', { name: '互惠规范' })
  expect(screen.getByLabelText('路由中心')).toHaveTextContent('a')
  fireEvent.click(screen.getByRole('button', { name: '以此为中心' }))
  await waitFor(() => expect(screen.getByLabelText('路由中心')).toHaveTextContent('b'))
})
it('shows knowledge relation counts separately from directory connections', async () => {
  render(<Harness />)
  await screen.findByText('可以阅读的原文释义。')
  expect(screen.getByLabelText('网络统计')).toHaveTextContent('知识关系 1')
  expect(screen.getByLabelText('网络统计')).toHaveTextContent('目录连接 0')
})
it('offers an explicit undo after expansion', async () => {
  render(<Harness />)
  await screen.findByText('可以阅读的原文释义。')
  fireEvent.click(screen.getByText('图中选择另一概念'))
  await screen.findByRole('heading', { name: '互惠规范' })
  fireEvent.click(screen.getByRole('button', { name: '展开关联' }))
  await screen.findByRole('button', { name: '撤回上次展开' })
  fireEvent.click(screen.getByRole('button', { name: '撤回上次展开' }))
  expect(screen.queryByRole('button', { name: '撤回上次展开' })).not.toBeInTheDocument()
})

it('ignores a late old center response after a new center is loaded', async () => {
  let resolveOld!: (value: unknown) => void
  api.readIncidentRelationPage.mockImplementation(({ knowledgeId }) => knowledgeId === 'a'
    ? new Promise((resolve) => { resolveOld = resolve }) : Promise.resolve({ relations: [], totalCount: 0 }))
  render(<Harness />)
  await waitFor(() => expect(resolveOld).toBeTypeOf('function'))
  fireEvent.click(screen.getByText('选择下一中心'))
  await screen.findByRole('heading', { name: '互惠规范' })
  resolveOld({ relations: [], totalCount: 0 })
  await waitFor(() => expect(screen.getByLabelText('路由中心')).toHaveTextContent('b'))
  expect(screen.queryByRole('heading', { name: '社会资本' })).not.toBeInTheDocument()
})
it('loads directory pages and can undo them without turning them into knowledge relations', async () => {
  render(<Harness />)
  await screen.findByText('可以阅读的原文释义。')
  fireEvent.click(screen.getByRole('button', { name: '实践论' }))
  api.readStructuralConnectionPage.mockResolvedValueOnce({ connections: [{
    connection_id: 'dir', source_node_id: 'D2', source_title: '实践论', source_node_type: 'dimension',
    target_node_id: 'cat', target_title: '田野方法', target_node_type: 'category', connection_type: 'contains', direction: 'outbound',
  }], nextCursor: 'page2' })
  fireEvent.click(screen.getByRole('button', { name: '展开目录' }))
  await screen.findByText('田野方法')
  expect(screen.getByLabelText('网络统计')).toHaveTextContent('目录连接 1')
  expect(screen.getByLabelText('网络统计')).toHaveTextContent('知识关系 1')
  expect(screen.getByRole('button', { name: '继续展开目录' })).toBeEnabled()
  fireEvent.click(screen.getByRole('button', { name: '撤回上次展开' }))
  expect(screen.queryByText('田野方法')).not.toBeInTheDocument()
})
it('does not apply candidate responses after their layer is disabled', async () => {
  let resolveCandidates!: (value: unknown) => void
  api.readIncidentCandidatePage.mockImplementation(() => new Promise((resolve) => { resolveCandidates = resolve }))
  render(<Harness />)
  await screen.findByText('可以阅读的原文释义。')
  fireEvent.click(screen.getByRole('checkbox', { name: '查看当前概念的候选关系' }))
  await waitFor(() => expect(resolveCandidates).toBeTypeOf('function'))
  fireEvent.click(screen.getByRole('checkbox', { name: '查看当前概念的候选关系' }))
  resolveCandidates({ candidates: [{ candidate_id: 'c', source_knowledge_id: 'a', target_knowledge_id: 'b', suggested_relation_type: 'extends' }], totalCount: 1 })
  await waitFor(() => expect(screen.queryByText('正在读取候选关系…')).not.toBeInTheDocument())
  expect(screen.getByLabelText('网络统计')).not.toHaveTextContent('候选关系 1')
})

it('restores the selected node after reading, including StrictMode remounts', async () => {
  const page = render(<StrictMode><Harness /></StrictMode>)
  await screen.findByRole('heading', { name: '社会资本' })
  fireEvent.click(screen.getByText('图中选择另一概念'))
  await screen.findByRole('heading', { name: '互惠规范' })
  page.unmount()
  render(<StrictMode><Harness /></StrictMode>)
  await screen.findByRole('heading', { name: '互惠规范' })
  expect(screen.getByLabelText('路由中心')).toHaveTextContent('a')
})
