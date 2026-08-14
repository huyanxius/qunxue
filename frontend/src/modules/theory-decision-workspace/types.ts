export type TheoryDecisionAction =
  | 'adopt'
  | 'exclude'
  | 'retain'
  | 'combine'
  | 'defer'
  | 'request_more_evidence'
  | 'revise_applicability'

export interface CandidateEvidence {
  readonly evidenceRefId: string
  readonly sourceId: string | null
  readonly title: string
  readonly verificationStatus: string
  readonly useBoundary: string
}

export interface TheoryCandidate {
  readonly candidateId: string
  readonly version: number
  readonly knowledgeId: string | null
  readonly title: string
  readonly originLabel: string
  readonly verificationLabel: string
  readonly formalAdoptionEligible: boolean
  readonly adoptionBlockers: readonly string[]
  readonly problemFocus: string
  readonly coreClaims: readonly string[]
  readonly analysisLevels: readonly string[]
  readonly prerequisites: readonly string[]
  readonly applicabilityJudgement: string
  readonly applicabilityRationale: string
  readonly supportingEvidence: readonly CandidateEvidence[]
  readonly missingEvidence: readonly string[]
  readonly limitations: readonly string[]
  readonly misuseBoundaries: readonly string[]
}

export interface SavedDecision {
  readonly candidateId: string
  readonly action: TheoryDecisionAction
  readonly reason: string
  readonly revisedApplicability: string | null
}

export interface SavedDecisionSet {
  readonly decisionSetId: string
  readonly version: number
  readonly decisions?: readonly SavedDecision[]
  readonly useAssignments?: readonly AssignmentDraft[]
  readonly relations?: readonly RelationDraft[]
}

export interface DeferredTheoryPlan {
  readonly reason: string
  readonly deferredAt: string
}

export interface ConfirmedTheoryPlan {
  readonly theoryPlanId: string
  readonly adoptedCandidateIds: readonly string[]
  readonly confirmedAt: string
}

export interface TheoryWorkspace {
  readonly taskId: string
  readonly matchRunId: string
  readonly matchRunVersion: number
  readonly knowledgeReleaseId: string
  readonly status: string
  readonly completionBasis: 'complete' | 'partial' | 'partial_with_user_ack'
  readonly candidates: readonly TheoryCandidate[]
  readonly latestDecisionSet: SavedDecisionSet | null
  readonly confirmedPlan: ConfirmedTheoryPlan | null
  readonly deferredPlan: DeferredTheoryPlan | null
}

export interface DecisionDraft {
  readonly candidateId: string
  readonly candidateVersion: number
  readonly action: TheoryDecisionAction
  readonly reason: string
  readonly relatedSourceIds: readonly string[]
  readonly relatedCandidateIds: readonly string[]
  readonly revisedApplicability: string | null
}

export interface AssignmentDraft {
  readonly candidateId: string
  readonly roleCode: string
  readonly responsibility: string
}

export interface RelationDraft {
  readonly candidateIds: readonly string[]
  readonly relationKind: string
  readonly explanation: string
  readonly premiseCompatibility: string
  readonly supportingEvidence: readonly string[]
  readonly excludingEvidence: readonly string[]
  readonly distinguishingEvidence: readonly string[]
}

export interface SaveTheoryDecisionsInput {
  readonly matchRunId: string
  readonly matchRunVersion: number
  readonly completionBasis: 'complete' | 'partial' | 'partial_with_user_ack'
  readonly decisions: readonly DecisionDraft[]
  readonly useAssignments: readonly AssignmentDraft[]
  readonly relations: readonly RelationDraft[]
}
