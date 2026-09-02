import {
  ArrowUpRightIcon,
  CrosshairIcon,
  ListBulletsIcon,
  PathIcon,
  QuotesIcon,
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
  type XYPosition,
} from '@xyflow/react'
import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import type {
  ResearchCanvasEdge,
  ResearchCanvasNode,
  ResearchCanvasNodeKind,
  ResearchCanvasProjection,
} from '../../modules/research-workspace'
import { ResearchAgentBot } from '../agent/ResearchAgentBot'
import { ResearchMapIdleShader } from './ResearchMapIdleShader'
import '@xyflow/react/dist/style.css'
import './research-map-canvas.css'

type ResearchMapCanvasProps = {
  readonly projection: ResearchCanvasProjection
  readonly idleActions?: ReactNode
  readonly selectedNodeId?: string | null
  readonly onSelectNode?: (node: ResearchCanvasNode) => void
  readonly onClearSelection?: () => void
  readonly onContinueNode?: (node: ResearchCanvasNode) => void
  readonly onOpenCitation?: (citationId: string) => void
  readonly expandedNodeContent?: Readonly<Record<string, ReactNode>>
}

type ArgumentNodeData = {
  node: ResearchCanvasNode
  onFocus: (node: ResearchCanvasNode) => void
  onContinue: (node: ResearchCanvasNode) => void
  sourcePosition?: Position
  targetPosition?: Position
}

type ArgumentFlowNode = Node<ArgumentNodeData, 'argument'>
type FocusDepth = 1 | 2 | 'all'

const elk = new ELK()
const EMPTY_EXPANDED_NODE_CONTENT: Readonly<Record<string, ReactNode>> = {}
const ExpandedNodeContentContext = createContext<Readonly<Record<string, ReactNode>>>(EMPTY_EXPANDED_NODE_CONTENT)

const kindLabels: Record<ResearchCanvasNodeKind, string> = {
  question: '研究问题',
  phenomenon: '核心现象',
  theory: '理论视角',
  claim: '核心主张',
  evidence: '经验依据',
  gap: '证据缺口',
  synthesis: '阶段综合',
  document: '研究章节',
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
  phenomenon: { width: 292, height: 154 },
  theory: { width: 250, height: 148 },
  claim: { width: 278, height: 154 },
  evidence: { width: 286, height: 172 },
  gap: { width: 250, height: 142 },
  synthesis: { width: 318, height: 176 },
  document: { width: 250, height: 128 },
}

function ArgumentNode({ data, selected }: NodeProps<ArgumentFlowNode>) {
  const { node } = data
  const expandedContent = useContext(ExpandedNodeContentContext)[node.id]
  if (expandedContent) {
    return (
      <article className="research-document-map-node is-expanded nodrag nowheel">
        <Handle type="target" position={data.targetPosition ?? Position.Left} className="research-argument-node__handle" />
        {expandedContent}
        <Handle type="source" position={data.sourcePosition ?? Position.Right} className="research-argument-node__handle" />
      </article>
    )
  }
  return (
    <article className={`research-argument-node is-${node.kind} ${selected ? 'is-selected' : ''}`}>
      <Handle type="target" position={data.targetPosition ?? Position.Left} className="research-argument-node__handle" />
      <NodeToolbar isVisible={selected} position={Position.Top} offset={10}>
        <div className="research-argument-node__toolbar">
          <button type="button" className="nodrag" onClick={() => data.onFocus(node)}><CrosshairIcon size={13} />聚焦</button>
          <button type="button" className="nodrag" onClick={() => data.onContinue(node)}>继续研究<ArrowUpRightIcon size={13} /></button>
        </div>
      </NodeToolbar>
      {node.kind !== 'document' ? <div className="research-argument-node__meta">
        <span>{node.kind === 'evidence' ? <QuotesIcon size={13} /> : <PathIcon size={13} />}{kindLabels[node.kind]}</span>
        <i className={`is-${node.status}`}>{nodeStatusLabels[node.status]}</i>
      </div> : null}
      <h3>{node.title}</h3>
      {node.summary ? <p>{node.summary}</p> : null}
      {node.kind !== 'document' ? <footer>
        <span>{node.citationIds.length ? `${node.citationIds.length} 条依据` : node.kind === 'gap' ? '等待补证' : 'Agent 结构化'}</span>
        <b aria-hidden="true" />
      </footer> : null}
      <Handle type="source" position={data.sourcePosition ?? Position.Right} className="research-argument-node__handle" />
    </article>
  )
}

const nodeTypes = { argument: ArgumentNode }

function MapIdleNote({ actions }: { readonly actions?: ReactNode }) {
  return (
    <div className="research-map__idle-state">
      <div className="research-map__idle-content">
        <ResearchAgentBot />
        <div className="research-map__idle-note" aria-label="画布说明">
          <h1>从一个社会学问题开始</h1>
          <p>对话中形成的研究结构会在这里展开。</p>
          {actions}
        </div>
      </div>
    </div>
  )
}

export function ResearchMapCanvas({
  projection,
  idleActions,
  selectedNodeId = null,
  onSelectNode,
  onClearSelection,
  onContinueNode,
  onOpenCitation,
  expandedNodeContent = EMPTY_EXPANDED_NODE_CONTENT,
}: ResearchMapCanvasProps) {
  const [flowNodes, setFlowNodes] = useState<ArgumentFlowNode[]>([])
  const [flowEdges, setFlowEdges] = useState<Edge[]>([])
  const [listOpen, setListOpen] = useState(false)
  const [focusDepth, setFocusDepth] = useState<FocusDepth>('all')
  const [layoutPending, setLayoutPending] = useState(false)
  const flowRef = useRef<ReactFlowInstance<ArgumentFlowNode, Edge> | null>(null)
  const layoutGeneration = useRef(0)
  const onSelectNodeRef = useRef(onSelectNode)
  const onContinueNodeRef = useRef(onContinueNode)
  onSelectNodeRef.current = onSelectNode
  onContinueNodeRef.current = onContinueNode

  const selectedNode = projection.nodes.find((node) => node.id === selectedNodeId) ?? null
  const hasDocumentNodes = projection.nodes.some((node) => node.kind === 'document')
  const focusedDocumentContent = Object.values(expandedNodeContent)[0] ?? null
  const visibleProjection = useMemo(
    () => filterProjection(projection, selectedNodeId, focusDepth),
    [focusDepth, projection, selectedNodeId],
  )
  const graphSignature = useMemo(
    () => JSON.stringify({
      nodes: visibleProjection.nodes.map((node) => [node.id, node.kind, node.title, node.summary, node.status, node.citationIds]),
      edges: visibleProjection.edges.map((edge) => [edge.id, edge.source, edge.target, edge.relation, edge.label]),
      expanded: Object.keys(expandedNodeContent).sort(),
    }),
    [expandedNodeContent, visibleProjection],
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
    const expandedNodeIds = new Set(Object.keys(expandedNodeContent))
    void layoutArgumentMap(visibleProjection.nodes, visibleProjection.edges, expandedNodeIds).then(({ nodes, edges }) => {
      if (layoutGeneration.current !== generation) return
      setFlowNodes(nodes.map((node) => ({
        ...node,
        selected: node.id === selectedNodeId,
        data: {
          ...node.data,
          onFocus: (value) => {
            onSelectNodeRef.current?.(value)
            setFocusDepth(1)
          },
          onContinue: (value) => onContinueNodeRef.current?.(value),
        },
      })))
      setFlowEdges(edges)
      setLayoutPending(false)
      globalThis.requestAnimationFrame?.(() => {
        const expandedNodes = nodes.filter((node) => expandedNodeIds.has(node.id))
        flowRef.current?.fitView({
          nodes,
          padding: expandedNodes.length ? 0.12 : 0.2,
          maxZoom: expandedNodes.length ? 0.72 : undefined,
          duration: 380,
        })
      })
    }).catch(() => {
      if (layoutGeneration.current === generation) setLayoutPending(false)
    })
  }, [graphSignature, selectedNodeId, visibleProjection.edges, visibleProjection.nodes])

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
      <div className={`research-map__canvas-wrap${projection.nodes.length ? '' : ' is-empty'}`}>
        {!projection.nodes.length ? <ResearchMapIdleShader /> : null}
        {focusedDocumentContent ? (
          <div className="research-map__document-focus">
            <article className="research-document-map-node is-expanded nodrag nowheel">
              {focusedDocumentContent}
            </article>
          </div>
        ) : (
        <ExpandedNodeContentContext.Provider value={expandedNodeContent}>
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
          aria-label={projection.nodes.length ? '可缩放、可拖动的社会学论证地图' : '空白研究画布'}
        >
          <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#d8d6cf" />
          {projection.nodes.length ? <Controls position="bottom-left" showInteractive={false} /> : null}
          {!hasDocumentNodes && projection.nodes.length >= 16 ? (
            <MiniMap
              position="bottom-left"
              pannable
              zoomable
              nodeColor={(node) => minimapColor((node.data as ArgumentNodeData).node.kind)}
              maskColor="rgb(247 247 244 / 72%)"
            />
          ) : null}
        </ReactFlow>
        </ExpandedNodeContentContext.Provider>
        )}
        {!projection.nodes.length ? <MapIdleNote actions={idleActions} /> : null}
        {projection.nodes.length && !hasDocumentNodes ? (
          <>
            {layoutPending ? <div className="research-map__layout-status" role="status">正在整理结构…</div> : null}

            <div className="research-map__toolbar">
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
              <button className="research-map__directory-toggle" type="button" title="节点目录" aria-label="打开节点目录" aria-pressed={listOpen} onClick={() => setListOpen((value) => !value)}><ListBulletsIcon size={16} /></button>
            </div>

            {selectedNode && selectedNode.kind !== 'document' ? (
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
        ) : null}
      </div>

    </section>
  )
}

async function layoutArgumentMap(
  nodes: ResearchCanvasNode[],
  edges: ResearchCanvasEdge[],
  expandedNodeIds = new Set<string>(),
): Promise<{ nodes: ArgumentFlowNode[]; edges: Edge[] }> {
  const expandedNodeId = nodes.find((node) => expandedNodeIds.has(node.id))?.id
  const compactNodes = nodes.filter((node) => node.id !== expandedNodeId)
  const result = expandedNodeId ? {
    children: nodes.map((node) => node.id === expandedNodeId
      ? { id: node.id, x: 0, y: 0 }
      : { id: node.id, x: 770, y: compactNodes.findIndex((item) => item.id === node.id) * 164 }),
  } : await elk.layout({
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
  const positions = new Map<string, XYPosition>(
    (result.children ?? []).map((child): [string, XYPosition] => [
      child.id,
      { x: child.x ?? 0, y: child.y ?? 0 },
    ]),
  )
  return {
    nodes: nodes.map((node) => ({
      id: node.id,
      type: 'argument',
      position: positions.get(node.id) ?? { x: 0, y: 0 },
      data: {
        node,
        onFocus: () => undefined,
        onContinue: () => undefined,
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      },
      style: expandedNodeIds.has(node.id) ? { width: 680, height: 820 } : nodeDimensions[node.kind],
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      ariaLabel: `${kindLabels[node.kind]}：${node.title}`,
    })),
    edges: (expandedNodeId ? [] : edges).map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: 'smoothstep',
      label: edge.label === '' ? undefined : edge.label || relationLabels[edge.relation],
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
  if (kind === 'phenomenon') return '#9a7742'
  if (kind === 'theory') return '#6c7b89'
  if (kind === 'claim') return '#4f6f60'
  if (kind === 'evidence') return '#8b988e'
  if (kind === 'gap') return '#aa6755'
  if (kind === 'document') return '#2f312e'
  return '#765f84'
}
