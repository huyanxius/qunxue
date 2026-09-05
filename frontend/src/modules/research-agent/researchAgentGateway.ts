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
  AgentTurnRequest,
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

export function stopAgentRun(runId: string, options?: { keepalive?: boolean }) {
  return stopRun(runId, options)
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
  payload: AgentTurnRequest & { idempotencyKey: string },
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
) {
  return streamTurn(payload, onEvent, signal)
}
