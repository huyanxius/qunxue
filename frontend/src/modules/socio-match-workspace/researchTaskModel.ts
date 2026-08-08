export type ResearchTaskEntryType = 'direct_input'
export type ResearchTaskStatus =
  | 'draft'
  | 'phenomenon_confirmed'
  | 'match_generating'
  | 'decisions_recorded'
  | 'framework_draft'
  | 'framework_confirmed'
export type ResearchTaskAction = 'submit_phenomenon'

/**
 * SocioMatch owns this stable view of a task; transport casing and generated
 * response types stop at the module adapter.
 */
export interface ResearchTask {
  readonly taskId: string
  readonly entryType: ResearchTaskEntryType
  readonly status: ResearchTaskStatus
  readonly version: number
  readonly allowedActions: readonly ResearchTaskAction[]
  readonly createdAt: string
  readonly updatedAt: string
}
