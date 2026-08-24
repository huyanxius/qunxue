import type {
  KnowledgeSourceVerificationStatus,
} from './types'

export const verificationStatusLabels: Record<
  KnowledgeSourceVerificationStatus,
  string
> = {
  verified: '已核验',
  system_summary: '系统摘要',
  pending: '待核验',
}
