import {
  confirmResearchStartProposal as confirmStartProposal,
  deleteAgentConversation as deleteConversation,
  getAgentConversation as getConversation,
  getResearchStartJourney as getStartJourney,
  listAgentConversations as listConversations,
  renameAgentConversation as renameConversation,
  stopAgentRun as stopRun,
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

export function renameAgentConversation(conversationId: string, title: string) {
  return renameConversation(conversationId, title) as Promise<AgentConversationSummary>
}

export function deleteAgentConversation(conversationId: string) {
  return deleteConversation(conversationId)
}

export function stopAgentRun(runId: string) {
  return stopRun(runId)
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
