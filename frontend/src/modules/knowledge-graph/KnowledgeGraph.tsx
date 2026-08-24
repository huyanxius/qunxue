import cytoscape, { type ElementDefinition } from 'cytoscape'
import { useEffect, useRef, useState } from 'react'

import './KnowledgeGraph.css'
import type { KnowledgeGraphProjection } from './types'

interface KnowledgeGraphProps {
  readonly projection: KnowledgeGraphProjection
  readonly onSelectKnowledge: (knowledgeId: string) => void
  readonly onExpandNode?: (nodeId: string) => void
  readonly onSelectEdge?: (edgeId: string) => void
  readonly focusNodeId?: string
}

function graphElements(
  projection: KnowledgeGraphProjection,
  focusNodeId?: string,
): ElementDefinition[] {
  const structureEdges = projection.edges.filter((edge) => edge.layer === 'structure')
  const structureTargets = new Set(structureEdges.map((edge) => edge.target))
  const orderedNodeIds: string[] = []

  function appendStructure(nodeId: string) {
    if (orderedNodeIds.includes(nodeId)) return
    orderedNodeIds.push(nodeId)
    structureEdges
      .filter((edge) => edge.source === nodeId)
      .forEach((edge) => appendStructure(edge.target))
  }

  if (focusNodeId) {
    structureEdges
      .map((edge) => edge.source)
      .filter((nodeId) => !structureTargets.has(nodeId))
      .forEach(appendStructure)
  }
  projection.nodes.forEach((node) => {
    if (!orderedNodeIds.includes(node.id)) orderedNodeIds.push(node.id)
  })
  const orderedNodes = orderedNodeIds
    .map((id) => projection.nodes.find((node) => node.id === id))
    .filter((node): node is KnowledgeGraphProjection['nodes'][number] => Boolean(node))

  return [
    ...orderedNodes.map((node, index) => ({
      data: {
        id: node.id,
        label: node.label,
        displayLabel: node.label,
        nodeType: node.nodeType ?? 'entry',
      },
      ...(focusNodeId ? {
        position: {
          x: 140 + (Math.floor(index / 4) % 2 === 0 ? index % 4 : 3 - (index % 4)) * 260,
          y: 110 + Math.floor(index / 4) * 200,
        },
      } : {}),
    })),
    ...projection.edges.map((edge) => ({
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.relationType,
        direction: edge.direction,
        layer: edge.layer ?? 'reviewed',
      },
    })),
  ]
}

function GraphNotice({ unavailable }: { readonly unavailable: boolean }) {
  return (
    <p className="knowledge-graph__notice" role="status">
      {unavailable
        ? '知识关系图暂时不可用。请继续使用目录、关系列表和知识详情。'
        : '当前图中没有可展示的知识关系。'}
    </p>
  )
}

export function KnowledgeGraph({
  projection,
  onSelectKnowledge,
  onExpandNode,
  onSelectEdge,
  focusNodeId,
}: KnowledgeGraphProps) {
  const canvasRef = useRef<HTMLDivElement>(null)
  const [isUnavailable, setIsUnavailable] = useState(false)
  const hasEdges = projection.edges.length > 0
  const semanticEdges = projection.edges.filter((edge) => edge.layer === 'candidate' || edge.layer === 'reviewed')
  const hasStructureNodes = projection.nodes.some((node) => node.nodeType !== undefined && node.nodeType !== 'entry')
  const shouldRender = hasEdges || hasStructureNodes
  const unavailable = shouldRender && isUnavailable

  useEffect(() => {
    if (!shouldRender || !canvasRef.current) return

    setIsUnavailable(false)
    let graph: cytoscape.Core | undefined

    try {
      graph = cytoscape({
        container: canvasRef.current,
        elements: graphElements(projection, focusNodeId),
        style: [
          {
            selector: 'node',
            style: {
              'background-color': '#e6f0f7',
              'border-color': '#3e7cb1',
              'border-width': 1,
              color: '#33404a',
              'font-size': 12,
              label: 'data(displayLabel)',
              'text-halign': 'center',
              'text-valign': 'center',
              'text-wrap': 'wrap',
              'text-max-width': '160px',
              width: 184,
              height: 68,
              padding: '4px',
              shape: 'round-rectangle',
            },
          },
          {
            selector: 'edge',
            style: {
              'curve-style': 'bezier',
              'line-color': '#c8d1d7',
              'target-arrow-color': '#c8d1d7',
              'target-arrow-shape': 'none',
              width: 1.5,
            },
          },
          {
            selector: 'edge[layer = "structure"]',
            style: {
              'line-color': '#c8d1d7',
              'target-arrow-color': '#c8d1d7',
              'target-arrow-shape': 'triangle',
              width: 1,
            },
          },
          {
            selector: 'edge[layer = "candidate"]',
            style: {
              'line-color': '#a56b2a',
              'line-style': 'dashed',
              color: '#7a4f1f',
              'font-size': 10,
              label: 'data(label)',
              'text-background-color': '#f7f3ed',
              'text-background-opacity': 0.92,
              'text-background-padding': '3px',
              'target-arrow-color': '#a56b2a',
              'target-arrow-shape': 'triangle',
              width: 4,
            },
          },
          {
            selector: 'edge[layer = "reviewed"]',
            style: {
              'line-color': '#3e7cb1',
              'target-arrow-color': '#3e7cb1',
              width: 2,
            },
          },
          {
            selector: 'edge[direction = "directed"]',
            style: { 'target-arrow-shape': 'triangle' },
          },
          {
            selector: 'edge[direction = "bidirectional"]',
            style: {
              'source-arrow-color': '#c8d1d7',
              'source-arrow-shape': 'triangle',
              'target-arrow-shape': 'triangle',
            },
          },
        ],
        layout: focusNodeId ? {
          name: 'preset',
          animate: false,
          fit: true,
          padding: 50,
        } : {
          name: 'breadthfirst',
          animate: false,
          directed: true,
          fit: true,
          padding: 32,
          spacingFactor: 1.15,
          transform: (_node, position) => ({ x: position.y, y: position.x }),
        },
      })
      graph.on('tap', 'node', (event) => {
        const nodeId = event.target.id()
        if ((event.target.data?.('nodeType') ?? 'entry') === 'entry') {
          onSelectKnowledge(nodeId)
          return
        }
        onExpandNode?.(nodeId)
      })
      graph.on('tap', 'edge', (event) => onSelectEdge?.(event.target.id()))
    } catch {
      // The surrounding knowledge explorer remains the usable non-graph path.
      setIsUnavailable(true)
    }

    return () => {
      graph?.destroy()
    }
  }, [focusNodeId, onExpandNode, onSelectEdge, onSelectKnowledge, projection, shouldRender])

  return (
    <section className="knowledge-graph" aria-labelledby="knowledge-graph-title">
      <header className="knowledge-graph__heading">
        <div>
          <p>当前发布 · {projection.releaseId}</p>
          <h2 id="knowledge-graph-title">知识关系图</h2>
        </div>
        <span>
          {projection.edges.filter((edge) => (edge.layer ?? 'reviewed') === 'reviewed').length} 条正式关系
          {' · '}
          {projection.edges.filter((edge) => edge.layer === 'candidate').length} 条候选关系
        </span>
      </header>

      {!shouldRender || unavailable ? <GraphNotice unavailable={unavailable} /> : null}
      {shouldRender && !hasEdges ? (
        <p className="knowledge-graph__notice" role="status">选择维度节点，逐级展开真实目录。</p>
      ) : null}
      {shouldRender ? (
        <div
          aria-label="知识关系图"
          className={`knowledge-graph__canvas${focusNodeId ? ' knowledge-graph__canvas--focused' : ''}`}
          hidden={unavailable}
          ref={canvasRef}
          role="img"
        />
      ) : null}
      {semanticEdges.length > 0 ? (
        <div className="knowledge-graph__edge-index" aria-label="关系边索引">
          <span>可访问关系边</span>
          {semanticEdges.map((edge) => (
            <button
              key={edge.id}
              type="button"
              aria-label={`查看${edge.layer === 'candidate' ? '候选' : '正式'}关系 ${edge.relationType}`}
              onClick={() => onSelectEdge?.(edge.id)}
            >
              {edge.layer === 'candidate' ? 'candidate' : 'relation'} · {edge.relationType}
            </button>
          ))}
        </div>
      ) : null}
    </section>
  )
}
