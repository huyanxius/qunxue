export type AnalysisAnnotationKind = 'descriptive' | 'researcher_reflection'
export type AnalysisRecordStatus = 'candidate' | 'confirmed' | 'rejected'
export type AnalysisCodingPlanStatus = 'candidate' | 'applied' | 'partially_applied' | 'rejected'
export type AnalysisCodingPlanItemStatus = 'candidate' | 'applied' | 'rejected'
export type AnalysisMemoKind = 'descriptive' | 'reflexive' | 'analytic' | 'methodological'
export type ComparisonFindingKind = 'support' | 'counterexample' | 'contradict' | 'competing_explanation' | 'evidence_gap'
export type CodebookLifecycle = 'active' | 'merged' | 'split' | 'retired'
export type MemoTargetKind = 'project' | 'material' | 'source' | 'code' | 'case' | 'comparison' | 'draft'
export type MatrixSubjectKind = 'code' | 'theme'
export type QualitativeMethod = 'thematic_analysis' | 'grounded_theory' | 'ethnography' | 'case_study' | 'narrative_research' | 'discourse_conversation_analysis' | 'literature_review'

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

export type AnalysisCodingPlanItem = {
  item_id: string
  material_id: string
  parse_id: string
  segment_id: string
  segment_content_hash: string
  quote: string
  quote_hash: string
  quote_start: number
  quote_end: number
  locator: ResearchAnalysisLocator
  code_id: string
  code_label: string
  code_definition: string
  codebook_version: number | null
  confidence: number
  rationale: string
  status: string
  annotation_id: string | null
  decision_reason: string | null
}

export type AnalysisCodingPlan = {
  plan_id: string
  task_id: string
  title: string
  rationale: string
  items: AnalysisCodingPlanItem[]
  source: string
  status: string
  version: number
  created_at: string
  conversation_id: string | null
  agent_run_id: string | null
  agent_turn_id: string | null
  tool_call_id: string | null
  decided_at: string | null
  decision_reason: string | null
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
  workspace?: QualitativeWorkspaceSnapshot
  method_presets?: QualitativeMethodPreset[]
  coding_plans?: AnalysisCodingPlan[]
}

export type CodebookEntry = {
  code_id: string
  inclusion_rules: string[]
  exclusion_rules: string[]
  parent_code_id: string | null
  positive_example_annotation_ids: string[]
  negative_example_annotation_ids: string[]
  lifecycle: CodebookLifecycle
  related_code_ids: string[]
  version: number
  updated_at: string
  revision_reason: string
}

export type AnalysisTheme = {
  theme_id: string
  label: string
  central_concept: string
  code_ids: string[]
  annotation_ids: string[]
  source: string
  status: AnalysisRecordStatus
  version: number
  created_at: string
  decided_at: string | null
  decision_reason: string | null
}

export type AnalysisMemoLink = {
  link_id: string
  memo_id: string
  target_kind: MemoTargetKind
  target_ref: string
  annotation_ids: string[]
  created_at: string
}

export type AnalysisCaseAttribute = { name: string; value: string }

export type AnalysisCaseProfile = {
  profile_id: string
  case_ref: string
  display_label: string
  attributes: AnalysisCaseAttribute[]
  summary: string
  annotation_ids: string[]
  memo_ids: string[]
  version: number
  updated_at: string
}

export type CaseThemeMatrixCell = {
  cell_id: string
  case_profile_id: string
  subject_kind: MatrixSubjectKind
  subject_id: string
  summary: string
  annotation_ids: string[]
  memo_ids: string[]
  finding_kinds: ComparisonFindingKind[]
  version: number
  updated_at: string
}

export type MethodPresetSelection = {
  method: QualitativeMethod
  version: number
  updated_at: string
}

export type QualitativeMethodPreset = {
  method: QualitativeMethod
  label: string
  primary_view: string
  matrix_axes: string[]
  prompts: string
  guardrails: string
}

export type QualitativeWorkspaceSnapshot = {
  schema_version: string
  content_hash: string
  method_preset: MethodPresetSelection
  codebook_entries: CodebookEntry[]
  memo_links: AnalysisMemoLink[]
  case_profiles: AnalysisCaseProfile[]
  formal_themes: AnalysisTheme[]
  candidate_themes: AnalysisTheme[]
  matrix_cells: CaseThemeMatrixCell[]
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

export type DecideCodingPlanInput = {
  expected_version: number
  decisions: Array<{ item_id: string; decision: 'confirmed' | 'rejected'; reason: string }>
}

export type RevokeCodingPlanInput = {
  expected_version: number
  reason: string
}

export type ConfigureCodebookEntryInput = {
  expected_version: number | null
  inclusion_rules: string[]
  exclusion_rules: string[]
  parent_code_id: string | null
  positive_example_annotation_ids: string[]
  negative_example_annotation_ids: string[]
}

export type TransitionCodebookEntryInput = {
  expected_version: number
  lifecycle: CodebookLifecycle
  related_code_ids: string[]
  reason: string
}

export type CreateAnalysisThemeInput = {
  label: string
  central_concept: string
  code_ids: string[]
  annotation_ids: string[]
}

export type CreateAnalysisMemoLinkInput = {
  memo_id: string
  target_kind: MemoTargetKind
  target_ref: string
  annotation_ids: string[]
}

export type SaveAnalysisCaseProfileInput = {
  expected_version: number | null
  case_ref: string
  display_label: string
  attributes: AnalysisCaseAttribute[]
  summary: string
  annotation_ids: string[]
  memo_ids: string[]
}

export type SaveCaseThemeMatrixCellInput = {
  expected_version: number | null
  case_profile_id: string
  subject_kind: MatrixSubjectKind
  subject_id: string
  summary: string
  annotation_ids: string[]
  memo_ids: string[]
  finding_kinds: ComparisonFindingKind[]
}

export type SetQualitativeMethodInput = {
  method: QualitativeMethod
  expected_version: number | null
}
