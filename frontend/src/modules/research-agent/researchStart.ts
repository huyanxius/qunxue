export type ResearchStartProposal = {
  proposalId: string
  phenomenon: string
  researchIntent: string | null
  context: string | null
  version: number
  status: 'pending_confirmation' | 'confirmed'
}

export type ResearchStartJourney = {
  conversationId: string
  status: 'collecting' | 'proposal_pending' | 'task_bound'
  taskId: string | null
  proposal: ResearchStartProposal | null
  knowledgeReleaseId?: string | null
  phenomenonConfirmed?: boolean
  resumePath: string | null
}
