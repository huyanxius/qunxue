export type AnalysisAnnotationKind = 'descriptive' | 'researcher_reflection'
export type AnalysisRecordStatus = 'candidate' | 'confirmed' | 'rejected'
export type AnalysisMemoKind = 'descriptive' | 'reflexive' | 'analytic' | 'methodological'
export type ComparisonFindingKind = 'support' | 'counterexample' | 'contradict' | 'competing_explanation' | 'evidence_gap'

export type ResearchAnalysisLocator = {
  block_index: number | null
  char_end: number | null
  char_start: number | null
  line_end: number | null
  line_start: number | null
  page: number | null
  paragraph: number | null
  section_path: string[]
}

export type AnalysisAnnotation = {
  annotation_id: string
  annotation_kind: AnalysisAnnotationKind
  case_label: string | null
  created_at: string
  locator: ResearchAnalysisLocator
  material_id: string
  note: string
  observed_at: string | null
  parse_id: string
  quote: string | null
  quote_end: number
  quote_hash: string
  quote_start: number
  reflection: string | null
  segment_content_hash: string
  segment_id: string
  source_available: boolean
  task_id: string
  unavailable_reason: string | null
}

export type AnalysisCode = {
  agent_run_id: string | null
  agent_turn_id: string | null
  annotation_ids: string[]
  code_id: string
  conversation_id: string | null
  created_at: string
  decided_at: string | null
  decision_reason: string | null
  definition: string
  label: string
  rationale: string
  source: string
  status: AnalysisRecordStatus
  task_id: string
  tool_call_id: string | null
  version: number
}

export type AnalysisMemo = {
  agent_run_id: string | null
  agent_turn_id: string | null
  annotation_ids: string[]
  code_ids: string[]
  content: string
  conversation_id: string | null
  created_at: string
  decided_at: string | null
  decision_reason: string | null
  memo_id: string
  memo_kind: AnalysisMemoKind
  source: string
  status: AnalysisRecordStatus
  task_id: string
  title: string
  tool_call_id: string | null
  version: number
}

export type ComparisonFinding = {
  annotation_ids?: string[]
  kind: ComparisonFindingKind
  statement: string
}

export type NextResearchStep = {
  action: string
  kind: string
  priority?: string
}

export type CaseComparison = {
  agent_run_id: string | null
  agent_turn_id: string | null
  case_labels: string[]
  comparison_id: string
  competing_explanations: string[]
  conversation_id: string | null
  created_at: string
  decided_at: string | null
  decision_reason: string | null
  evidence_gaps: string[]
  findings: ComparisonFinding[]
  next_steps: NextResearchStep[]
  question: string
  source: string
  status: AnalysisRecordStatus
  task_id: string
  theory_implication: string
  time_labels: string[]
  title: string
  tool_call_id: string | null
  version: number
}

export type ResearchAnalysisSnapshot = {
  annotations: AnalysisAnnotation[]
  codes: AnalysisCode[]
  comparisons: CaseComparison[]
  memos: AnalysisMemo[]
  task_id: string
}

export type CreateAnalysisAnnotationInput = {
  annotation_kind: AnalysisAnnotationKind
  case_label?: string | null
  material_id: string
  note: string
  observed_at?: string | null
  parse_id: string
  quote_end: number
  quote_start: number
  reflection?: string | null
  segment_id: string
}

export type CreateAnalysisCodeInput = {
  annotation_ids: string[]
  definition: string
  label: string
  rationale: string
}

export type CreateAnalysisMemoInput = {
  annotation_ids?: string[]
  code_ids?: string[]
  content: string
  memo_kind: AnalysisMemoKind
  title: string
}

export type CreateCaseComparisonInput = {
  case_labels: string[]
  competing_explanations?: string[]
  evidence_gaps?: string[]
  findings: ComparisonFinding[]
  next_steps?: NextResearchStep[]
  question: string
  theory_implication: string
  time_labels?: string[]
  title: string
}

export type DecideAnalysisRecordInput = {
  decision: AnalysisRecordStatus
  expected_version: number
  reason: string
}
