import {
  getAgentConversation as getConversation,
  listAgentConversations as listConversations,
  streamAgentTurn as streamTurn,
} from './researchAgentApi'
import type {
  AgentConversation,
  AgentConversationSummary,
  AgentEvent,
} from './model'

export function listAgentConversations(signal?: AbortSignal) {
  return listConversations(signal) as Promise<AgentConversationSummary[]>
}

export function getAgentConversation(conversationId: string, signal?: AbortSignal) {
  return getConversation(conversationId, signal) as Promise<AgentConversation>
}

export function streamAgentTurn(
  payload: { conversation_id: string | null; message: string; idempotencyKey: string; workspace?: 'agent' | 'research'; task_id?: string | null; document_id?: string | null; section_id?: string | null; document_version?: number | null; theory_plan_id?: string | null },
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
) {
  return streamTurn(payload, onEvent, signal)
}
