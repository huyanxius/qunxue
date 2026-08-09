import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { KnowledgeGraph, type KnowledgeGraphProjection } from './index'

const cytoscapeMock = vi.hoisted(() => vi.fn())

vi.mock('cytoscape', () => ({ default: cytoscapeMock }))

const projection: KnowledgeGraphProjection = {
  releaseId: 'release-preview-2026-08',
  nodes: [
    {
      id: 'knowledge-field',
      label: '场域理论',
      reviewStatus: 'reviewed',
    },
    {
      id: 'knowledge-habitus',
      label: '惯习',
      reviewStatus: 'pending',
    },
  ],
  edges: [
    {
      id: 'relation-field-habitus',
      source: 'knowledge-field',
      target: 'knowledge-habitus',
      relationType: '概念依赖',
      direction: 'directed',
    },
  ],
}

interface CytoscapeCoreStub {
  readonly destroy: ReturnType<typeof vi.fn>
  readonly layout: ReturnType<typeof vi.fn>
  readonly on: ReturnType<typeof vi.fn>
}

const cores: CytoscapeCoreStub[] = []

function createCore(): CytoscapeCoreStub {
  return {
    destroy: vi.fn(),
    layout: vi.fn(() => ({ run: vi.fn() })),
    on: vi.fn(),
  }
}

beforeEach(() => {
  cores.length = 0
  cytoscapeMock.mockReset()
  cytoscapeMock.mockImplementation(() => {
    const core = createCore()
    cores.push(core)
    return core
  })
})

afterEach(() => {
  cleanup()
})

describe('KnowledgeGraph', () => {
  it('shows a factual fallback when supplied relations are empty', () => {
    render(
      <KnowledgeGraph
        projection={{ ...projection, edges: [] }}
        onSelectKnowledge={vi.fn()}
      />,
    )

    expect(screen.getByRole('status')).toHaveTextContent(
      '当前图中没有可展示的已审核显式关系。',
    )
    expect(cytoscapeMock).not.toHaveBeenCalled()
  })

  it('renders supplied graph data and forwards a stable node id', () => {
    const onSelectKnowledge = vi.fn()
    render(
      <KnowledgeGraph
        projection={projection}
        onSelectKnowledge={onSelectKnowledge}
      />,
    )

    expect(screen.getByRole('region', { name: '知识关系图' })).toBeVisible()
    expect(cytoscapeMock).toHaveBeenCalledTimes(1)
    expect(cytoscapeMock).toHaveBeenCalledWith(
      expect.objectContaining({ container: expect.any(HTMLDivElement) }),
    )

    const nodeTapHandler = cores[0]?.on.mock.calls.find(
      ([event, selector]) => event === 'tap' && selector === 'node',
    )?.[2]
    nodeTapHandler?.({ target: { id: () => 'knowledge-field' } })

    expect(onSelectKnowledge).toHaveBeenCalledWith('knowledge-field')
  })

  it('makes a pending node review status visible in the graph label', () => {
    render(
      <KnowledgeGraph projection={projection} onSelectKnowledge={vi.fn()} />,
    )

    const options = cytoscapeMock.mock.calls[0]?.[0]
    const pendingNode = options?.elements.find(
      (element: { data: { id: string } }) =>
        element.data.id === 'knowledge-habitus',
    )
    const nodeStyle = options?.style.find(
      (rule: { selector: string }) => rule.selector === 'node',
    )

    expect(pendingNode?.data.displayLabel).toBe('惯习\n待核验')
    expect(nodeStyle?.style.label).toBe('data(displayLabel)')
  })

  it('keeps a reviewed node title unchanged', () => {
    render(
      <KnowledgeGraph projection={projection} onSelectKnowledge={vi.fn()} />,
    )

    const options = cytoscapeMock.mock.calls[0]?.[0]
    const reviewedNode = options?.elements.find(
      (element: { data: { id: string } }) =>
        element.data.id === 'knowledge-field',
    )

    expect(reviewedNode?.data.displayLabel).toBe('场域理论')
  })

  it('labels a retired node without presenting it as pending', () => {
    const retiredProjection = {
      ...projection,
      nodes: projection.nodes.map((node) =>
        node.id === 'knowledge-habitus'
          ? { ...node, reviewStatus: 'retired' }
          : node,
      ),
    }
    render(
      <KnowledgeGraph
        projection={retiredProjection}
        onSelectKnowledge={vi.fn()}
      />,
    )

    const options = cytoscapeMock.mock.calls[0]?.[0]
    const retiredNode = options?.elements.find(
      (element: { data: { id: string } }) =>
        element.data.id === 'knowledge-habitus',
    )

    expect(retiredNode?.data.displayLabel).toBe('惯习\n已停用')
  })

  it('destroys the previous graph before rerendering and on unmount', () => {
    const view = render(
      <KnowledgeGraph projection={projection} onSelectKnowledge={vi.fn()} />,
    )

    view.rerender(
      <KnowledgeGraph
        projection={{ ...projection, nodes: [...projection.nodes] }}
        onSelectKnowledge={vi.fn()}
      />,
    )

    expect(cores[0]?.destroy).toHaveBeenCalledTimes(1)
    view.unmount()
    expect(cores[1]?.destroy).toHaveBeenCalledTimes(1)
  })

  it('falls back without crashing when Cytoscape cannot initialize', async () => {
    cytoscapeMock.mockImplementationOnce(() => {
      throw new Error('canvas unavailable')
    })

    render(
      <KnowledgeGraph projection={projection} onSelectKnowledge={vi.fn()} />,
    )

    expect(await screen.findByRole('status')).toHaveTextContent(
      '知识关系图暂时不可用。',
    )
  })

  it('shows the factual empty state after an initialization failure', async () => {
    cytoscapeMock.mockImplementationOnce(() => {
      throw new Error('canvas unavailable')
    })

    const view = render(
      <KnowledgeGraph projection={projection} onSelectKnowledge={vi.fn()} />,
    )

    await screen.findByRole('status')
    view.rerender(
      <KnowledgeGraph
        projection={{ ...projection, edges: [] }}
        onSelectKnowledge={vi.fn()}
      />,
    )

    expect(screen.getByRole('status')).toHaveTextContent(
      '当前图中没有可展示的已审核显式关系。',
    )
  })
})
