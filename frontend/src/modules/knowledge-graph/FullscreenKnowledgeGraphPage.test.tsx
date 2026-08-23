import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useCallback, useState } from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const cytoscapeMock = vi.hoisted(() => vi.fn())
const readIncidentCandidatePage = vi.hoisted(() => vi.fn())
const readIncidentRelationPage = vi.hoisted(() => vi.fn())
const readKnowledgeGraphFocusEntry = vi.hoisted(() => vi.fn())
const readStructuralConnectionPage = vi.hoisted(() => vi.fn())
const searchKnowledgeGraphEntries = vi.hoisted(() => vi.fn())

vi.mock('cytoscape', () => ({ default: cytoscapeMock }))
vi.mock('./knowledgeGraphApi', () => ({
  readIncidentCandidatePage,
  readIncidentRelationPage,
  readKnowledgeGraphFocusEntry,
  readStructuralConnectionPage,
  searchKnowledgeGraphEntries,
}))

import {
  FullscreenKnowledgeGraphPage,
  type FullscreenKnowledgeGraphState,
} from './FullscreenKnowledgeGraphPage'

const entries = {
  center: {
    knowledgeId: 'D1:C001:E001', title: '社会资本', reviewStatus: 'reviewed',
    directoryPath: [
      { nodeId: 'D1', nodeType: 'dimension' as const, title: '本体论' },
      { nodeId: 'D1:C001', nodeType: 'category' as const, title: '社会关系' },
    ],
  },
  second: {
    knowledgeId: 'D1:C001:E002', title: '关系资源', reviewStatus: 'reviewed',
    directoryPath: [
      { nodeId: 'D1', nodeType: 'dimension' as const, title: '本体论' },
      { nodeId: 'D1:C001', nodeType: 'category' as const, title: '社会关系' },
    ],
  },
  child: {
    knowledgeId: 'D1:C001:E001:H001', title: '强关系', reviewStatus: 'pending',
    directoryPath: [],
  },
  reviewed: {
    knowledgeId: 'D2:C002:E009', title: '互惠规范', reviewStatus: 'reviewed',
    directoryPath: [],
  },
  candidateOnly: {
    knowledgeId: 'D4:V154', title: '数据殖民主义', reviewStatus: 'pending',
    directoryPath: [],
  },
}

const pathConnection = {
  connection_id: 'structure:d1-category', connection_kind: 'structure',
  source_node_id: 'D1', source_node_type: 'dimension', source_title: '本体论',
  target_node_id: 'D1:C001', target_node_type: 'category', target_title: '社会关系',
  connection_type: 'contains', direction: 'outbound',
}
const centerConnection = {
  connection_id: 'structure:category-center', connection_kind: 'structure',
  source_node_id: 'D1:C001', source_node_type: 'category', source_title: '社会关系',
  target_node_id: 'D1:C001:E001', target_node_type: 'entry', target_title: '社会资本',
  connection_type: 'contains', direction: 'outbound',
}
const siblingConnection = {
  ...centerConnection,
  connection_id: 'structure:category-sibling',
  target_node_id: 'D1:C001:E002', target_title: '关系资源',
}
const childConnection = {
  ...centerConnection,
  connection_id: 'structure:center-child',
  source_node_id: 'D1:C001:E001', source_node_type: 'entry', source_title: '社会资本',
  target_node_id: 'D1:C001:E001:H001', target_title: '强关系',
}

const cores: Array<{
  fit: ReturnType<typeof vi.fn>
  layout: ReturnType<typeof vi.fn>
  on: ReturnType<typeof vi.fn>
}> = []

function renderPage(path = '/knowledge/graph?knowledge_release_id=release-a') {
  const params = new URL(path, 'https://qunxue.local').searchParams
  const initialState: FullscreenKnowledgeGraphState = {
    releaseId: params.get('knowledge_release_id') ?? undefined,
    query: params.get('query') ?? undefined,
    centerId: params.get('center') ?? undefined,
    pendingEnabled: params.get('pending') === '1',
  }

  function Harness() {
    const [state, setState] = useState(initialState)
    const updateState = useCallback((changes: Partial<FullscreenKnowledgeGraphState>) => {
      setState((current) => ({ ...current, ...changes }))
    }, [])
    return (
      <FullscreenKnowledgeGraphPage
        state={state}
        onStateChange={updateState}
        entryHref={(knowledgeId) => `/knowledge/${encodeURIComponent(knowledgeId)}`}
      />
    )
  }

  return render(<Harness />)
}

beforeEach(() => {
  vi.clearAllMocks()
  cores.length = 0
  cytoscapeMock.mockReset()
  cytoscapeMock.mockImplementation(() => {
    const elements = {
      boundingBox: vi.fn(() => ({ x1: 0, x2: 100, y1: 0, y2: 100 })),
      removeClass: vi.fn(),
    }
    const core = {
      container: vi.fn(() => ({ clientWidth: 1000, clientHeight: 700 })),
      center: vi.fn(),
      destroy: vi.fn(),
      elements: vi.fn(() => elements),
      fit: vi.fn(),
      getElementById: vi.fn(() => ({
        closedNeighborhood: vi.fn(() => ({ kind: 'neighborhood' })),
        empty: vi.fn(() => false),
        nonempty: vi.fn(() => true),
        position: vi.fn(() => ({ x: 50, y: 50 })),
      })),
      layout: vi.fn(() => ({ run: vi.fn() })),
      maxZoom: vi.fn(() => 3.2),
      minZoom: vi.fn(() => 0.16),
      nodes: vi.fn(() => ({ addClass: vi.fn(), removeClass: vi.fn() })),
      one: vi.fn(),
      edges: vi.fn(() => ({ addClass: vi.fn(), removeClass: vi.fn() })),
      on: vi.fn(),
      resize: vi.fn(),
      viewport: vi.fn(),
    }
    cores.push(core)
    return core
  })
  searchKnowledgeGraphEntries.mockResolvedValue({
    entries: [entries.center, entries.second],
    nextCursor: undefined,
  })
  readKnowledgeGraphFocusEntry.mockImplementation(async ({ knowledgeId }) => (
    Object.values(entries).find((entry) => entry.knowledgeId === knowledgeId)
      ?? { ...entries.reviewed, knowledgeId, title: knowledgeId }
  ))
  readStructuralConnectionPage.mockImplementation(async ({ sourceNodeId }) => {
    if (sourceNodeId === 'D1') return { connections: [pathConnection] }
    if (sourceNodeId === 'D1:C001') {
      return { connections: [centerConnection, siblingConnection], nextCursor: 'siblings-2' }
    }
    return { connections: [childConnection], nextCursor: 'children-2' }
  })
  readIncidentRelationPage.mockResolvedValue({
    relations: [{
      relation_id: 'relation:reviewed',
      source_knowledge_id: entries.center.knowledgeId,
      target_knowledge_id: entries.reviewed.knowledgeId,
      relation_type: 'supports', direction: 'outbound',
      description: '社会资本支持互惠规范。', evidence_source_ids: ['source:1'],
      evidence_grade: 'reviewed', content_version: 1, review_status: 'reviewed',
    }],
    nextCursor: 'relations-2', totalCount: 2,
  })
  readIncidentCandidatePage.mockResolvedValue({
    candidates: [{
      candidate_id: 'candidate:pending',
      source_knowledge_id: entries.center.knowledgeId,
      target_knowledge_id: entries.candidateOnly.knowledgeId,
      suggested_relation_type: 'extends', direction: 'outbound',
      evidence_excerpt: '社会资本扩展了关系资源讨论。',
      evidence_locator: '本体论/社会关系.md#content-line-9',
      evidence_source_id: 'source:1', source_content_version: 1,
      target_content_version: 1, producer: 'explicit-title-trigger',
      producer_config_version: 'explicit-title-trigger-v1', score: 1,
      trigger_reason: 'trigger=扩展了', review_status: 'pending', review_record_id: null,
    }],
    nextCursor: 'candidates-2', totalCount: 2,
  })
})

afterEach(cleanup)

it('does not run an internal transition in the fullscreen graph', () => {
  renderPage()

  const options = cytoscapeMock.mock.calls[0]?.[0]
  expect(options.layout.animate).toBe(false)
  for (const selector of ['node', 'edge']) {
    expect(options.style.find((rule: { selector: string }) => rule.selector === selector))
      .toEqual(expect.objectContaining({
        style: expect.objectContaining({ 'transition-duration': 0 }),
      }))
  }
})

it('opens a dimension node as one bounded directory page', async () => {
  readStructuralConnectionPage.mockResolvedValueOnce({
    connections: [pathConnection],
    nextCursor: 'dimension-2',
  }).mockResolvedValueOnce({
    connections: [],
    nextCursor: undefined,
  })
  renderPage()

  const nodeTap = cores[0]?.on.mock.calls.find(
    ([event, selector]) => event === 'tap' && selector === 'node',
  )?.[2]
  nodeTap?.({
    target: {
      data: (key: string) => key === 'nodeType' ? 'dimension' : undefined,
      id: () => 'D1',
    },
  })

  await waitFor(() => expect(readStructuralConnectionPage).toHaveBeenCalledWith({
    releaseId: 'release-a',
    sourceNodeId: 'D1',
  }))
  fireEvent.click(screen.getByRole('button', { name: '加载更多目录节点' }))
  await waitFor(() => expect(readStructuralConnectionPage).toHaveBeenCalledWith({
    releaseId: 'release-a',
    sourceNodeId: 'D1',
    cursor: 'dimension-2',
  }))
})

it('searches a real entry and builds a bounded structural and reviewed neighborhood', async () => {
  renderPage()

  expect(cytoscapeMock.mock.calls[0]?.[0].elements.filter(
    (element: { data: { source?: string } }) => !element.data.source,
  )).toHaveLength(7)
  const initialOptions = cytoscapeMock.mock.calls[0]?.[0]
  expect(initialOptions.style).toEqual(expect.arrayContaining([
    expect.objectContaining({
      selector: 'node',
      style: expect.objectContaining({
        shape: 'ellipse',
        width: 10,
        height: 10,
        label: 'data(label)',
        'text-valign': 'top',
        'min-zoomed-font-size': 8,
      }),
    }),
    expect.objectContaining({
      selector: 'node.node--dimension',
      style: expect.objectContaining({ width: 16, height: 16 }),
    }),
  ]))
  expect(screen.getByRole('button', { name: '适应画布' })).toBeVisible()
  expect(screen.getByRole('button', { name: '重新布局' })).toBeVisible()
  expect(readIncidentCandidatePage).not.toHaveBeenCalled()
  expect(readStructuralConnectionPage).not.toHaveBeenCalledWith({
    releaseId: 'release-a', sourceNodeId: 'D1',
  })

  fireEvent.change(screen.getByRole('searchbox', { name: '搜索真实条目' }), {
    target: { value: '社会' },
  })
  fireEvent.click(screen.getByRole('button', { name: '搜索' }))
  fireEvent.click(await screen.findByRole('button', { name: /社会资本/ }))

  expect(await screen.findByRole('heading', { name: '社会资本' })).toBeVisible()
  expect(screen.queryByText('没有找到匹配的真实条目。')).not.toBeInTheDocument()
  expect(within(screen.getByLabelText('当前中心')).getByText('本体论 / 社会关系')).toBeVisible()
  expect(screen.getByRole('button', { name: '加载更多直接子级' })).toBeVisible()
  expect(screen.getByRole('button', { name: '加载更多同父条目' })).toBeVisible()
  expect(screen.getByRole('button', { name: '加载更多正式关系' })).toBeVisible()
  expect(readIncidentCandidatePage).not.toHaveBeenCalled()

  const latestElements = cytoscapeMock.mock.calls.at(-1)?.[0].elements
  expect(latestElements.map((element: { data: { id: string } }) => element.data.id)).toEqual(
    expect.arrayContaining([
      'D1', 'D1:C001', entries.center.knowledgeId, entries.second.knowledgeId,
      entries.child.knowledgeId, entries.reviewed.knowledgeId, 'relation:reviewed',
    ]),
  )
  const focusedOptions = cytoscapeMock.mock.calls.at(-1)?.[0]
  expect(focusedOptions.layout).toEqual(expect.objectContaining({ name: 'cose' }))
  expect(focusedOptions.style).toEqual(expect.arrayContaining([
    expect.objectContaining({
      selector: 'node.node--focus',
      style: expect.objectContaining({ width: 16, height: 16 }),
    }),
    expect.objectContaining({
      selector: 'edge.edge--candidate',
      style: expect.objectContaining({ 'line-style': 'dashed' }),
    }),
    expect.objectContaining({
      selector: 'edge',
      style: expect.objectContaining({ 'curve-style': 'straight' }),
    }),
  ]))

  const edgeTap = cores.at(-1)?.on.mock.calls.find(
    ([event, selector]) => event === 'tap' && selector === 'edge',
  )?.[2]
  const renderCountBeforeEdgeSelection = cytoscapeMock.mock.calls.length
  edgeTap?.({
    target: {
      id: () => 'structure:path:D1:D1:C001',
      select: vi.fn(),
    },
  })
  expect(await screen.findByLabelText('知识结构说明')).toHaveTextContent(
    '仅表达目录与层级结构，不是正式语义关系',
  )
  expect(cytoscapeMock).toHaveBeenCalledTimes(renderCountBeforeEdgeSelection)
})

it('loads each local layer one bounded page at a time and labels pending as non-factual', async () => {
  renderPage()
  fireEvent.change(screen.getByRole('searchbox', { name: '搜索真实条目' }), {
    target: { value: '社会' },
  })
  fireEvent.click(screen.getByRole('button', { name: '搜索' }))
  fireEvent.click(await screen.findByRole('button', { name: /社会资本/ }))
  await screen.findByRole('heading', { name: '社会资本' })

  fireEvent.click(screen.getByRole('button', { name: '加载更多直接子级' }))
  await waitFor(() => expect(readStructuralConnectionPage).toHaveBeenCalledWith({
    releaseId: 'release-a', sourceNodeId: entries.center.knowledgeId, cursor: 'children-2',
  }))
  fireEvent.click(screen.getByRole('button', { name: '加载更多同父条目' }))
  await waitFor(() => expect(readStructuralConnectionPage).toHaveBeenCalledWith({
    releaseId: 'release-a', sourceNodeId: 'D1:C001', cursor: 'siblings-2',
  }))
  fireEvent.click(screen.getByRole('button', { name: '加载更多正式关系' }))
  await waitFor(() => expect(readIncidentRelationPage).toHaveBeenCalledWith({
    releaseId: 'release-a', knowledgeId: entries.center.knowledgeId, cursor: 'relations-2',
  }))

  fireEvent.click(screen.getByRole('button', { name: '显示待审核候选' }))
  expect(await screen.findByText('待审核候选、非知识事实；不会计入 reviewed 数量。')).toBeVisible()
  await waitFor(() => {
    const pendingElements = cytoscapeMock.mock.calls.at(-1)?.[0].elements
    expect(pendingElements).toEqual(expect.arrayContaining([
      expect.objectContaining({ data: expect.objectContaining({ id: entries.candidateOnly.knowledgeId }) }),
      expect.objectContaining({ data: expect.objectContaining({ id: 'candidate:pending' }) }),
    ]))
  })
  expect(screen.getByRole('button', { name: '加载更多待审核候选' })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: '加载更多待审核候选' }))
  await waitFor(() => expect(readIncidentCandidatePage).toHaveBeenCalledWith({
    releaseId: 'release-a', knowledgeId: entries.center.knowledgeId, cursor: 'candidates-2',
  }))

  const edgeTap = cores.at(-1)?.on.mock.calls.find(
    ([event, selector]) => event === 'tap' && selector === 'edge',
  )?.[2]
  edgeTap?.({ target: { id: () => 'candidate:pending', select: vi.fn() } })
  const evidence = await screen.findByLabelText('待审核候选证据')
  expect(within(evidence).getByText('社会资本扩展了关系资源讨论。')).toBeVisible()
  expect(within(evidence).getByText(/确定性规则命中，不是校准置信度/)).toBeVisible()

  fireEvent.click(screen.getByRole('button', { name: '隐藏待审核候选' }))
  await waitFor(() => {
    const hiddenElements = cytoscapeMock.mock.calls.at(-1)?.[0].elements
    const ids = hiddenElements.map((element: { data: { id: string } }) => element.data.id)
    expect(ids).not.toContain('candidate:pending')
    expect(ids).not.toContain(entries.candidateOnly.knowledgeId)
    expect(ids).toEqual(expect.arrayContaining([
      'D1', 'D1:C001', entries.center.knowledgeId, entries.second.knowledgeId,
      entries.child.knowledgeId, entries.reviewed.knowledgeId, 'relation:reviewed',
    ]))
  })
})

it('ignores an older center response after the user selects another result', async () => {
  let releaseOldPath: ((value: { connections: (typeof pathConnection)[] }) => void) | undefined
  const oldPath = new Promise<{ connections: (typeof pathConnection)[] }>((resolve) => {
    releaseOldPath = resolve
  })
  let firstDimensionRead = true
  readStructuralConnectionPage.mockImplementation(async ({ sourceNodeId }) => {
    if (sourceNodeId === 'D1' && firstDimensionRead) {
      firstDimensionRead = false
      return oldPath
    }
    if (sourceNodeId === 'D1') return { connections: [pathConnection] }
    if (sourceNodeId === 'D1:C001') return { connections: [centerConnection, siblingConnection] }
    return { connections: [] }
  })

  renderPage()
  fireEvent.change(screen.getByRole('searchbox', { name: '搜索真实条目' }), {
    target: { value: '社会' },
  })
  fireEvent.click(screen.getByRole('button', { name: '搜索' }))
  fireEvent.click(await screen.findByRole('button', { name: /社会资本/ }))
  fireEvent.click(screen.getByRole('button', { name: /关系资源/ }))

  expect(await screen.findByRole('heading', { name: '关系资源' })).toBeVisible()
  releaseOldPath?.({ connections: [pathConnection] })
  await waitFor(() => {
    const focused = cytoscapeMock.mock.calls.at(-1)?.[0].elements.find(
      (element: { data: { focus?: boolean } }) => element.data.focus,
    )
    expect(focused?.data.id).toBe(entries.second.knowledgeId)
  })
})
