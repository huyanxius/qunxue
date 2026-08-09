/**
 * 知识浏览模块的界面模型；未来 adapter 必须从生成 DTO 映射，不能把它当第二套 HTTP 契约。
 */
export type KnowledgeReviewStatus =
  | 'draft'
  | 'pending'
  | 'reviewed'
  | 'retired'

export type KnowledgeSourceVerificationStatus =
  | 'verified'
  | 'system_summary'
  | 'pending'

export interface KnowledgeDirectoryNode {
  nodeId: string
  nodeType: 'dimension' | 'category'
  title: string
}

export interface KnowledgeDirectoryFacet extends KnowledgeDirectoryNode {
  parentNodeId?: string
  entryCount: number
}

export interface KnowledgeEntrySummary {
  knowledgeId: string
  contentVersion: number
  title: string
  category: string
  categoryId: string
  dimension: string
  dimensionId: string
  directoryPath: readonly KnowledgeDirectoryNode[]
  reviewStatus: KnowledgeReviewStatus
}

export interface KnowledgeRelease {
  knowledgeReleaseId: string
  level: 'preview' | 'final'
  contentHash: string
}

export interface KnowledgeSourceView {
  sourceId: string
  title: string
  authorsOrInstitution: readonly string[]
  year?: number
  publication?: string
  locator?: string
  url?: string
  sourceType: string
  verificationStatus: KnowledgeSourceVerificationStatus
  useBoundary: string
}

export interface KnowledgeRelationView {
  relationId: string
  sourceKnowledgeId: string
  targetKnowledgeId: string
  relationType: string
  direction: string
  description: string
  evidenceSourceIds: readonly string[]
  evidenceGrade?: string
  reviewStatus: KnowledgeReviewStatus
  contentVersion: number
}

export interface KnowledgeTheoryProfile {
  theoryId: string
  title: string
  relatedKnowledgeIds: readonly string[]
  reviewStatus: KnowledgeReviewStatus
  matchEligible: boolean
}

export interface KnowledgeEntryDetail extends KnowledgeEntrySummary {
  knowledgeReleaseId: string
  aliases: readonly string[]
  content: string
  sources: readonly KnowledgeSourceView[]
  relations: readonly KnowledgeRelationView[]
  theoryProfile?: KnowledgeTheoryProfile
}
