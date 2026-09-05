import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ComponentType, ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ResearchMapCanvas } from './ResearchMapCanvas'
import type { ResearchCanvasProjection } from '../../modules/research-workspace'

vi.mock('elkjs/lib/elk.bundled.js', () => ({
  default: class {
    async layout(graph: { children?: Array<Record<string, unknown>>; edges?: Array<Record<string, unknown>> }) {
      return {
        ...graph,
        children: (graph.children ?? []).map((child, index) => ({ ...child, x: index * 180, y: index * 40 })),
      }
    }
  },
}))

vi.mock('@xyflow/react', () => ({
  Background: () => <div className="react-flow__background" />,
  BackgroundVariant: { Dots: 'dots' },
  Controls: () => <div data-testid="flow-controls" />,
  Handle: () => null,
  MarkerType: { ArrowClosed: 'arrowclosed' },
  MiniMap: () => <div data-testid="flow-minimap" />,
  NodeToolbar: ({ children, isVisible }: { children: React.ReactNode; isVisible?: boolean }) => isVisible ? <>{children}</> : null,
  Position: { Left: 'left', Right: 'right', Top: 'top' },
  ReactFlow: ({ children, nodes, nodeTypes, onNodeClick, onInit, 'aria-label': ariaLabel }: {
    children: ReactNode
    nodes: Array<{ id: string; data: { node: { title: string } } }>
    nodeTypes?: { argument: ComponentType<{ data: { node: { id: string; kind: string; title: string }; onFocus: () => void; onContinue: () => void }; selected: boolean }> }
    onNodeClick?: (event: unknown, node: unknown) => void
    onInit?: (instance: { fitView: () => void }) => void
    'aria-label'?: string
  }) => {
    onInit?.({ fitView: () => undefined })
    const ArgumentNode = nodeTypes?.argument
    return <div data-testid="react-flow" aria-label={ariaLabel}>{nodes.map((node) => <div key={node.id}><button type="button" onClick={() => onNodeClick?.({}, node)}>{node.data.node.title}</button>{ArgumentNode ? <ArgumentNode data={node.data as never} selected={false} /> : null}</div>)}{children}</div>
  },
}))

afterEach(cleanup)

const projection: ResearchCanvasProjection = {
  status: 'ready',
  question: '为什么年轻人越来越孤独？',
  nodes: [
    { id: 'question', kind: 'question', title: '为什么年轻人越来越孤独？', summary: '一个社会联结问题。', status: 'developing', provenance: 'user', citationIds: [] },
    { id: 'theory', kind: 'theory', title: '社会资本理论', summary: '观察关系资源与信任。', status: 'grounded', provenance: 'agent', citationIds: [] },
    { id: 'claim', kind: 'claim', title: '时间贫困压缩关系维护', summary: '劳动与通勤挤压重复互动。', status: 'grounded', provenance: 'agent', citationIds: ['knowledge:time'] },
    { id: 'evidence', kind: 'evidence', title: '稳定互动机会下降', summary: '知识证据摘要。', status: 'verified', provenance: 'knowledge', citationIds: ['knowledge:time'] },
    { id: 'gap', kind: 'gap', title: '缺少城市层级比较', summary: '需要补充比较材料。', status: 'open', provenance: 'agent', citationIds: [] },
    { id: 'synthesis', kind: 'synthesis', title: '孤独是关系机会结构的变化', summary: '阶段性综合。', status: 'complete', provenance: 'agent', citationIds: ['knowledge:time'] },
  ],
  edges: [
    { id: 'e1', source: 'theory', target: 'claim', relation: 'explains', label: '解释机制' },
    { id: 'e2', source: 'evidence', target: 'claim', relation: 'supports' },
    { id: 'e3', source: 'claim', target: 'synthesis', relation: 'derives' },
    { id: 'e4', source: 'gap', target: 'claim', relation: 'challenges' },
  ],
}

describe('ResearchMapCanvas', () => {
  it('explains the dotted canvas without duplicating the Agent prompts', () => {
    const { container } = render(<ResearchMapCanvas projection={{ status: 'empty', question: '', nodes: [], edges: [] }} />)

    expect(screen.getByLabelText('空白研究画布')).toBeVisible()
    expect(container.querySelector('.react-flow__background')).toBeInTheDocument()
    expect(container.querySelector('[data-research-agent-bot]')).toBeInTheDocument()
    expect(screen.getByLabelText('画布说明')).toHaveTextContent('对话中形成的研究结构会在这里展开。')
    expect(within(screen.getByLabelText('画布说明')).queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByText('让问题在这里形成结构')).not.toBeInTheDocument()
    expect(screen.queryByText('ARGUMENT MAP')).not.toBeInTheDocument()
    expect(screen.queryByText('不是聊天摘要。这里仅保留 Agent 明确建立的问题、理论、主张、证据与缺口。')).not.toBeInTheDocument()
    expect(screen.queryByText(/0 个节点/)).not.toBeInTheDocument()
  })

  it('lays out typed argument nodes with mature navigation aids', async () => {
    render(<ResearchMapCanvas projection={projection} />)

    await waitFor(() => expect(screen.getByRole('button', { name: '时间贫困压缩关系维护' })).toBeVisible())
    expect(screen.queryByLabelText('画布说明')).not.toBeInTheDocument()
    expect(screen.getByTestId('flow-controls')).toBeInTheDocument()
    expect(screen.queryByTestId('flow-minimap')).not.toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: '画布聚焦层级' })).toBeVisible()
    expect(screen.queryByText('研究论证地图')).not.toBeInTheDocument()
    expect(screen.queryByText(/6 个节点/)).not.toBeInTheDocument()
  })

  it('opens the inspector from a real node selection and exposes its citation', async () => {
    const onSelectNode = vi.fn()
    const onOpenCitation = vi.fn()
    const { rerender } = render(<ResearchMapCanvas projection={projection} onSelectNode={onSelectNode} onOpenCitation={onOpenCitation} />)

    await waitFor(() => fireEvent.click(screen.getByRole('button', { name: '时间贫困压缩关系维护' })))
    expect(onSelectNode).toHaveBeenCalledWith(expect.objectContaining({ id: 'claim' }))

    rerender(<ResearchMapCanvas projection={projection} selectedNodeId="claim" onSelectNode={onSelectNode} onOpenCitation={onOpenCitation} />)
    const inspector = screen.getByRole('complementary', { name: '节点检查器' })
    expect(within(inspector).getByText('劳动与通勤挤压重复互动。')).toBeVisible()
    fireEvent.click(within(inspector).getByRole('button', { name: '依据 1' }))
    expect(onOpenCitation).toHaveBeenCalledWith('knowledge:time')
  })

  it('keeps the grouped node directory inside the canvas and closes it with Escape', async () => {
    render(<ResearchMapCanvas projection={projection} />)

    fireEvent.click(screen.getByRole('button', { name: '打开节点目录' }))
    const list = screen.getByRole('region', { name: '研究节点目录' })
    expect(within(list).getByText('理论视角')).toBeVisible()
    expect(within(list).getByText('证据缺口')).toBeVisible()

    fireEvent.keyDown(list, { key: 'Escape' })
    expect(screen.queryByRole('region', { name: '研究节点目录' })).not.toBeInTheDocument()
  })

  it('expands document content inside the existing argument map node', async () => {
    const documentProjection: ResearchCanvasProjection = {
      ...projection,
      nodes: [...projection.nodes, { id: 'document', kind: 'document', title: '理论判断文档', summary: '研究文档', status: 'developing', provenance: 'user', citationIds: [] }],
    }

    render(<ResearchMapCanvas projection={documentProjection} selectedNodeId="document" expandedNodeContent={{ document: <section aria-label="研究文档节点">正文编辑区</section> }} />)

    expect(await screen.findByRole('region', { name: '研究文档节点' })).toHaveTextContent('正文编辑区')
    expect(screen.getByRole('region', { name: '研究论证地图' })).toContainElement(screen.getByRole('region', { name: '研究文档节点' }))
  })
})

it('keeps evidence inspection available when a manuscript card shares the canvas', () => {
  const onOpenCitation = vi.fn()
  render(<ResearchMapCanvas projection={{ ...projection, nodes: [...projection.nodes, { id: 'manuscript', kind: 'document', title: '研究方案文稿', status: 'developing', provenance: 'user', citationIds: [] }] }} selectedNodeId="claim" onOpenCitation={onOpenCitation} />)
  fireEvent.click(screen.getByRole('button', { name: '依据 1' }))
  expect(onOpenCitation).toHaveBeenCalledWith('knowledge:time')
})
