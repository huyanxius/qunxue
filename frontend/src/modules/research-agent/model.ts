export type AgentCitation = {
  citation_id: string
  label: string
  kind: string
  excerpt?: string | null
  knowledge_id?: string | null
  source_id?: string | null
  source_kind?: string | null
  material_id?: string | null
  parse_id?: string | null
  segment_id?: string | null
  locator?: Record<string, unknown> | null
  deleted?: boolean
}

export type AgentResearchNodeKind = 'question' | 'theory' | 'claim' | 'evidence' | 'gap' | 'synthesis'
export type AgentResearchNodeStatus = 'developing' | 'grounded' | 'open' | 'verified' | 'challenged' | 'complete'
export type AgentResearchRelationKind = 'explains' | 'supports' | 'challenges' | 'derives' | 'refines'

export type AgentResearchMapNode = {
  id: string
  kind: AgentResearchNodeKind
  title: string
  summary?: string | null
  status: AgentResearchNodeStatus
  citation_ids: string[]
}

export type AgentResearchMapRelation = {
  id: string
  source: string
  target: string
  relation: AgentResearchRelationKind
  label?: string | null
}

export type AgentResearchMapPatch = {
  schema_version: 1
  nodes: AgentResearchMapNode[]
  relations: AgentResearchMapRelation[]
  remove_node_ids: string[]
  remove_relation_ids: string[]
}

export type AgentResearchMap = {
  schema_version: 1
  nodes: AgentResearchMapNode[]
  relations: AgentResearchMapRelation[]
}

export type AgentMessage = {
  message_id: string
  role: 'user' | 'assistant'
  content: string
  citations: AgentCitation[]
  sequence: number
  created_at: string
}

export type AgentToolTrace = {
  tool: string
  phase: 'started' | 'finished' | 'failed'
  call_id: string
  input?: Record<string, unknown> | null
  output?: unknown
  detail?: string | null
  error?: string | null
}

export type AgentTurn = {
  turn_id: string
  user: AgentMessage
  assistant: AgentMessage
  tool_traces?: AgentToolTrace[]
  knowledge_release_id?: string | null
  canvas_patches?: AgentResearchMapPatch[]
}

export type AgentConversationSummary = {
  conversation_id: string
  title: string
  updated_at: string
  turn_count: number
}

export type AgentConversation = AgentConversationSummary & {
  created_at: string
  turns: AgentTurn[]
  research_map?: AgentResearchMap
}

export type AgentRuntimeMode = 'mock' | 'base' | 'sft'

export type AgentToolStep = {
  id: string
  tool: string
  label: string
  status: 'running' | 'completed' | 'failed'
  input?: unknown
  output?: unknown
  detail?: string | null
}

export type AgentEvent =
  | { type: 'turn_started'; conversation_id: string; run_id: string; replayed: boolean; runtime_mode?: AgentRuntimeMode }
  | { type: 'agent_status'; status: 'thinking' | 'answering' }
  | {
      type: 'tool_started'
      tool: string
      call_id: string | null
      input?: unknown
      detail?: string | null
    }
  | {
      type: 'tool_finished'
      tool: string
      call_id: string | null
      output?: unknown
      detail?: string | null
    }
  | {
      type: 'tool_failed'
      tool: string
      call_id: string | null
      input?: unknown
      message: string
      error_code: string | null
      detail: string | null
    }
  | { type: 'assistant_delta'; delta: string }
  | { type: 'citation_added'; citation: AgentCitation }
  | { type: 'canvas_patch'; patch: AgentResearchMapPatch }
  | { type: 'turn_completed'; conversation: AgentConversation; knowledge_release_id: string }
  | { type: 'turn_interrupted'; code: string; message: string }
  | { type: 'turn_failed'; code: string; message: string }
