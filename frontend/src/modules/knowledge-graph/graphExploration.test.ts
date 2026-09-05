import cytoscape from 'cytoscape'
import { expect, it } from 'vitest'
import { syncGraphProjection } from './graphExploration'

it('keeps dragged positions and viewport while adding and removing neighbors', () => {
  const graph = cytoscape({ headless: true, styleEnabled: true })
  const base = { releaseId: 'r', nodes: [{ id: 'a', label: '概念' }], edges: [] }
  syncGraphProjection(graph, base)
  graph.getElementById('a').position({ x: 217, y: 93 })
  graph.viewport({ zoom: 1.4, pan: { x: 15, y: 32 } })
  syncGraphProjection(graph, { ...base, nodes: [...base.nodes, { id: 'b', label: '关联' }], edges: [
    { id: 'ab', source: 'a', target: 'b', relationType: 'related', direction: 'undirected', layer: 'reviewed' },
  ] }, 'a')
  expect(graph.getElementById('a').position()).toEqual({ x: 217, y: 93 })
  expect(graph.zoom()).toBe(1.4)
  expect(graph.pan()).toEqual({ x: 15, y: 32 })
  expect(graph.getElementById('b').position()).not.toEqual(graph.getElementById('a').position())
  syncGraphProjection(graph, base)
  expect(graph.nodes().length).toBe(1)
  expect(graph.getElementById('a').position()).toEqual({ x: 217, y: 93 })
  graph.destroy()
})
