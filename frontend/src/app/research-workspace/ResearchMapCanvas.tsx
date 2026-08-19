import cytoscape, { type ElementDefinition } from 'cytoscape'
import {
  ArrowsOutIcon,
  CheckCircleIcon,
  CircleNotchIcon,
  ListBulletsIcon,
  MapTrifoldIcon,
  WarningCircleIcon,
  XCircleIcon,
  XIcon,
} from '@phosphor-icons/react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import type {
  ResearchCanvasNode,
  ResearchCanvasNodeKind,
  ResearchCanvasProjection,
  ResearchCanvasStatus,
} from '../../modules/research-workspace'
import './research-map-canvas.css'

type ResearchMapCanvasProps = {
  readonly projection: ResearchCanvasProjection
  readonly selectedNodeId?: string | null
  readonly onSelectNode?: (node: ResearchCanvasNode) => void
}

const statusLabels: Record<ResearchCanvasStatus, string> = {
  empty: '等待你的问题',
  thinking: 'Agent 正在理解',
  retrieving: '正在检索证据',
  answering: '正在形成综合',
  ready: '已形成初步结构',
  failed: '需要重新尝试',
  interrupted: '已中断',
}

const kindLabels: Record<ResearchCanvasNodeKind, string> = {
  question: '研究问题',
  tool: 'Agent 工具',
  evidence: '知识证据',
  synthesis: 'Agent 综合',
}

const statusIcon = (status: ResearchCanvasNode['status']) => {
  if (status === 'running') return <CircleNotchIcon size={14} className="research-map__node-status research-map__node-status--running" aria-label="进行中" />
  if (status === 'failed') return <XCircleIcon size={14} className="research-map__node-status research-map__node-status--failed" aria-label="失败" />
  if (status === 'interrupted') return <WarningCircleIcon size={14} className="research-map__node-status research-map__node-status--interrupted" aria-label="已中断" />
  return <CheckCircleIcon size={14} className="research-map__node-status research-map__node-status--complete" aria-label="已完成" />
}

function graphElements(projection: ResearchCanvasProjection): ElementDefinition[] {
  const byKind: Record<ResearchCanvasNodeKind, ResearchCanvasNode[]> = {
    question: [],
    tool: [],
    evidence: [],
    synthesis: [],
  }
  projection.nodes.forEach((node) => byKind[node.kind].push(node))
  const positions = new Map<string, { x: number; y: number }>()

  byKind.question.forEach((node, index) => positions.set(node.id, { x: 180, y: 145 + index * 170 }))
  byKind.tool.forEach((node, index) => positions.set(node.id, { x: 420, y: 105 + index * 125 }))
  byKind.evidence.forEach((node, index) => positions.set(node.id, { x: 680, y: 85 + index * 120 }))
  byKind.synthesis.forEach((node, index) => positions.set(node.id, { x: 930, y: 145 + index * 170 }))

  return [
    ...projection.nodes.map((node) => ({
      data: {
        id: node.id,
        label: graphNodeLabel(node),
        kind: node.kind,
        status: node.status,
      },
      position: positions.get(node.id) ?? { x: 180, y: 145 },
    })),
    ...projection.edges.map((edge) => ({
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.label ?? '',
      },
    })),
  ]
}

function graphNodeLabel(node: ResearchCanvasNode) {
  const limit = node.kind === 'question' ? 34 : 42
  return node.title.length > limit ? `${node.title.slice(0, limit)}…` : node.title
}

const graphStyle: cytoscape.StylesheetJson = [
  {
    selector: 'node',
    style: {
      'background-color': '#ffffff',
      'border-color': '#cfc9bd',
      'border-width': 1,
      color: '#24231f',
      'font-family': 'Inter, -apple-system, BlinkMacSystemFont, sans-serif',
      'font-size': 12,
      label: 'data(label)',
      'text-halign': 'center',
      'text-valign': 'center',
      'text-wrap': 'wrap',
      'text-max-width': '156px',
      width: 188,
      height: 66,
      padding: '8px',
      shape: 'round-rectangle',
    },
  },
  {
    selector: 'node[kind = "question"]',
    style: {
      'background-color': '#24231f',
      'border-color': '#24231f',
      color: '#ffffff',
      height: 82,
      width: 220,
      'font-size': 13,
    },
  },
  {
    selector: 'node[kind = "tool"]',
    style: {
      'background-color': '#f3f0e9',
      'border-color': '#d6c2a3',
      color: '#625644',
      'font-size': 11,
      height: 54,
      width: 168,
    },
  },
  {
    selector: 'node[kind = "evidence"]',
    style: {
      'background-color': '#f8f7f3',
      'border-color': '#b8c3ba',
      color: '#3e5143',
      height: 62,
      width: 196,
    },
  },
  {
    selector: 'node[kind = "synthesis"]',
    style: {
      'background-color': '#fff8f2',
      'border-color': '#bd735c',
      color: '#713d2f',
      height: 76,
      width: 200,
      'font-size': 13,
    },
  },
  {
    selector: 'node[status = "running"]',
    style: {
      'border-color': '#b98a43',
      'border-width': 2,
    },
  },
  {
    selector: 'node[status = "failed"]',
    style: {
      'border-color': '#b15d4a',
      'border-style': 'dashed',
      'border-width': 2,
    },
  },
  {
    selector: 'node[status = "interrupted"]',
    style: {
      'border-color': '#b25c45',
      'border-style': 'dashed',
      'border-width': 2,
    },
  },
  {
    selector: 'edge',
    style: {
      'curve-style': 'bezier',
      'line-color': '#d1ccc2',
      'target-arrow-color': '#d1ccc2',
      'target-arrow-shape': 'triangle',
      width: 1.6,
    },
  },
  {
    selector: ':selected',
    style: {
      'border-color': '#b25c45',
      'border-width': 3,
    },
  },
]

function MapEmptyState() {
  return (
    <div className="research-map__empty">
      <div className="research-map__empty-mark"><MapTrifoldIcon size={22} /></div>
      <h3>问题、证据和 Agent 综合会在这里形成可追溯的结构</h3>
      <p>先在右侧说出一个社会学问题。Agent 判断需要哪些工具后，本次会话返回的过程会逐步出现在研究地图中。</p>
      <div className="research-map__empty-flow" aria-label="研究地图工作方式">
        <span><b>01</b>提出问题</span>
        <i aria-hidden="true" />
        <span><b>02</b>检索或解释</span>
        <i aria-hidden="true" />
        <span><b>03</b>形成结构</span>
      </div>
    </div>
  )
}

export function ResearchMapCanvas({ projection, selectedNodeId, onSelectNode }: ResearchMapCanvasProps) {
  const [canvasElement, setCanvasElement] = useState<HTMLDivElement | null>(null)
  const graphRef = useRef<cytoscape.Core | null>(null)
  const projectionRef = useRef(projection)
  const onSelectNodeRef = useRef(onSelectNode)
  const [unavailable, setUnavailable] = useState(false)
  const [listOpen, setListOpen] = useState(false)
  const elements = useMemo(() => graphElements(projection), [projection])
  const elementsKey = useMemo(() => JSON.stringify(elements), [elements])
  const hasNodes = projection.nodes.length > 0

  projectionRef.current = projection
  onSelectNodeRef.current = onSelectNode

  const setCanvasRef = useCallback((element: HTMLDivElement | null) => {
    setCanvasElement(element)
  }, [])

  useEffect(() => {
    if (!canvasElement || graphRef.current) return
    setUnavailable(false)
    let graph: cytoscape.Core | undefined
    let fitFrame = 0
    try {
      graph = cytoscape({
        container: canvasElement,
        elements,
        style: graphStyle,
        layout: { name: 'preset', fit: true, padding: 70 },
        minZoom: 0.35,
        maxZoom: 2.2,
        userPanningEnabled: true,
        userZoomingEnabled: true,
      })
      graphRef.current = graph
      graph.on('tap', 'node', (event) => {
        const nodeId = event.target.id()
        const node = projectionRef.current.nodes.find((item) => item.id === nodeId)
        if (node) onSelectNodeRef.current?.(node)
      })
      if (typeof graph.resize === 'function') graph.resize()
      if (typeof graph.fit === 'function') graph.fit(graph.elements(), 70)
      fitFrame = globalThis.requestAnimationFrame?.(() => {
        if (!graph) return
        if (typeof graph.resize === 'function') graph.resize()
        if (typeof graph.fit === 'function') graph.fit(graph.elements(), 70)
      }) ?? 0
    } catch {
      setUnavailable(true)
    }
    return () => {
      if (fitFrame) globalThis.cancelAnimationFrame?.(fitFrame)
      graphRef.current = null
      graph?.destroy()
    }
  }, [canvasElement])

  useEffect(() => {
    const graph = graphRef.current
    if (!graph || !canvasElement) return
    const syncViewport = () => {
      if (typeof graph.resize === 'function') graph.resize()
    }
    syncViewport()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(syncViewport)
    observer.observe(canvasElement)
    return () => observer.disconnect()
  }, [canvasElement])

  useEffect(() => {
    const graph = graphRef.current
    if (!graph || !hasNodes) return
    let fitFrame = 0
    try {
      if (typeof graph.resize === 'function') graph.resize()
      graph.elements().remove()
      graph.add(JSON.parse(elementsKey) as ElementDefinition[])
      graph.layout({ name: 'preset', fit: true, padding: 70 }).run()
      if (typeof graph.resize === 'function') graph.resize()
      if (typeof graph.fit === 'function') graph.fit(graph.elements(), 70)
      fitFrame = globalThis.requestAnimationFrame?.(() => {
        if (typeof graph.resize === 'function') graph.resize()
        if (typeof graph.fit === 'function') graph.fit(graph.elements(), 70)
      }) ?? 0
    } catch {
      setUnavailable(true)
    }
    return () => {
      if (fitFrame) globalThis.cancelAnimationFrame?.(fitFrame)
    }
  }, [elementsKey, hasNodes])

  useEffect(() => {
    if (!listOpen) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setListOpen(false)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [listOpen])

  function fitGraph() {
    if (!graphRef.current) return
    if (typeof graphRef.current.resize === 'function') graphRef.current.resize()
    if (typeof graphRef.current.fit === 'function') graphRef.current.fit(graphRef.current.elements(), 70)
  }

  const selectedNode = projection.nodes.find((node) => node.id === selectedNodeId)

  return (
    <section className="research-map" aria-label="研究地图">
      <header className="research-map__header">
        <div className="research-map__heading">
          <span className="research-map__eyebrow"><MapTrifoldIcon size={14} />研究地图</span>
          <h2>{projection.question ? '研究结构' : '从问题开始，逐步形成结构'}</h2>
          <p>Agent 的工作过程会在这里留下可以回看的节点。</p>
        </div>
        <div className="research-map__header-actions">
          <span className={`research-map__status research-map__status--${projection.status}`}><i aria-hidden="true" />{statusLabels[projection.status]}</span>
          <button type="button" title="适应画布" aria-label="适应画布" onClick={fitGraph} disabled={!projection.nodes.length}><ArrowsOutIcon size={16} /></button>
          <button type="button" title="以列表查看" aria-label="以列表查看" aria-pressed={listOpen} onClick={() => setListOpen((value) => !value)} disabled={!projection.nodes.length}><ListBulletsIcon size={16} /></button>
        </div>
      </header>
      <div className="research-map__canvas-wrap">
        {projection.nodes.length === 0 ? <MapEmptyState /> : (
          <>
            <div ref={setCanvasRef} className="research-map__canvas" role="img" aria-label="可拖动的研究节点地图" hidden={unavailable} />
            {unavailable ? <p className="research-map__notice" role="alert">研究地图暂时不可用，下面的结构列表仍然可以继续查看。</p> : null}
            {selectedNode ? (
              <button type="button" className="research-map__selection" onClick={() => onSelectNode?.(selectedNode)}>
                <span>{kindLabels[selectedNode.kind]}</span>
                <strong>{selectedNode.title}</strong>
              </button>
            ) : null}
            {listOpen ? (
              <aside className="research-map__list" role="region" aria-label="研究节点列表">
                <div className="research-map__list-header">
                  <strong>研究节点</strong>
                  <button type="button" aria-label="关闭节点列表" title="关闭节点列表" onClick={() => setListOpen(false)}>
                    <XIcon size={15} />
                  </button>
                </div>
                <div className="research-map__list-items">
                  {projection.nodes.map((node) => (
                    <button type="button" key={node.id} className={node.id === selectedNodeId ? 'is-selected' : ''} onClick={() => onSelectNode?.(node)}>
                      {statusIcon(node.status)}
                      <span><small>{kindLabels[node.kind]}</small><strong>{node.title}</strong></span>
                    </button>
                  ))}
                </div>
              </aside>
            ) : null}
          </>
        )}
      </div>
      <footer className="research-map__footer">
        <span><b>{projection.nodes.length}</b> 个节点 · <b>{projection.edges.length}</b> 条关系</span>
        <span className="research-map__legend"><span><i className="is-question" />问题</span><span><i className="is-evidence" />证据</span><span><i className="is-synthesis" />Agent 综合</span></span>
      </footer>
    </section>
  )
}
