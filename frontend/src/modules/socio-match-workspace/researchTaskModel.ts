export type ResearchTaskEntryType = 'direct_input'
export type ResearchTaskStatus = 'draft'
export type ResearchTaskAction = 'submit_phenomenon'
export type ResearchTaskSource = 'user_input'

export interface ResearchTask {
  readonly taskId: string
  readonly entryType: ResearchTaskEntryType
  readonly status: ResearchTaskStatus
  readonly version: number
  readonly allowedActions: readonly ResearchTaskAction[]
  readonly phenomenon: string
  readonly researchIntent: string | null
  readonly context: string | null
  readonly source: ResearchTaskSource
  readonly createdAt: string
  readonly updatedAt: string
}

export interface ResearchTaskSubmission {
  readonly phenomenon: string
  readonly researchIntent?: string | null
  readonly context?: string | null
}
