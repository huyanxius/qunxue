import cytoscape, { type Core, type ElementDefinition } from 'cytoscape'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import './ObsidianKnowledgeGraph.css'
import type { KnowledgeGraphProjection } from './types'

interface ObsidianKnowledgeGraphProps {
  readonly projection: KnowledgeGraphProjection
  readonly focusNodeId?: string
  readonly onExpandNode?: (nodeId: string) => void
  readonly onSelectEdge?: (edgeId: string) => void
  readonly onSelectKnowledge: (knowledgeId: string) => void
}

function graphElements(
  projection: KnowledgeGraphProjection,
  focusNodeId?: string,
): ElementDefinition[] {
  const neighborIds = new Set(
    projection.edges.flatMap((edge) => (
      edge.source === focusNodeId ? [edge.target]
        : edge.target === focusNodeId ? [edge.source]
          : []
    )),
  )

  return [
    ...projection.nodes.map((node) => {
      const nodeType = node.nodeType ?? 'entry'
      const classes = [
        `node--${nodeType}`,
        node.id === focusNodeId ? 'node--focus' : '',
        neighborIds.has(node.id) ? 'node--neighbor' : '',
        focusNodeId && node.id !== focusNodeId && !neighborIds.has(node.id)
          ? 'node--context'
          : '',
        node.reviewStatus && node.reviewStatus !== 'reviewed'
          ? 'node--unreviewed'
          : '',
      ].filter(Boolean).join(' ')
      return {
        classes,
        data: {
          id: node.id,
          label: node.label,
          nodeType,
          focus: node.id === focusNodeId,
          reviewStatus: node.reviewStatus,
        },
      }
    }),
    ...projection.edges.map((edge) => ({
      classes: [
        `edge--${edge.layer ?? 'reviewed'}`,
        edge.source === focusNodeId || edge.target === focusNodeId
          ? 'edge--neighbor'
          : 'edge--context',
        edge.direction === 'directed' || edge.direction === 'outbound'
          ? 'edge--directed'
          : '',
        edge.direction === 'bidirectional' ? 'edge--bidirectional' : '',
      ].filter(Boolean).join(' '),
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.layer === 'candidate'
          ? `pending · ${edge.relationType}`
          : edge.relationType,
        layer: edge.layer ?? 'reviewed',
      },
    })),
  ]
}

function layoutOptions(hasFocus: boolean, hasEdges: boolean) {
  if (!hasFocus && !hasEdges) {
    return {
      name: 'circle',
      animate: false,
      fit: true,
      padding: 96,
      spacingFactor: 1.35,
    }
  }
  return {
    name: 'cose',
    animate: false,
    componentSpacing: 56,
    edgeElasticity: 120,
    fit: true,
    gravity: 0.34,
    idealEdgeLength: 54,
    nestingFactor: 1.15,
    nodeOverlap: 14,
    nodeRepulsion: 90000,
    numIter: 800,
    padding: 72,
    randomize: true,
  }
}

function fitView(graph: Core, focusNodeId?: string) {
  if (!focusNodeId) {
    graph.fit(graph.elements(), 88)
    return
  }
  const focus = graph.getElementById(focusNodeId)
  const container = graph.container()
  if (focus.empty() || !container) {
    graph.fit(graph.elements(), 72)
    return
  }
  const bounds = graph.elements().boundingBox({ includeLabels: false })
  const position = focus.position()
  const padding = 72
  const halfWidth = Math.max(position.x - bounds.x1, bounds.x2 - position.x, 1)
  const halfHeight = Math.max(position.y - bounds.y1, bounds.y2 - position.y, 1)
  const zoom = Math.max(
    graph.minZoom(),
    Math.min(
      graph.maxZoom(),
      (container.clientWidth - padding * 2) / (halfWidth * 2),
      (container.clientHeight - padding * 2) / (halfHeight * 2),
    ),
  )
  graph.viewport({
    zoom,
    pan: {
      x: container.clientWidth / 2 - position.x * zoom,
      y: container.clientHeight / 2 - position.y * zoom,
    },
  })
}

const graphStyle: cytoscape.StylesheetJson = [
  {
    selector: 'node',
    style: {
      'background-color': '#7f929f',
      'border-color': '#f7fafc',
      'border-width': 1.5,
      color: '#33404a',
      'font-size': 10,
      height: 10,
      label: 'data(label)',
      'min-zoomed-font-size': 8,
      opacity: 0.92,
      shape: 'ellipse',
      'text-background-color': '#fcfdfe',
      'text-background-opacity': 0,
      'text-background-padding': '2px',
      'text-background-shape': 'roundrectangle',
      'text-halign': 'center',
      'text-margin-y': -8,
      'text-outline-color': '#fcfdfe',
      'text-outline-opacity': 0.92,
      'text-outline-width': 2,
      'text-valign': 'top',
      'transition-duration': 160,
      'transition-property': 'background-color, border-color, height, opacity, width',
      width: 10,
      'z-index': 2,
    },
  },
  {
    selector: 'node.node--dimension',
    style: {
      'background-color': '#264d68',
      'border-color': '#dcebf4',
      'border-width': 2,
      color: '#173f5f',
      'font-size': 10,
      'font-weight': 700,
      height: 16,
      'min-zoomed-font-size': 9,
      'text-margin-y': -10,
      width: 16,
      'z-index': 8,
    },
  },
  {
    selector: 'node.node--category',
    style: {
      'background-color': '#6f8797',
      height: 12,
      width: 12,
      'z-index': 5,
    },
  },
  {
    selector: 'node.node--neighbor',
    style: {
      'background-color': '#3e7cb1',
      height: 11,
      opacity: 1,
      width: 11,
      'z-index': 7,
    },
  },
  {
    selector: 'node.node--focus',
    style: {
      'background-color': '#173f5f',
      'border-color': '#9fc6df',
      'border-width': 3,
      color: '#173f5f',
      'font-size': 11,
      'font-weight': 700,
      height: 16,
      'min-zoomed-font-size': 9,
      'text-margin-y': -11,
      'underlay-color': '#9fc6df',
      'underlay-opacity': 0.2,
      'underlay-padding': 5,
      'underlay-shape': 'ellipse',
      width: 16,
      'z-index': 12,
    },
  },
  {
    selector: 'node.node--unreviewed',
    style: { 'border-color': '#b48752' },
  },
  {
    selector: 'node.node--context',
    style: { opacity: 0.62 },
  },
  {
    selector: 'node.is-hovered, node:selected',
    style: {
      'background-color': '#173f5f',
      'border-color': '#9fc6df',
      'border-width': 4,
      opacity: 1,
      'z-index': 14,
    },
  },
  {
    selector: 'node.is-dimmed',
    style: { opacity: 0.12 },
  },
  {
    selector: 'edge',
    style: {
      'curve-style': 'straight',
      'line-color': '#c8d1d7',
      opacity: 0.72,
      'target-arrow-shape': 'none',
      width: 0.8,
      'z-index': 1,
    },
  },
  {
    selector: 'edge.edge--structure',
    style: {
      'line-color': '#c8d1d7',
      opacity: 0.58,
      width: 0.7,
    },
  },
  {
    selector: 'edge.edge--reviewed',
    style: {
      'line-color': '#3e7cb1',
      opacity: 0.9,
      'target-arrow-color': '#3e7cb1',
      width: 1.8,
    },
  },
  {
    selector: 'edge.edge--candidate',
    style: {
      'line-color': '#a56b2a',
      'line-style': 'dashed',
      opacity: 0.88,
      'target-arrow-color': '#a56b2a',
      width: 1.6,
    },
  },
  {
    selector: 'edge.edge--directed',
    style: {
      'arrow-scale': 0.65,
      'target-arrow-shape': 'triangle',
    },
  },
  {
    selector: 'edge.edge--bidirectional',
    style: {
      'arrow-scale': 0.65,
      'source-arrow-color': '#3e7cb1',
      'source-arrow-shape': 'triangle',
      'target-arrow-shape': 'triangle',
    },
  },
  {
    selector: 'edge.edge--context',
    style: { opacity: 0.42 },
  },
  {
    selector: 'edge.is-hovered, edge:selected',
    style: {
      color: '#33404a',
      'font-size': 9,
      label: 'data(label)',
      opacity: 1,
      'text-background-color': '#fcfdfe',
      'text-background-opacity': 0.92,
      'text-background-padding': '3px',
      width: 2.2,
      'z-index': 10,
    },
  },
  {
    selector: 'edge.is-dimmed',
    style: { opacity: 0.08 },
  },
]

export function ObsidianKnowledgeGraph({
  projection,
  focusNodeId,
  onExpandNode,
  onSelectEdge,
  onSelectKnowledge,
}: ObsidianKnowledgeGraphProps) {
  const canvasRef = useRef<HTMLDivElement>(null)
  const graphRef = useRef<Core | undefined>(undefined)
  const onExpandNodeRef = useRef(onExpandNode)
  const onSelectEdgeRef = useRef(onSelectEdge)
  const onSelectKnowledgeRef = useRef(onSelectKnowledge)
  onExpandNodeRef.current = onExpandNode
  onSelectEdgeRef.current = onSelectEdge
  onSelectKnowledgeRef.current = onSelectKnowledge
  const [unavailable, setUnavailable] = useState(false)
  const [hoveredLabel, setHoveredLabel] = useState('')
  const elements = useMemo(
    () => graphElements(projection, focusNodeId),
    [focusNodeId, projection],
  )
  const hasEdges = projection.edges.length > 0

  const fit = useCallback(() => {
    if (graphRef.current) fitView(graphRef.current, focusNodeId)
  }, [focusNodeId])

  const relayout = useCallback(() => {
    const graph = graphRef.current
    if (!graph) return
    graph.one('layoutstop', () => fitView(graph, focusNodeId))
    graph.layout(layoutOptions(Boolean(focusNodeId), hasEdges)).run()
  }, [focusNodeId, hasEdges])

  useEffect(() => {
    if (!canvasRef.current || elements.length === 0) return
    setUnavailable(false)
    let graph: Core | undefined
    let resizeObserver: ResizeObserver | undefined
    let frame = 0

    try {
      graph = cytoscape({
        autoungrabify: false,
        boxSelectionEnabled: false,
        container: canvasRef.current,
        elements,
        layout: layoutOptions(Boolean(focusNodeId), hasEdges),
        maxZoom: 3.2,
        minZoom: 0.16,
        style: graphStyle,
        userPanningEnabled: true,
        userZoomingEnabled: true,
      })
      graphRef.current = graph
      graph.on('tap', 'node', (event) => {
        const nodeType = event.target.data('nodeType') ?? 'entry'
        const nodeId = event.target.id()
        if (nodeType === 'entry') onSelectKnowledgeRef.current(nodeId)
        else onExpandNodeRef.current?.(nodeId)
      })
      graph.on('tap', 'edge', (event) => {
        event.target.select()
        onSelectEdgeRef.current?.(event.target.id())
      })
      graph.on('mouseover', 'node', (event) => {
        const neighborhood = event.target.closedNeighborhood()
        graph?.elements().addClass('is-dimmed')
        neighborhood.removeClass('is-dimmed').addClass('is-hovered')
        setHoveredLabel(event.target.data('label') ?? '')
      })
      graph.on('mouseout', 'node', () => {
        graph?.elements().removeClass('is-dimmed is-hovered')
        setHoveredLabel('')
      })
      graph.on('mouseover', 'edge', (event) => event.target.addClass('is-hovered'))
      graph.on('mouseout', 'edge', (event) => event.target.removeClass('is-hovered'))
      frame = globalThis.requestAnimationFrame?.(() => {
        if (graph) fitView(graph, focusNodeId)
      }) ?? 0
      if (typeof ResizeObserver !== 'undefined') {
        resizeObserver = new ResizeObserver(() => graph?.resize())
        resizeObserver.observe(canvasRef.current)
      }
    } catch {
      setUnavailable(true)
    }

    return () => {
      if (frame) globalThis.cancelAnimationFrame?.(frame)
      resizeObserver?.disconnect()
      graphRef.current = undefined
      graph?.destroy()
    }
  }, [elements, focusNodeId, hasEdges])

  return (
    <section className="obsidian-knowledge-graph" aria-label="节点式知识图谱">
      <div className="obsidian-knowledge-graph__controls">
        <span>{projection.nodes.length} 个节点 · {projection.edges.length} 条连线</span>
        <div>
          <button type="button" onClick={fit}>适应画布</button>
          <button type="button" onClick={relayout}>重新布局</button>
        </div>
      </div>
      {hoveredLabel ? (
        <p className="obsidian-knowledge-graph__hover" aria-live="polite">{hoveredLabel}</p>
      ) : null}
      {unavailable ? (
        <p className="obsidian-knowledge-graph__notice" role="alert">
          节点画布暂时不可用；右侧搜索、详情与证据仍可继续使用。
        </p>
      ) : null}
      {!focusNodeId && !hasEdges ? (
        <p className="obsidian-knowledge-graph__notice" role="status">
          七维入口已就绪。搜索条目，或选择维度节点开始探索。
        </p>
      ) : null}
      <div
        ref={canvasRef}
        className="obsidian-knowledge-graph__canvas"
        role="img"
        aria-label="Obsidian 式节点知识图谱"
        hidden={unavailable}
      />
    </section>
  )
}
