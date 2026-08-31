import type {
  ConsentScope,
  DeidentificationStatus,
  LiteratureExchangeFormat,
  MaterialArchiveProfileResponse,
  ModelProcessingScope,
  ProfessionalMaterialArchiveResponse,
  ResearchRole,
  ResearchStage,
  SensitivityLevel,
  UpdateMaterialArchiveProfileRequest,
} from '../../api/generated'

export type ProfessionalMaterialArchive = ProfessionalMaterialArchiveResponse
export type ProfessionalMaterialProfile = MaterialArchiveProfileResponse
export type ProfessionalMaterialProfileUpdate = UpdateMaterialArchiveProfileRequest
export type LiteratureFormat = LiteratureExchangeFormat

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
  'not_assessed', 'manual_only', 'local_only', 'external_allowed',
]

const LABELS: Record<string, string> = {
  empirical_material: '经验材料', literature: '文献', research_process: '研究过程',
  prior_draft: '既有草稿', dataset: '数据集', result: '研究结果', other: '其他',
  intake: '待清点', collection: '采集中', analysis: '分析中', writing: '写作中', archived: '已归档',
  public: '公开', internal: '内部', sensitive: '敏感', highly_sensitive: '高度敏感',
  public_use: '可公开使用', project_only: '仅本研究', team_only: '仅研究团队',
  manual_review_only: '仅人工阅读', withdrawn: '已撤回',
  not_required: '无需去标识化', pending: '待去标识化', partial: '部分完成', complete: '已完成',
  not_assessed: '尚未评估', manual_only: '仅人工处理', local_only: '仅本地模型',
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
