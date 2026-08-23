import type {
  AgentConversation,
  AgentResearchMap,
  AgentResearchMapNode,
  AgentResearchMapPatch,
  AgentResearchMapRelation,
  AgentResearchNodeKind,
  AgentResearchNodeStatus,
  AgentToolStep,
} from '../research-agent'

export type ResearchCanvasStatus =
  | 'empty'
  | 'thinking'
  | 'retrieving'
  | 'answering'
  | 'ready'
  | 'failed'
  | 'interrupted'

export type ResearchCanvasNodeKind = AgentResearchNodeKind | 'phenomenon' | 'document'
export type ResearchCanvasNodeStatus = AgentResearchNodeStatus

type ResearchCanvasToolStep = AgentToolStep & { interrupted?: boolean }

export type ResearchCanvasNode = {
  id: string
  kind: ResearchCanvasNodeKind
  title: string
  excerpt?: string | null
  summary?: string | null
  status: ResearchCanvasNodeStatus
  provenance: 'agent' | 'knowledge' | 'user'
  citationId?: string
  citationIds: string[]
  turnId?: string
}

export type ResearchCanvasEdge = {
  id: string
  source: string
  target: string
  relation: AgentResearchMapRelation['relation']
  label?: string | null
}

export type ResearchCanvasProjection = {
  status: ResearchCanvasStatus
  question: string | null
  nodes: ResearchCanvasNode[]
  edges: ResearchCanvasEdge[]
}

export type ResearchCanvasStreamingTurn = {
  question: string
  answer: string
  citations: import('../research-agent').AgentCitation[]
  toolSteps: ResearchCanvasToolStep[]
  canvasPatches: AgentResearchMapPatch[]
  interrupted?: boolean
  failure?: string
}

export function createEmptyResearchCanvasProjection(): ResearchCanvasProjection {
  return { status: 'empty', nodes: [], edges: [], question: null }
}

export function projectResearchCanvas({
  conversation,
  streamingTurn,
}: {
  conversation: AgentConversation | null
  streamingTurn?: ResearchCanvasStreamingTurn | null
}): ResearchCanvasProjection {
  let map = conversationMap(conversation)
  for (const patch of streamingTurn?.canvasPatches ?? []) map = applyPatch(map, patch)

  const nodes = map.nodes.map((node) => toCanvasNode(node, conversation))
  const edges = map.relations.map((relation) => ({
    id: relation.id,
    source: relation.source,
    target: relation.target,
    relation: relation.relation,
    ...(relation.label ? { label: relation.label } : {}),
  }))
  return {
    status: inferStatus({ conversation, streamingTurn, nodes }),
    question: streamingTurn?.question ?? latestQuestion(conversation),
    nodes,
    edges,
  }
}

function conversationMap(conversation: AgentConversation | null): AgentResearchMap {
  if (conversation?.research_map?.schema_version === 1) return conversation.research_map
  let map: AgentResearchMap = { schema_version: 1, nodes: [], relations: [] }
  for (const turn of conversation?.turns ?? []) {
    for (const patch of turn.canvas_patches ?? []) map = applyPatch(map, patch)
  }
  return map
}

function applyPatch(map: AgentResearchMap, patch: AgentResearchMapPatch): AgentResearchMap {
  const nodes = new Map(map.nodes.map((node) => [node.id, node]))
  const relations = new Map(map.relations.map((relation) => [relation.id, relation]))
  for (const id of patch.remove_node_ids) nodes.delete(id)
  for (const id of patch.remove_relation_ids) relations.delete(id)
  for (const node of patch.nodes) nodes.set(node.id, node)
  for (const relation of patch.relations) relations.set(relation.id, relation)
  const valid = new Set(nodes.keys())
  return {
    schema_version: 1,
    nodes: [...nodes.values()],
    relations: [...relations.values()].filter((relation) => valid.has(relation.source) && valid.has(relation.target)),
  }
}

function toCanvasNode(node: AgentResearchMapNode, conversation: AgentConversation | null): ResearchCanvasNode {
  const turnId = conversation?.turns.find((turn) =>
    (turn.canvas_patches ?? []).some((patch) => patch.nodes.some((item) => item.id === node.id)),
  )?.turn_id
  return {
    id: node.id,
    kind: node.kind,
    title: node.title,
    excerpt: node.summary ?? null,
    summary: node.summary ?? null,
    status: node.status,
    provenance: node.kind === 'evidence' ? 'knowledge' : node.kind === 'question' ? 'user' : 'agent',
    citationId: node.citation_ids[0],
    citationIds: [...node.citation_ids],
    turnId,
  }
}

function latestQuestion(conversation: AgentConversation | null): string | null {
  return conversation?.turns.at(-1)?.user.content ?? null
}

function inferStatus({
  conversation,
  streamingTurn,
  nodes,
}: {
  conversation: AgentConversation | null
  streamingTurn?: ResearchCanvasStreamingTurn | null
  nodes: ResearchCanvasNode[]
}): ResearchCanvasStatus {
  if (streamingTurn?.failure) return 'failed'
  if (streamingTurn?.interrupted) return 'interrupted'
  if (streamingTurn?.toolSteps.some((step) => step.status === 'running')) return 'retrieving'
  if (streamingTurn) return streamingTurn.answer.trim() ? 'answering' : 'thinking'
  if (conversation?.turns.length || nodes.length) return 'ready'
  return 'empty'
}
