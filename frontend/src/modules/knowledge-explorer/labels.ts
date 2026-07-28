import type {
  KnowledgeReviewStatus,
  KnowledgeSourceVerificationStatus,
} from './types'

export const reviewStatusLabels: Record<KnowledgeReviewStatus, string> = {
  draft: '草稿',
  pending: '待审核',
  reviewed: '已审核',
  retired: '已停用',
}

export const verificationStatusLabels: Record<
  KnowledgeSourceVerificationStatus,
  string
> = {
  verified: '已核验',
  system_summary: '系统摘要',
  pending: '待核验',
}
