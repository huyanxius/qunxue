import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ResearchMapCanvas } from './ResearchMapCanvas'
import type { ResearchCanvasProjection } from '../../modules/research-workspace'

const cytoscapeMock = vi.hoisted(() => vi.fn(() => ({
  add: vi.fn(),
  destroy: vi.fn(),
  elements: vi.fn(() => ({ remove: vi.fn() })),
  fit: vi.fn(),
  layout: vi.fn(() => ({ run: vi.fn() })),
  on: vi.fn(),
  resize: vi.fn(),
})))

vi.mock('cytoscape', () => ({ default: cytoscapeMock }))

afterEach(() => {
  cleanup()
  cytoscapeMock.mockClear()
})

function projection(answer: string): ResearchCanvasProjection {
  return {
    status: 'answering',
    question: '为什么年轻人越来越孤独？',
    nodes: [
      {
        id: 'question:streaming',
        kind: 'question',
        title: '为什么年轻人越来越孤独？',
        status: 'running',
        provenance: 'user',
      },
      {
        id: 'synthesis:streaming',
        kind: 'synthesis',
        title: 'Agent 综合',
        excerpt: answer,
        status: 'running',
        provenance: 'agent',
      },
    ],
    edges: [{
      id: 'question:streaming->synthesis:streaming',
      source: 'question:streaming',
      target: 'synthesis:streaming',
      label: '形成综合',
    }],
  }
}

describe('ResearchMapCanvas', () => {
  it('keeps one Cytoscape instance while only the streaming answer changes', () => {
    const { rerender } = render(<ResearchMapCanvas projection={projection('第一段')} />)

    rerender(<ResearchMapCanvas projection={projection('第一段继续生成')} />)

    expect(cytoscapeMock).toHaveBeenCalledTimes(1)
    const firstCall = (cytoscapeMock.mock.calls as unknown as Array<[Record<string, unknown>]>)[0]?.[0]
    expect(firstCall).toEqual(expect.objectContaining({
      elements: expect.arrayContaining([
        expect.objectContaining({ data: expect.objectContaining({ id: 'question:streaming' }) }),
      ]),
    }))
  })

  it('synchronizes the graph viewport after the responsive canvas receives nodes', () => {
    render(<ResearchMapCanvas projection={projection('第一段')} />)

    const graph = cytoscapeMock.mock.results[0]?.value as { resize: ReturnType<typeof vi.fn> }
    expect(graph.resize).toHaveBeenCalled()
  })

  it('keeps the node list inside the canvas and closes it with Escape', () => {
    render(<ResearchMapCanvas projection={projection('第一段')} />)

    const map = screen.getByRole('region', { name: '研究地图' })
    fireEvent.click(within(map).getByRole('button', { name: '以列表查看' }))

    const list = within(map).getByRole('region', { name: '研究节点列表' })
    expect(list.parentElement).toHaveClass('research-map__canvas-wrap')
    expect(within(list).getByRole('button', { name: '关闭节点列表' })).toBeVisible()

    fireEvent.keyDown(list, { key: 'Escape' })
    expect(within(map).queryByRole('region', { name: '研究节点列表' })).not.toBeInTheDocument()
  })
})
