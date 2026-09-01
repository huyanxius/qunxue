export type ResearchCycleEvidenceGap = Readonly<{
  gap_id: string
  source_kind: string
  source_id: string
  description: string
  suggested_action: string
  destination: string
  priority: string
  analysis_content_hash: string
  theory_plan_id: string | null
  theory_plan_version: number | null
  status: string
}>

export type ResearchCycleSnapshot = Readonly<{
  schema_version: string
  task_id: string
  version: number
  content_hash: string
  analysis_content_hash: string
  theory_plan_id: string | null
  theory_plan_version: number | null
  evidence: ReadonlyArray<Record<string, unknown>>
  gaps: ReadonlyArray<ResearchCycleEvidenceGap>
  project_facts: Readonly<{
    material_count: number
    material_kinds: ReadonlyArray<ReadonlyArray<string | number>>
    case_count: number
    case_material_coverage: ReadonlyArray<ReadonlyArray<string | number>>
    consent_scopes: ReadonlyArray<ReadonlyArray<string | number>>
    sensitivity_levels: ReadonlyArray<ReadonlyArray<string | number>>
    pending_deidentification_count: number
    sampling_batches: ReadonlyArray<string>
    analysis_counts: ReadonlyArray<ReadonlyArray<string | number>>
  }>
  reporting_hints: ReadonlyArray<Readonly<{
    guideline: string
    item_key: string
    label: string
    status: string
    message: string
    blocking: boolean
  }>>
  research_map_patch: Readonly<{
    nodes?: ReadonlyArray<Record<string, unknown>>
    relations?: ReadonlyArray<Record<string, unknown>>
  }>
}>
