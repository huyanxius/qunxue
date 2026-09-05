import type { Core } from 'cytoscape'
import type { KnowledgeGraphProjection } from './types'

/** Update only changed elements; user positions and viewport are exploration state. */
export function syncGraphProjection(graph: Core, projection: KnowledgeGraphProjection, anchor?: string) {
  const wanted = new Set([...projection.nodes, ...projection.edges].map((item) => item.id))
  const fresh = projection.nodes.filter((node) => graph.getElementById(node.id).empty())
  const origin = anchor && graph.getElementById(anchor).nonempty()
    ? graph.getElementById(anchor).position() : { x: 0, y: 0 }
  const occupied = graph.nodes().map((node) => node.position())
  graph.batch(() => {
    graph.elements().filter((element) => !wanted.has(element.id())).remove()
    projection.nodes.forEach((node) => {
      const existing = graph.getElementById(node.id)
      const data = { id: node.id, label: node.label, nodeType: node.nodeType ?? 'entry' }
      if (existing.nonempty()) { existing.data(data); return }
      const index = fresh.indexOf(node)
      const angle = index * 2.3999632297
      let radius = fresh.length === 1 && occupied.length === 0 ? 0 : 180 + 42 * Math.sqrt(index)
      let position = { x: origin.x + Math.cos(angle) * radius, y: origin.y + Math.sin(angle) * radius }
      while (occupied.some((point) => Math.hypot(point.x - position.x, point.y - position.y) < 115)) {
        radius += 70
        position = { x: origin.x + Math.cos(angle) * radius, y: origin.y + Math.sin(angle) * radius }
      }
      occupied.push(position)
      graph.add({ group: 'nodes', data, position })
    })
    projection.edges.forEach((edge) => {
      const data = { ...edge, label: edge.layer === 'structure' ? '目录包含' : edge.relationType }
      const existing = graph.getElementById(edge.id)
      if (existing.nonempty()) existing.data(data)
      else graph.add({ group: 'edges', data })
    })
  })
}
