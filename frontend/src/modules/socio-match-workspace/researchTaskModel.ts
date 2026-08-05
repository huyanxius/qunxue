export type ResearchTaskSource = 'user_input'

export interface ResearchTask {
  readonly taskId: string
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
