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

export interface KnowledgeUseEligibility {
  browseEligible: boolean
  ragEligible: boolean
  trainingCandidateEligible: boolean
  matchEligible: boolean
  reviewRecordIds: readonly string[]
}

export interface KnowledgeSource {
  sourceId: string
  title: string
  contributor?: string
  year?: number
  publication?: string
  locator?: string
  url?: string
  sourceType: string
  verificationStatus: KnowledgeSourceVerificationStatus
  usageBoundary?: string
}

export interface KnowledgeRelation {
  relationId: string
  sourceKnowledgeId: string
  targetKnowledgeId: string
  relatedTitle: string
  relationType: string
  direction: 'directed' | 'bidirectional'
  description: string
  evidenceSourceIds: readonly string[]
  evidenceGrade?: string
  reviewStatus: KnowledgeReviewStatus
  contentVersion: number
}

export interface KnowledgeExplorerEntry {
  knowledgeId: string
  contentVersion: number
  title: string
  category: string
  dimension: string
  reviewStatus: KnowledgeReviewStatus
}

export interface KnowledgeExplorerRelease {
  knowledgeReleaseId: string
  level: 'working' | 'preview' | 'final'
  contentHash: string
}

export interface KnowledgeExplorerPage {
  release: KnowledgeExplorerRelease
  entries: readonly KnowledgeExplorerEntry[]
  nextCursor?: string
}

export interface KnowledgeExplorerDetail {
  entry: KnowledgeExplorerEntry
  content: string
  theoryId?: string
  sources: readonly KnowledgeSource[]
  relations: readonly KnowledgeRelation[]
  useEligibility: KnowledgeUseEligibility
}

export interface KnowledgeExplorerDataSource {
  currentRelease(): Promise<KnowledgeExplorerRelease>
  search(input: {
    releaseId: string
    query?: string
    category?: string
    cursor?: string
  }): Promise<KnowledgeExplorerPage>
  getEntry(input: {
    knowledgeId: string
    releaseId: string
  }): Promise<KnowledgeExplorerDetail>
}

export interface KnowledgeExplorerProps {
  dataSource: KnowledgeExplorerDataSource
  initialKnowledgeId?: string
  dataNotice?: string
  homeHref?: string
  onNavigateHome?: () => void
}
