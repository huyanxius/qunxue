import cytoscape, { type ElementDefinition } from 'cytoscape'
import { useEffect, useRef, useState } from 'react'

import type { KnowledgeGraphProjection } from './knowledgeGraphAdapter'
import './KnowledgeGraph.css'

interface KnowledgeGraphProps {
  readonly projection: KnowledgeGraphProjection
  readonly onSelectKnowledge: (knowledgeId: string) => void
}

const reviewStatusLabels: Readonly<Record<string, string>> = {
  draft: '草稿',
  pending: '待核验',
  retired: '已停用',
}

function nodeDisplayLabel(label: string, reviewStatus: string) {
  if (reviewStatus === 'reviewed') return label
  return `${label}\n${reviewStatusLabels[reviewStatus] ?? reviewStatus}`
}

function graphElements(
  projection: KnowledgeGraphProjection,
): ElementDefinition[] {
  return [
    ...projection.nodes.map((node) => ({
      data: {
        id: node.id,
        label: node.label,
        displayLabel: nodeDisplayLabel(node.label, node.reviewStatus),
        reviewStatus: node.reviewStatus,
      },
    })),
    ...projection.edges.map((edge) => ({
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.relationType,
        direction: edge.direction,
      },
    })),
  ]
}

function GraphNotice({ unavailable }: { readonly unavailable: boolean }) {
  return (
    <p className="knowledge-graph__notice" role="status">
      {unavailable
        ? '知识关系图暂时不可用。请继续使用目录、关系列表和知识详情。'
        : '当前图中没有可展示的已审核显式关系。'}
    </p>
  )
}

export function KnowledgeGraph({
  projection,
  onSelectKnowledge,
}: KnowledgeGraphProps) {
  const canvasRef = useRef<HTMLDivElement>(null)
  const [isUnavailable, setIsUnavailable] = useState(false)
  const hasEdges = projection.edges.length > 0
  const unavailable = hasEdges && isUnavailable

  useEffect(() => {
    if (!hasEdges || !canvasRef.current) return

    setIsUnavailable(false)
    let graph: cytoscape.Core | undefined

    try {
      graph = cytoscape({
        container: canvasRef.current,
        elements: graphElements(projection),
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
              width: 'label',
              height: 'label',
              padding: '12px',
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
        layout: {
          name: 'breadthfirst',
          animate: false,
          directed: true,
          padding: 32,
        },
      })
      graph.on('tap', 'node', (event) => {
        onSelectKnowledge(event.target.id())
      })
    } catch {
      // The surrounding knowledge explorer remains the usable non-graph path.
      setIsUnavailable(true)
    }

    return () => {
      graph?.destroy()
    }
  }, [hasEdges, onSelectKnowledge, projection])

  return (
    <section className="knowledge-graph" aria-labelledby="knowledge-graph-title">
      <header className="knowledge-graph__heading">
        <div>
          <p>当前发布 · {projection.release.knowledgeReleaseId}</p>
          <h2 id="knowledge-graph-title">知识关系图</h2>
        </div>
        <span>{projection.edges.length} 条已审核显式关系</span>
      </header>

      {!hasEdges || unavailable ? <GraphNotice unavailable={unavailable} /> : null}
      {hasEdges ? (
        <div
          aria-label="知识关系图"
          className="knowledge-graph__canvas"
          hidden={unavailable}
          ref={canvasRef}
          role="img"
        />
      ) : null}
    </section>
  )
}
