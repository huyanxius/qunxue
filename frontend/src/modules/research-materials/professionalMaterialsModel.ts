export type ResearchRole = 'empirical_material' | 'literature' | 'research_process' | 'prior_draft' | 'dataset' | 'result' | 'other'
export type ResearchStage = 'intake' | 'collection' | 'analysis' | 'writing' | 'archived'
export type SensitivityLevel = 'public' | 'internal' | 'sensitive' | 'highly_sensitive'
export type ConsentScope = 'public_use' | 'project_only' | 'team_only' | 'manual_review_only' | 'withdrawn'
export type DeidentificationStatus = 'not_required' | 'pending' | 'partial' | 'complete'
export type ModelProcessingScope = 'manual_only' | 'local_only' | 'external_allowed'
export type LiteratureFormat = 'bibtex' | 'ris' | 'csl_json'
export type MaterialKind = 'paper' | 'interview_transcript' | 'observation_record' | 'field_note' | 'other'
export type MaterialRelationType = 'derived_from' | 'supplements' | 'translation_of' | 'version_of' | 'describes' | 'related'
export type CaseAttributeValue = string | number | boolean | null

export type ProfessionalMaterialProfile = {
  material_id: string
  research_role: ResearchRole
  specific_type: string
  stage: ResearchStage
  batch_id: string | null
  tags: string[]
  collection_ids: string[]
  sensitivity: SensitivityLevel
  consent_scope: ConsentScope
  deidentification_status: DeidentificationStatus
  model_processing_scope: ModelProcessingScope
  allows_manual_reading: boolean
  allows_external_model_processing: boolean
  updated_at: string
}

export type ProfessionalMaterialProfileUpdate = {
  research_role: ResearchRole
  specific_type: string
  stage: ResearchStage
  batch_id?: string | null
  tags?: string[]
  collection_ids?: string[]
  sensitivity: SensitivityLevel
  consent_scope: ConsentScope
  deidentification_status: DeidentificationStatus
  model_processing_scope: ModelProcessingScope
}

export type MaterialBatch = { batch_id: string; name: string; created_at: string }
export type MaterialCollection = {
  collection_id: string
  name: string
  description: string | null
  parent_collection_id: string | null
  created_at: string
}
export type LiteratureEntry = {
  literature_id: string
  item_type: string
  title: string
  doi: string | null
  csl_data: Record<string, unknown>
  attachment_material_ids: string[]
  collection_ids: string[]
  created_at: string
}
export type ResearchCase = {
  case_id: string
  name: string
  description: string | null
  attributes: Record<string, CaseAttributeValue>
  material_ids: string[]
  created_at: string
}
export type MaterialRelation = {
  relation_id: string
  source_material_id: string
  target_material_id: string
  relation_type: MaterialRelationType
  note: string | null
  created_at: string
}
export type LiteratureDuplicateHint = {
  literature_id: string
  candidate_id: string
  reasons: string[]
}
export type MaterialArchiveInventory = {
  catalog_pending_material_ids: string[]
  parse_failed_material_ids: string[]
  suspected_duplicate_literature_ids: string[]
  pending_deidentification_material_ids: string[]
  restricted_material_ids: string[]
}
export type ProfessionalMaterialArchive = {
  task_id: string
  profiles: ProfessionalMaterialProfile[]
  batches: MaterialBatch[]
  collections: MaterialCollection[]
  literature: LiteratureEntry[]
  cases: ResearchCase[]
  relations: MaterialRelation[]
  duplicate_hints: LiteratureDuplicateHint[]
  inventory: MaterialArchiveInventory
}

export type CreateMaterialCollectionInput = {
  name: string
  description?: string | null
  parent_collection_id?: string | null
}
export type CreateResearchCaseInput = {
  name: string
  description?: string | null
  attributes?: Record<string, CaseAttributeValue>
  material_ids?: string[]
}
export type CreateMaterialRelationInput = {
  source_material_id: string
  target_material_id: string
  relation_type: MaterialRelationType
  note?: string | null
}
export type CreateLiteratureEntryInput = {
  item_type: string
  title: string
  doi?: string | null
  csl_data?: Record<string, unknown>
  attachment_material_ids?: string[]
  collection_ids?: string[]
}
export type DoiMetadataCandidate = {
  doi: string
  item_type: string
  title: string
  source: string
  verified_at: string
  csl_data: Record<string, unknown>
}
export type BatchUploadResult = {
  batch_id: string
  items: Array<{
    filename: string
    status: string
    material_id?: string | null
    error_code?: string | null
    message?: string | null
  }>
}

export const RESEARCH_ROLES: readonly ResearchRole[] = [
  'empirical_material', 'literature', 'research_process', 'prior_draft',
  'dataset', 'result', 'other',
]
export const RESEARCH_STAGES: readonly ResearchStage[] = [
  'intake', 'collection', 'analysis', 'writing', 'archived',
]
export const SENSITIVITY_LEVELS: readonly SensitivityLevel[] = [
  'public', 'internal', 'sensitive', 'highly_sensitive',
]
export const CONSENT_SCOPES: readonly ConsentScope[] = [
  'public_use', 'project_only', 'team_only', 'manual_review_only', 'withdrawn',
]
export const DEIDENTIFICATION_STATUSES: readonly DeidentificationStatus[] = [
  'not_required', 'pending', 'partial', 'complete',
]
export const MODEL_PROCESSING_SCOPES: readonly ModelProcessingScope[] = [
  'manual_only', 'local_only', 'external_allowed',
]

const LABELS: Record<string, string> = {
  empirical_material: '经验材料', literature: '文献', research_process: '研究过程',
  prior_draft: '既有草稿', dataset: '数据集', result: '研究结果', other: '其他',
  intake: '待清点', collection: '采集中', analysis: '分析中', writing: '写作中', archived: '已归档',
  public: '公开', internal: '内部', sensitive: '敏感', highly_sensitive: '高度敏感',
  public_use: '可公开使用', project_only: '仅本研究', team_only: '仅研究团队',
  manual_review_only: '仅人工阅读', withdrawn: '已撤回',
  not_required: '无需去标识化', pending: '待去标识化', partial: '部分完成', complete: '已完成',
  manual_only: '仅人工处理', local_only: '仅本地模型',
  external_allowed: '允许外部模型',
}

export function archiveLabel(value: string): string {
  return LABELS[value] ?? value
}

export function profileUpdateFrom(
  profile: ProfessionalMaterialProfile,
): ProfessionalMaterialProfileUpdate {
  return {
    research_role: profile.research_role,
    specific_type: profile.specific_type,
    stage: profile.stage,
    batch_id: profile.batch_id,
    tags: profile.tags,
    collection_ids: profile.collection_ids,
    sensitivity: profile.sensitivity,
    consent_scope: profile.consent_scope,
    deidentification_status: profile.deidentification_status,
    model_processing_scope: profile.model_processing_scope,
  }
}
