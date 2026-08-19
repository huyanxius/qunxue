import type {
  AgentCitation,
  AgentConversation,
  AgentToolStep,
} from '../research-agent'

const toolLabels: Record<string, string> = {
  search_knowledge: '检索知识库',
  read_knowledge_entry: '读取知识条目',
  read_sources: '读取来源',
  browse_knowledge_directory: '浏览知识目录',
}

export type ResearchCanvasStatus =
  | 'empty'
  | 'thinking'
  | 'retrieving'
  | 'answering'
  | 'ready'
  | 'failed'
  | 'interrupted'

export type ResearchCanvasNodeKind = 'question' | 'tool' | 'evidence' | 'synthesis'

export type ResearchCanvasNodeStatus = 'running' | 'complete' | 'failed' | 'interrupted'

type ResearchCanvasToolStep = AgentToolStep & { interrupted?: boolean }

export type ResearchCanvasNode = {
  id: string
  kind: ResearchCanvasNodeKind
  title: string
  excerpt?: string | null
  status: ResearchCanvasNodeStatus
  provenance: 'user' | 'agent' | 'knowledge' | 'tool'
  citationId?: string
  turnId?: string
}

export type ResearchCanvasEdge = {
  id: string
  source: string
  target: string
  label?: string
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
  citations: AgentCitation[]
  toolSteps: ResearchCanvasToolStep[]
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
  const nodes = new Map<string, ResearchCanvasNode>()
  const edges = new Map<string, ResearchCanvasEdge>()

  const addNode = (node: ResearchCanvasNode) => {
    nodes.set(node.id, node)
  }
  const addEdge = (source: string, target: string, label?: string) => {
    if (!nodes.has(source) || !nodes.has(target)) return
    const id = `${source}->${target}`
    edges.set(id, { id, source, target, ...(label ? { label } : {}) })
  }

  for (const turn of conversation?.turns ?? []) {
    addPersistedTurn(turn, addNode, addEdge)
  }

  if (streamingTurn) {
    const questionId = 'question:streaming'
    addNode({
      id: questionId,
      kind: 'question',
      title: streamingTurn.question,
      status: streamingTurn.failure
        ? 'failed'
        : streamingTurn.interrupted
          ? 'interrupted'
          : 'running',
      provenance: 'user',
    })
    for (const step of streamingTurn.toolSteps) {
      addToolNode(step, addNode)
      addEdge(questionId, `tool:${step.id}`, '调用')
    }
    for (const citation of streamingTurn.citations) {
      addEvidenceNode(citation, undefined, addNode)
    }
    if (streamingTurn.answer.trim()) {
      const synthesisId = 'synthesis:streaming'
      addNode({
        id: synthesisId,
        kind: 'synthesis',
        title: 'Agent 综合',
        excerpt: streamingTurn.answer,
        status: streamingTurn.failure
          ? 'failed'
          : streamingTurn.interrupted
            ? 'interrupted'
            : 'running',
        provenance: 'agent',
      })
      addEdge(questionId, synthesisId, '形成综合')
      for (const citation of streamingTurn.citations) {
        addEdge(`evidence:${citation.citation_id}`, synthesisId, '依据')
      }
      for (const step of streamingTurn.toolSteps) {
        addEdge(`tool:${step.id}`, synthesisId, '返回')
      }
    }
  }

  const status = inferStatus({ conversation, streamingTurn, nodes: [...nodes.values()] })
  const latestQuestion = streamingTurn?.question
    ?? conversation?.turns.at(-1)?.user.content
    ?? null

  return {
    status,
    question: latestQuestion,
    nodes: [...nodes.values()],
    edges: [...edges.values()],
  }
}

function addPersistedTurn(
  turn: AgentConversation['turns'][number],
  addNode: (node: ResearchCanvasNode) => void,
  addEdge: (source: string, target: string, label?: string) => void,
) {
  const questionId = `question:${turn.turn_id}`
  const synthesisId = `synthesis:${turn.turn_id}`
  addNode({
    id: questionId,
    kind: 'question',
    title: turn.user.content,
    status: 'complete',
    provenance: 'user',
    turnId: turn.turn_id,
  })
  addNode({
    id: synthesisId,
    kind: 'synthesis',
    title: 'Agent 综合',
    excerpt: turn.assistant.content,
    status: 'complete',
    provenance: 'agent',
    turnId: turn.turn_id,
  })
  addEdge(questionId, synthesisId, '形成综合')

  for (const trace of turn.tool_traces ?? []) {
    const step: AgentToolStep = {
      id: trace.call_id,
      tool: trace.tool,
      label: toolLabels[trace.tool] ?? '调用学科工具',
      status: trace.phase === 'failed' ? 'failed' : trace.phase === 'started' ? 'running' : 'completed',
      input: trace.input ?? undefined,
      output: trace.output,
      detail: trace.detail,
    }
    addToolNode(step, addNode, turn.turn_id)
    addEdge(questionId, `tool:${step.id}`, '调用')
    addEdge(`tool:${step.id}`, synthesisId, '返回')
  }

  for (const citation of turn.assistant.citations) {
    addEvidenceNode(citation, turn.turn_id, addNode)
    addEdge(`evidence:${citation.citation_id}`, synthesisId, '依据')
  }
}

function addToolNode(
  step: ResearchCanvasToolStep,
  addNode: (node: ResearchCanvasNode) => void,
  turnId?: string,
) {
  addNode({
    id: `tool:${step.id}`,
    kind: 'tool',
    title: step.label,
    excerpt: step.detail ?? null,
    status: step.interrupted
      ? 'interrupted'
      : step.status === 'completed'
        ? 'complete'
        : step.status === 'failed'
          ? 'failed'
          : 'running',
    provenance: 'tool',
    turnId,
  })
}

function addEvidenceNode(
  citation: AgentCitation,
  turnId: string | undefined,
  addNode: (node: ResearchCanvasNode) => void,
) {
  addNode({
    id: `evidence:${citation.citation_id}`,
    kind: 'evidence',
    title: citation.label,
    excerpt: citation.excerpt ?? null,
    status: 'complete',
    provenance: citation.kind === 'source' ? 'knowledge' : 'knowledge',
    citationId: citation.citation_id,
    turnId,
  })
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
