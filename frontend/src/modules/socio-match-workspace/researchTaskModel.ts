export type ResearchTaskEntryType = 'direct_input' | 'material_input'
export type ResearchTaskStatus =
  | 'draft'
  | 'phenomenon_confirmed'
  | 'match_generating'
  | 'decisions_recorded'
  | 'framework_draft'
  | 'framework_confirmed'
export type ResearchTaskAction = 'submit_phenomenon'

export interface SeedTheoryStart {
  readonly theoryId: string
  readonly name?: string
}

export interface SeedTheoryClue extends SeedTheoryStart {
  readonly name: string
}

export interface ResearchTask {
  readonly taskId: string
  readonly entryType: ResearchTaskEntryType
  readonly status: ResearchTaskStatus
  readonly version: number
  readonly allowedActions: readonly ResearchTaskAction[]
  readonly seedTheory: SeedTheoryClue | null
  readonly createdAt: string
  readonly updatedAt: string
}

export interface PhenomenonExample {
  readonly exampleId: string
  readonly title: string
  readonly phenomenon: string
  readonly researchIntent: string | null
  readonly context: string | null
  readonly sourceType: 'built_in_example'
}

export interface PhenomenonEvidence {
  readonly evidenceRefId: string
  readonly excerpt: string
  readonly locator: string | null
  readonly sourceDescription: string | null
  readonly useBoundary: string
}

export interface PhenomenonCandidate {
  readonly candidateId: string
  readonly taskId: string
  readonly version: number
  readonly status: 'proposed' | 'edited' | 'confirmed' | 'superseded'
  readonly contentOrigin: 'system_generated' | 'user_modified'
  readonly phenomenon: string
  readonly researchIntent: string | null
  readonly context: string | null
  readonly missingInformation: readonly string[]
  readonly sourceTraceability: 'traceable' | 'partial' | 'untraceable'
  readonly evidence: readonly PhenomenonEvidence[]
  readonly modelLabel: string
}

export interface PhenomenonSnapshot {
  readonly phenomenonQueryId: string
  readonly phenomenon: string
  readonly researchIntent: string | null
  readonly context: string | null
  readonly contentHash: string
  readonly confirmedAt: string
}

export interface StartedPhenomenon {
  readonly taskId: string
  readonly candidate: PhenomenonCandidate
}

export interface RestoredPhenomenon {
  readonly candidates: readonly PhenomenonCandidate[]
  readonly candidate: PhenomenonCandidate
  readonly snapshot: PhenomenonSnapshot | null
  readonly seedTheory: SeedTheoryClue | null
}

export interface MaterialStartInput {
  readonly pastedText: string
  readonly file: File | null
  readonly researchIntent: string
  readonly context: string
  readonly processingPolicyVersion: string
  readonly seedTheory?: SeedTheoryStart | null
}
