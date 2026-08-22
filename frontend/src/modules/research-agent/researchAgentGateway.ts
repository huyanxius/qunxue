import {
  confirmResearchStartProposal as confirmStartProposal,
  getAgentConversation as getConversation,
  getResearchStartJourney as getStartJourney,
  listAgentConversations as listConversations,
  streamAgentTurn as streamTurn,
} from './researchAgentApi'
import type {
  AgentConversation,
  AgentConversationSummary,
  AgentEvent,
} from './model'
import type { ResearchStartJourney } from './researchStart'

export function listAgentConversations(signal?: AbortSignal) {
  return listConversations(signal) as Promise<AgentConversationSummary[]>
}

export function getAgentConversation(conversationId: string, signal?: AbortSignal) {
  return getConversation(conversationId, signal) as Promise<AgentConversation>
}

export function getResearchStartJourney(conversationId: string, signal?: AbortSignal) {
  return getStartJourney(conversationId, signal) as Promise<ResearchStartJourney>
}

export function confirmResearchStartProposal(
  request: {
    proposalId: string
    expectedVersion: number
    phenomenon: string
    researchIntent: string | null
    context: string | null
    idempotencyKey: string
  },
  signal?: AbortSignal,
) {
  return confirmStartProposal(request, signal) as Promise<ResearchStartJourney>
}

export function streamAgentTurn(
  payload: { conversation_id: string | null; message: string; idempotencyKey: string; workspace?: 'agent' | 'research'; task_id?: string | null; document_id?: string | null; section_id?: string | null; document_version?: number | null; theory_plan_id?: string | null },
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
) {
  return streamTurn(payload, onEvent, signal)
}
