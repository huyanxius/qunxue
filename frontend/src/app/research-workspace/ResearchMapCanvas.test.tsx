import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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
  Background: () => null,
  BackgroundVariant: { Dots: 'dots' },
  Controls: () => <div data-testid="flow-controls" />,
  Handle: () => null,
  MarkerType: { ArrowClosed: 'arrowclosed' },
  MiniMap: () => <div data-testid="flow-minimap" />,
  NodeToolbar: ({ children, isVisible }: { children: React.ReactNode; isVisible?: boolean }) => isVisible ? <>{children}</> : null,
  Position: { Left: 'left', Right: 'right', Top: 'top' },
  ReactFlow: ({ children, nodes, onNodeClick, onInit }: {
    children: React.ReactNode
    nodes: Array<{ id: string; data: { node: { title: string } } }>
    onNodeClick?: (event: unknown, node: unknown) => void
    onInit?: (instance: { fitView: () => void }) => void
  }) => {
    onInit?.({ fitView: () => undefined })
    return <div data-testid="react-flow">{nodes.map((node) => <button type="button" key={node.id} onClick={() => onNodeClick?.({}, node)}>{node.data.node.title}</button>)}{children}</div>
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
  it('lays out typed argument nodes with mature navigation aids', async () => {
    render(<ResearchMapCanvas projection={projection} />)

    await waitFor(() => expect(screen.getByRole('button', { name: '时间贫困压缩关系维护' })).toBeVisible())
    expect(screen.getByTestId('flow-controls')).toBeInTheDocument()
    expect(screen.getByTestId('flow-minimap')).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: '画布聚焦层级' })).toBeVisible()
    expect(screen.getByText((_, element) => element?.textContent === '6 个节点 · 4 条论证关系')).toBeVisible()
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
})
