export type ResearchTaskEntryType = 'direct_input'
export type ResearchTaskStatus = 'draft'
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

export interface PhenomenonEvidence {
  readonly evidenceRefId: string
  readonly excerpt: string
  readonly sourceDescription: string | null
  readonly useBoundary: string
}

export interface PhenomenonCandidate {
  readonly candidateId: string
  readonly taskId: string
  readonly version: number
  readonly status: 'proposed' | 'edited' | 'confirmed' | 'superseded'
  readonly phenomenon: string
  readonly researchIntent: string | null
  readonly context: string | null
  readonly evidence: readonly PhenomenonEvidence[]
  readonly modelLabel: string
}

export interface PhenomenonSnapshot {
  readonly phenomenonQueryId: string
  readonly phenomenon: string
  readonly researchIntent: string | null
  readonly context: string | null
  readonly confirmedAt: string
}

export interface StartedPhenomenon {
  readonly taskId: string
  readonly candidate: PhenomenonCandidate
}

export interface RestoredPhenomenon {
  readonly candidate: PhenomenonCandidate
  readonly snapshot: PhenomenonSnapshot | null
}
