import { cleanup, fireEvent, render, screen } from '@testing-library/react'
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
      nodeType: 'entry',
      reviewStatus: 'reviewed',
    },
    {
      id: 'knowledge-habitus',
      label: '惯习',
      nodeType: 'entry',
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
      layer: 'reviewed',
    },
  ],
}

interface CytoscapeCoreStub {
  readonly destroy: ReturnType<typeof vi.fn>
  readonly fit: ReturnType<typeof vi.fn>
  readonly elements: ReturnType<typeof vi.fn>
  readonly getElementById: ReturnType<typeof vi.fn>
  readonly layout: ReturnType<typeof vi.fn>
  readonly on: ReturnType<typeof vi.fn>
}

const cores: CytoscapeCoreStub[] = []

function createCore(): CytoscapeCoreStub {
  const pathCollection = { kind: 'focused-path' }
  const focused = {
    nonempty: () => true,
    predecessors: vi.fn(() => ({ kind: 'predecessors' })),
    union: vi.fn(() => pathCollection),
  }
  return {
    destroy: vi.fn(),
    elements: vi.fn(() => pathCollection),
    fit: vi.fn(),
    getElementById: vi.fn(() => focused),
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
      '当前图中没有可展示的知识关系。',
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

  it('expands directory nodes, navigates entry nodes, and selects candidate edges', () => {
    const onExpandNode = vi.fn()
    const onSelectKnowledge = vi.fn()
    const onSelectEdge = vi.fn()
    const layeredProjection: KnowledgeGraphProjection = {
      ...projection,
      nodes: [
        { id: 'D1', label: '本体论', nodeType: 'dimension' },
        ...projection.nodes,
      ],
      edges: [
        ...projection.edges,
        {
          id: 'candidate:one',
          source: 'knowledge-field',
          target: 'knowledge-habitus',
          relationType: 'extends',
          direction: 'outbound',
          layer: 'candidate',
          reviewStatus: 'pending',
        },
      ],
    }
    render(
      <KnowledgeGraph
        projection={layeredProjection}
        onExpandNode={onExpandNode}
        onSelectEdge={onSelectEdge}
        onSelectKnowledge={onSelectKnowledge}
      />,
    )

    const nodeTapHandler = cores[0]?.on.mock.calls.find(
      ([event, selector]) => event === 'tap' && selector === 'node',
    )?.[2]
    nodeTapHandler?.({ target: { data: (key: string) => key === 'nodeType' ? 'dimension' : 'D1', id: () => 'D1' } })
    nodeTapHandler?.({ target: { data: (key: string) => key === 'nodeType' ? 'entry' : 'knowledge-field', id: () => 'knowledge-field' } })

    const edgeTapHandler = cores[0]?.on.mock.calls.find(
      ([event, selector]) => event === 'tap' && selector === 'edge',
    )?.[2]
    edgeTapHandler?.({ target: { id: () => 'candidate:one' } })

    expect(onExpandNode).toHaveBeenCalledWith('D1')
    expect(onSelectKnowledge).toHaveBeenCalledWith('knowledge-field')
    expect(onSelectEdge).toHaveBeenCalledWith('candidate:one')
    const options = cytoscapeMock.mock.calls[0]?.[0]
    expect(options?.style).toEqual(expect.arrayContaining([
      expect.objectContaining({
        selector: 'edge[layer = "candidate"]',
        style: expect.objectContaining({
          'line-style': 'dashed',
          label: 'data(label)',
          width: 4,
        }),
      }),
    ]))
    fireEvent.click(screen.getByRole('button', { name: '查看候选关系 extends' }))
    expect(onSelectEdge).toHaveBeenLastCalledWith('candidate:one')
  })

  it('does not append internal review state to graph labels', () => {
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

    expect(pendingNode?.data.displayLabel).toBe('惯习')
    expect(nodeStyle?.style.label).toBe('data(displayLabel)')
    expect(nodeStyle?.style.width).toBe(184)
    expect(nodeStyle?.style.height).toBe(68)
    expect(nodeStyle?.style['text-wrap']).toBe('wrap')
  })

  it('uses a spaced two-row preset for a focused path', () => {
    render(
      <KnowledgeGraph
        projection={projection}
        focusNodeId="knowledge-habitus"
        onSelectKnowledge={vi.fn()}
      />,
    )

    const options = cytoscapeMock.mock.calls[0]?.[0]
    expect(options.layout).toEqual(expect.objectContaining({
      name: 'preset',
      fit: true,
      padding: 50,
    }))
    const nodeElements = options.elements.filter(
      (element: { data: { source?: string } }) => !element.data.source,
    )
    expect(nodeElements.map((element: { position: unknown }) => element.position)).toEqual([
      { x: 140, y: 110 },
      { x: 400, y: 110 },
    ])
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

  it('does not append retired state to a published node label', () => {
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

    expect(retiredNode?.data.displayLabel).toBe('惯习')
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
      '当前图中没有可展示的知识关系。',
    )
  })
})
