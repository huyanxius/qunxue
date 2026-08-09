import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { KnowledgeGraph } from './KnowledgeGraph'
import type { KnowledgeGraphProjection } from './knowledgeGraphAdapter'

const cytoscapeMock = vi.hoisted(() => vi.fn())

vi.mock('cytoscape', () => ({ default: cytoscapeMock }))

const projection: KnowledgeGraphProjection = {
  release: {
    knowledgeReleaseId: 'release-preview-2026-08',
    level: 'preview',
    contentHash: 'sha256:preview-content',
  },
  nodes: [
    {
      id: 'knowledge-field',
      label: '场域理论',
      dimensionId: 'D6',
      dimension: '学派传统',
      categoryId: 'category-theory',
      category: '理论',
      directoryPath: [
        { id: 'D6', type: 'dimension', title: '学派传统' },
        { id: 'category-theory', type: 'category', title: '理论' },
      ],
      reviewStatus: 'reviewed',
      contentVersion: 3,
    },
    {
      id: 'knowledge-habitus',
      label: '惯习',
      dimensionId: 'D1',
      dimension: '本体论',
      categoryId: 'category-concept',
      category: '概念',
      directoryPath: [
        { id: 'D1', type: 'dimension', title: '本体论' },
        { id: 'category-concept', type: 'category', title: '概念' },
      ],
      reviewStatus: 'pending',
      contentVersion: 2,
    },
  ],
  edges: [
    {
      id: 'relation-field-habitus',
      source: 'knowledge-field',
      target: 'knowledge-habitus',
      relationType: '概念依赖',
      direction: 'directed',
      description: '场域分析需要结合行动者的惯习。',
      evidenceSourceIds: ['source-book-1'],
      evidenceGrade: 'A',
      reviewStatus: 'reviewed',
      contentVersion: 2,
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
