import {
  getAgentConversation as getConversation,
  listAgentConversations as listConversations,
  streamAgentTurn as streamTurn,
  type AgentEvent as AdapterEvent,
} from './researchAgentApi'

export type AgentCitation = {
  citation_id: string
  label: string
  kind: string
  excerpt?: string | null
  knowledge_id?: string | null
  source_id?: string | null
}

export type AgentMessage = {
  message_id: string
  role: 'user' | 'assistant'
  content: string
  citations: AgentCitation[]
  sequence: number
  created_at: string
}

export type AgentTurn = {
  turn_id: string
  user: AgentMessage
  assistant: AgentMessage
  tool_traces?: AgentToolTrace[]
  knowledge_release_id?: string | null
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

export type AgentConversationSummary = {
  conversation_id: string
  title: string
  updated_at: string
  turn_count: number
}

export type AgentConversation = AgentConversationSummary & {
  created_at: string
  turns: AgentTurn[]
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
  | { type: 'turn_completed'; conversation: AgentConversation; knowledge_release_id: string }
  | { type: 'turn_interrupted'; code: string; message: string }
  | { type: 'turn_failed'; code: string; message: string }

export function listAgentConversations(signal?: AbortSignal) {
  return listConversations(signal) as Promise<AgentConversationSummary[]>
}

export function getAgentConversation(conversationId: string, signal?: AbortSignal) {
  return getConversation(conversationId, signal) as Promise<AgentConversation>
}

export function streamAgentTurn(
  payload: { conversation_id: string | null; message: string; idempotencyKey: string },
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
) {
  return streamTurn(payload, (event: AdapterEvent) => onEvent(event as AgentEvent), signal)
}
