import {
  ArrowsOutIcon,
  ArrowUpRightIcon,
  CrosshairIcon,
  ListBulletsIcon,
  MapTrifoldIcon,
  PathIcon,
  QuotesIcon,
  TreeStructureIcon,
  XIcon,
} from '@phosphor-icons/react'
import ELK from 'elkjs/lib/elk.bundled.js'
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  NodeToolbar,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
} from '@xyflow/react'
import { useEffect, useMemo, useRef, useState } from 'react'

import type {
  ResearchCanvasEdge,
  ResearchCanvasNode,
  ResearchCanvasNodeKind,
  ResearchCanvasProjection,
  ResearchCanvasStatus,
} from '../../modules/research-workspace'
import '@xyflow/react/dist/style.css'
import './research-map-canvas.css'

type ResearchMapCanvasProps = {
  readonly projection: ResearchCanvasProjection
  readonly selectedNodeId?: string | null
  readonly onSelectNode?: (node: ResearchCanvasNode) => void
  readonly onClearSelection?: () => void
  readonly onContinueNode?: (node: ResearchCanvasNode) => void
  readonly onOpenCitation?: (citationId: string) => void
}

type ArgumentNodeData = {
  node: ResearchCanvasNode
  onFocus: (node: ResearchCanvasNode) => void
  onContinue: (node: ResearchCanvasNode) => void
}

type ArgumentFlowNode = Node<ArgumentNodeData, 'argument'>
type FocusDepth = 1 | 2 | 'all'

const elk = new ELK()

const statusLabels: Record<ResearchCanvasStatus, string> = {
  empty: '等待研究问题',
  thinking: 'Agent 正在建模',
  retrieving: '正在核对证据',
  answering: '正在形成论证',
  ready: '论证结构已同步',
  failed: '本轮未完成',
  interrupted: '本轮已中断',
}

const kindLabels: Record<ResearchCanvasNodeKind, string> = {
  question: '研究问题',
  theory: '理论视角',
  claim: '核心主张',
  evidence: '经验依据',
  gap: '证据缺口',
  synthesis: '阶段综合',
}

const nodeStatusLabels: Record<ResearchCanvasNode['status'], string> = {
  developing: '形成中',
  grounded: '已有依据',
  open: '待处理',
  verified: '已核验',
  challenged: '有争议',
  complete: '已完成',
}

const relationLabels: Record<ResearchCanvasEdge['relation'], string> = {
  explains: '解释',
  supports: '支持',
  challenges: '质疑',
  derives: '推导',
  refines: '细化',
}

const nodeDimensions: Record<ResearchCanvasNodeKind, { width: number; height: number }> = {
  question: { width: 310, height: 126 },
  theory: { width: 250, height: 148 },
  claim: { width: 278, height: 154 },
  evidence: { width: 286, height: 172 },
  gap: { width: 250, height: 142 },
  synthesis: { width: 318, height: 176 },
}

function ArgumentNode({ data, selected }: NodeProps<ArgumentFlowNode>) {
  const { node } = data
  return (
    <article className={`research-argument-node is-${node.kind} ${selected ? 'is-selected' : ''}`}>
      <Handle type="target" position={Position.Left} className="research-argument-node__handle" />
      <NodeToolbar isVisible={selected} position={Position.Top} offset={10}>
        <div className="research-argument-node__toolbar">
          <button type="button" className="nodrag" onClick={() => data.onFocus(node)}><CrosshairIcon size={13} />聚焦</button>
          <button type="button" className="nodrag" onClick={() => data.onContinue(node)}>继续研究<ArrowUpRightIcon size={13} /></button>
        </div>
      </NodeToolbar>
      <div className="research-argument-node__meta">
        <span>{node.kind === 'evidence' ? <QuotesIcon size={13} /> : <PathIcon size={13} />}{kindLabels[node.kind]}</span>
        <i className={`is-${node.status}`}>{nodeStatusLabels[node.status]}</i>
      </div>
      <h3>{node.title}</h3>
      {node.summary ? <p>{node.summary}</p> : null}
      <footer>
        <span>{node.citationIds.length ? `${node.citationIds.length} 条依据` : node.kind === 'gap' ? '等待补证' : 'Agent 结构化'}</span>
        <b aria-hidden="true" />
      </footer>
      <Handle type="source" position={Position.Right} className="research-argument-node__handle" />
    </article>
  )
}

const nodeTypes = { argument: ArgumentNode }

function MapEmptyState() {
  return (
    <div className="research-map__empty">
      <div className="research-map__empty-mark"><TreeStructureIcon size={24} /></div>
      <span>ARGUMENT MAP</span>
      <h3>从一个值得追问的社会学问题开始</h3>
      <p>Agent 会在真实对话中识别理论、主张、证据与缺口。只有通过研究工具确认的结构才会进入画布。</p>
      <div className="research-map__empty-spine" aria-label="论证地图结构">
        <span>问题</span><i /><span>理论</span><i /><span>主张</span><i /><span>证据</span><i /><span>综合</span>
      </div>
    </div>
  )
}

export function ResearchMapCanvas({
  projection,
  selectedNodeId = null,
  onSelectNode,
  onClearSelection,
  onContinueNode,
  onOpenCitation,
}: ResearchMapCanvasProps) {
  const [flowNodes, setFlowNodes] = useState<ArgumentFlowNode[]>([])
  const [flowEdges, setFlowEdges] = useState<Edge[]>([])
  const [listOpen, setListOpen] = useState(false)
  const [focusDepth, setFocusDepth] = useState<FocusDepth>('all')
  const [layoutPending, setLayoutPending] = useState(false)
  const flowRef = useRef<ReactFlowInstance<ArgumentFlowNode, Edge> | null>(null)
  const layoutGeneration = useRef(0)

  const selectedNode = projection.nodes.find((node) => node.id === selectedNodeId) ?? null
  const visibleProjection = useMemo(
    () => filterProjection(projection, selectedNodeId, focusDepth),
    [focusDepth, projection, selectedNodeId],
  )
  const graphSignature = useMemo(
    () => JSON.stringify({
      nodes: visibleProjection.nodes.map((node) => [node.id, node.kind, node.title, node.summary, node.status, node.citationIds]),
      edges: visibleProjection.edges.map((edge) => [edge.id, edge.source, edge.target, edge.relation, edge.label]),
    }),
    [visibleProjection],
  )

  useEffect(() => {
    if (!visibleProjection.nodes.length) {
      setFlowNodes([])
      setFlowEdges([])
      return
    }
    const generation = layoutGeneration.current + 1
    layoutGeneration.current = generation
    setLayoutPending(true)
    void layoutArgumentMap(visibleProjection.nodes, visibleProjection.edges).then(({ nodes, edges }) => {
      if (layoutGeneration.current !== generation) return
      setFlowNodes(nodes.map((node) => ({
        ...node,
        selected: node.id === selectedNodeId,
        data: {
          ...node.data,
          onFocus: (value) => {
            onSelectNode?.(value)
            setFocusDepth(1)
          },
          onContinue: (value) => onContinueNode?.(value),
        },
      })))
      setFlowEdges(edges)
      setLayoutPending(false)
      globalThis.requestAnimationFrame?.(() => flowRef.current?.fitView({ padding: 0.2, duration: 380 }))
    }).catch(() => {
      if (layoutGeneration.current === generation) setLayoutPending(false)
    })
  }, [graphSignature, onContinueNode, onSelectNode, selectedNodeId, visibleProjection.edges, visibleProjection.nodes])

  useEffect(() => {
    setFlowNodes((nodes) => nodes.map((node) => ({ ...node, selected: node.id === selectedNodeId })))
  }, [selectedNodeId])

  useEffect(() => {
    if (!listOpen) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setListOpen(false)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [listOpen])

  const counts = useMemo(() => Object.fromEntries(
    Object.keys(kindLabels).map((kind) => [kind, projection.nodes.filter((node) => node.kind === kind).length]),
  ) as Record<ResearchCanvasNodeKind, number>, [projection.nodes])

  function selectNode(node: ResearchCanvasNode) {
    onSelectNode?.(node)
  }

  function clearSelection() {
    setFocusDepth('all')
    onClearSelection?.()
  }

  return (
    <section className="research-map" aria-label="研究论证地图">
      <header className="research-map__header">
        <div className="research-map__heading">
          <span className="research-map__eyebrow"><MapTrifoldIcon size={14} />研究论证地图</span>
          <h2>{projection.question || '从问题开始，形成可检验的论证结构'}</h2>
          <p>不是聊天摘要。这里仅保留 Agent 明确建立的问题、理论、主张、证据与缺口。</p>
        </div>
        <div className="research-map__header-actions">
          <span className={`research-map__status research-map__status--${projection.status}`}><i aria-hidden="true" />{statusLabels[projection.status]}</span>
          <button type="button" title="适应画布" aria-label="适应画布" onClick={() => flowRef.current?.fitView({ padding: 0.2, duration: 300 })} disabled={!projection.nodes.length}><ArrowsOutIcon size={16} /></button>
          <button type="button" title="节点目录" aria-label="打开节点目录" aria-pressed={listOpen} onClick={() => setListOpen((value) => !value)} disabled={!projection.nodes.length}><ListBulletsIcon size={16} /></button>
        </div>
      </header>

      <div className="research-map__canvas-wrap">
        {!projection.nodes.length ? <MapEmptyState /> : (
          <>
            <ReactFlow<ArgumentFlowNode, Edge>
              nodes={flowNodes}
              edges={flowEdges}
              nodeTypes={nodeTypes}
              onInit={(instance) => { flowRef.current = instance }}
              onNodeClick={(_, flowNode) => selectNode(flowNode.data.node)}
              onNodeDoubleClick={(_, flowNode) => onContinueNode?.(flowNode.data.node)}
              onPaneClick={clearSelection}
              nodesDraggable
              nodesConnectable={false}
              elementsSelectable
              fitView
              minZoom={0.28}
              maxZoom={1.7}
              proOptions={{ hideAttribution: true }}
              aria-label="可缩放、可拖动的社会学论证地图"
            >
              <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#d8d6cf" />
              <Controls position="bottom-left" showInteractive={false} />
              {projection.nodes.length >= 6 ? (
                <MiniMap
                  position="bottom-left"
                  pannable
                  zoomable
                  nodeColor={(node) => minimapColor((node.data as ArgumentNodeData).node.kind)}
                  maskColor="rgb(247 247 244 / 72%)"
                />
              ) : null}
            </ReactFlow>
            <div className="research-map__spine-label" aria-hidden="true"><TreeStructureIcon size={14} />论证脊柱</div>
            {layoutPending ? <div className="research-map__layout-status" role="status">正在整理结构…</div> : null}

            <nav className="research-map__depth" aria-label="画布聚焦层级">
              <span>视野</span>
              {([1, 2, 'all'] as const).map((depth) => (
                <button
                  key={depth}
                  type="button"
                  className={focusDepth === depth ? 'is-active' : ''}
                  disabled={depth !== 'all' && !selectedNode}
                  aria-pressed={focusDepth === depth}
                  onClick={() => setFocusDepth(depth)}
                >{depth === 'all' ? '全部' : `${depth} 跳`}</button>
              ))}
            </nav>

            {selectedNode ? (
              <aside className="research-map__inspector" aria-label="节点检查器">
                <header><span>{kindLabels[selectedNode.kind]}</span><button type="button" aria-label="关闭节点检查器" onClick={clearSelection}><XIcon size={15} /></button></header>
                <div className={`research-map__inspector-mark is-${selectedNode.kind}`}><PathIcon size={17} /></div>
                <h3>{selectedNode.title}</h3>
                <p>{selectedNode.summary || '这个节点暂时没有补充说明。你可以让 Agent 继续拆解或补证。'}</p>
                <dl>
                  <div><dt>状态</dt><dd>{nodeStatusLabels[selectedNode.status]}</dd></div>
                  <div><dt>连接</dt><dd>{connectionCount(projection.edges, selectedNode.id)} 条关系</dd></div>
                  <div><dt>依据</dt><dd>{selectedNode.citationIds.length ? `${selectedNode.citationIds.length} 条` : '尚未绑定'}</dd></div>
                </dl>
                {selectedNode.citationIds.length ? (
                  <div className="research-map__inspector-citations">
                    {selectedNode.citationIds.map((id, index) => <button type="button" key={id} onClick={() => onOpenCitation?.(id)}>依据 {index + 1}<ArrowUpRightIcon size={12} /></button>)}
                  </div>
                ) : null}
                <button type="button" className="research-map__inspector-primary" onClick={() => onContinueNode?.(selectedNode)}>让 Agent 继续推进<ArrowUpRightIcon size={14} /></button>
              </aside>
            ) : null}

            {listOpen ? (
              <aside className="research-map__list" role="region" aria-label="研究节点目录">
                <div className="research-map__list-header"><div><span>结构目录</span><strong>{projection.nodes.length} 个研究节点</strong></div><button type="button" aria-label="关闭节点目录" onClick={() => setListOpen(false)}><XIcon size={15} /></button></div>
                <div className="research-map__list-groups">
                  {(Object.keys(kindLabels) as ResearchCanvasNodeKind[]).map((kind) => counts[kind] ? (
                    <section key={kind}>
                      <h3>{kindLabels[kind]}<span>{counts[kind]}</span></h3>
                      {projection.nodes.filter((node) => node.kind === kind).map((node) => (
                        <button type="button" key={node.id} className={node.id === selectedNodeId ? 'is-selected' : ''} onClick={() => selectNode(node)}><i className={`is-${kind}`} /><span>{node.title}</span></button>
                      ))}
                    </section>
                  ) : null)}
                </div>
              </aside>
            ) : null}
          </>
        )}
      </div>

      <footer className="research-map__footer">
        <span><b>{projection.nodes.length}</b> 个节点 · <b>{projection.edges.length}</b> 条论证关系</span>
        <span className="research-map__legend"><span><i className="is-theory" />理论</span><span><i className="is-claim" />主张</span><span><i className="is-evidence" />证据</span><span><i className="is-gap" />缺口</span></span>
      </footer>
    </section>
  )
}

async function layoutArgumentMap(
  nodes: ResearchCanvasNode[],
  edges: ResearchCanvasEdge[],
): Promise<{ nodes: ArgumentFlowNode[]; edges: Edge[] }> {
  const result = await elk.layout({
    id: 'research-map',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': 'RIGHT',
      'elk.alignment': 'CENTER',
      'elk.edgeRouting': 'ORTHOGONAL',
      'elk.layered.spacing.nodeNodeBetweenLayers': '118',
      'elk.spacing.nodeNode': '54',
      'elk.spacing.edgeNode': '26',
      'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
      'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
    },
    children: nodes.map((node) => ({ id: node.id, ...nodeDimensions[node.kind] })),
    edges: edges.map((edge) => ({ id: edge.id, sources: [edge.source], targets: [edge.target] })),
  })
  const positions = new Map((result.children ?? []).map((child) => [child.id, { x: child.x ?? 0, y: child.y ?? 0 }]))
  return {
    nodes: nodes.map((node) => ({
      id: node.id,
      type: 'argument',
      position: positions.get(node.id) ?? { x: 0, y: 0 },
      data: { node, onFocus: () => undefined, onContinue: () => undefined },
      style: nodeDimensions[node.kind],
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      ariaLabel: `${kindLabels[node.kind]}：${node.title}`,
    })),
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: 'smoothstep',
      label: edge.label || relationLabels[edge.relation],
      markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: relationColor(edge.relation) },
      style: {
        stroke: relationColor(edge.relation),
        strokeWidth: edge.relation === 'challenges' ? 1.8 : 1.45,
        strokeDasharray: edge.relation === 'challenges' || edge.relation === 'refines' ? '6 5' : undefined,
      },
      labelStyle: { fill: '#78766f', fontSize: 10, fontWeight: 600 },
      labelBgStyle: { fill: '#f7f7f4', fillOpacity: 0.94 },
      labelBgPadding: [5, 3],
      labelBgBorderRadius: 4,
    })),
  }
}

function filterProjection(
  projection: ResearchCanvasProjection,
  selectedNodeId: string | null,
  depth: FocusDepth,
): ResearchCanvasProjection {
  if (!selectedNodeId || depth === 'all') return projection
  const visible = new Set([selectedNodeId])
  let frontier = new Set([selectedNodeId])
  for (let step = 0; step < depth; step += 1) {
    const next = new Set<string>()
    for (const edge of projection.edges) {
      if (frontier.has(edge.source)) next.add(edge.target)
      if (frontier.has(edge.target)) next.add(edge.source)
    }
    for (const id of next) visible.add(id)
    frontier = next
  }
  return {
    ...projection,
    nodes: projection.nodes.filter((node) => visible.has(node.id)),
    edges: projection.edges.filter((edge) => visible.has(edge.source) && visible.has(edge.target)),
  }
}

function connectionCount(edges: ResearchCanvasEdge[], nodeId: string) {
  return edges.filter((edge) => edge.source === nodeId || edge.target === nodeId).length
}

function relationColor(relation: ResearchCanvasEdge['relation']) {
  if (relation === 'supports') return '#5d7869'
  if (relation === 'challenges') return '#a75b49'
  if (relation === 'derives') return '#5c7184'
  if (relation === 'refines') return '#9a7742'
  return '#9a9a92'
}

function minimapColor(kind: ResearchCanvasNodeKind) {
  if (kind === 'question') return '#292d2a'
  if (kind === 'theory') return '#6c7b89'
  if (kind === 'claim') return '#4f6f60'
  if (kind === 'evidence') return '#8b988e'
  if (kind === 'gap') return '#aa6755'
  return '#765f84'
}
