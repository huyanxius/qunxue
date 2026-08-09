import { apiClient } from '../../api/client'
import {
  getCurrentKnowledgeRelease,
  getKnowledgeEntry,
  listKnowledgeEntries,
} from '../../api/generated/sdk.gen'
import type {
  KnowledgeDirectoryNodeResponse,
  KnowledgeEntryDetailResponse,
  KnowledgeEntrySummaryResponse,
  KnowledgeRelationResponse,
  KnowledgeReleaseResponse,
  SourceRecordResponse,
  TheoryProfileResponse,
} from '../../api/generated/types.gen'

import type {
  KnowledgeDirectoryNode,
  KnowledgeEntryDetail,
  KnowledgeEntrySummary,
  KnowledgeRelationView,
  KnowledgeRelease,
  KnowledgeSourceView,
  KnowledgeTheoryProfile,
} from './types'

function directoryNode(
  node: KnowledgeDirectoryNodeResponse,
): KnowledgeDirectoryNode {
  return {
    nodeId: node.node_id,
    nodeType: node.node_type,
    title: node.title,
  }
}

function entrySummary(
  entry: KnowledgeEntrySummaryResponse,
): KnowledgeEntrySummary {
  return {
    knowledgeId: entry.knowledge_id,
    contentVersion: entry.content_version,
    title: entry.title,
    category: entry.category,
    categoryId: entry.category_id,
    dimension: entry.dimension,
    dimensionId: entry.dimension_id,
    directoryPath: entry.directory_path.map(directoryNode),
    reviewStatus: entry.review_status,
  }
}

function release(response: KnowledgeReleaseResponse): KnowledgeRelease {
  if (response.level === 'working') {
    throw new Error('当前知识发布不可浏览')
  }
  return {
    knowledgeReleaseId: response.knowledge_release_id,
    level: response.level,
    contentHash: response.content_hash,
  }
}

function source(source: SourceRecordResponse): KnowledgeSourceView {
  return {
    sourceId: source.source_id,
    title: source.title,
    authorsOrInstitution: source.authors_or_institution,
    year: source.year ?? undefined,
    publication: source.publication ?? undefined,
    locator: source.locator ?? undefined,
    url: source.url ?? undefined,
    sourceType: source.source_type,
    verificationStatus: source.verification_status,
    useBoundary: source.use_boundary,
  }
}

function relation(
  item: KnowledgeRelationResponse,
): KnowledgeRelationView {
  return {
    relationId: item.relation_id,
    sourceKnowledgeId: item.source_knowledge_id,
    targetKnowledgeId: item.target_knowledge_id,
    relationType: item.relation_type,
    direction: item.direction,
    description: item.description,
    evidenceSourceIds: item.evidence_source_ids,
    evidenceGrade: item.evidence_grade || undefined,
    reviewStatus: item.review_status,
    contentVersion: item.content_version,
  }
}

function theoryProfile(
  profile: TheoryProfileResponse | null,
): KnowledgeTheoryProfile | undefined {
  if (!profile) return undefined
  return {
    theoryId: profile.theory_id,
    title: profile.title,
    relatedKnowledgeIds: profile.related_knowledge_ids,
    reviewStatus: profile.review_status,
    matchEligible: profile.match_eligible,
  }
}

function entryDetail(
  entry: KnowledgeEntryDetailResponse,
): KnowledgeEntryDetail {
  return {
    ...entrySummary(entry),
    knowledgeReleaseId: entry.knowledge_release_id,
    aliases: entry.aliases,
    content: entry.content,
    sources: entry.sources.map(source),
    relations: entry.relations
      .filter((item) => item.review_status === 'reviewed')
      .map(relation),
    theoryProfile: theoryProfile(entry.theory_profile),
  }
}

export async function readCurrentKnowledgeRelease() {
  const { data } = await getCurrentKnowledgeRelease({ client: apiClient })
  if (!data) throw new Error('知识服务暂时不可用')
  return release(data)
}

export async function readKnowledgeEntry(input: {
  knowledgeId: string
  releaseId: string
}) {
  const { data } = await getKnowledgeEntry({
    client: apiClient,
    path: { knowledge_id: input.knowledgeId },
    query: { knowledge_release_id: input.releaseId },
  })
  if (!data) throw new Error('未找到当前发布中的知识条目')
  if (data.knowledge_release_id !== input.releaseId) {
    throw new Error('知识服务返回了不同发布版本，请重新进入知识库')
  }
  return entryDetail(data)
}

export async function loadKnowledgeDirectory(releaseId: string) {
  const entries: KnowledgeEntrySummary[] = []
  let cursor: string | undefined

  do {
    const { data } = await listKnowledgeEntries({
      client: apiClient,
      query: {
        knowledge_release_id: releaseId,
        cursor,
        limit: 100,
      },
    })
    if (!data) throw new Error('知识服务暂时不可用')
    if (data.knowledge_release_id !== releaseId) {
      throw new Error('知识服务返回了不同发布版本，请重新进入知识库')
    }

    entries.push(...data.entries.map(entrySummary))
    cursor = data.next_cursor ?? undefined
  } while (cursor)

  return entries
}

export async function readKnowledgePreview(releaseId: string) {
  const { data } = await listKnowledgeEntries({
    client: apiClient,
    query: {
      knowledge_release_id: releaseId,
      limit: 48,
    },
  })
  if (!data) throw new Error('知识服务暂时不可用')
  if (data.knowledge_release_id !== releaseId) {
    throw new Error('知识服务返回了不同发布版本，请重新进入知识库')
  }
  return data.entries.map(entrySummary)
}

export async function searchKnowledgeEntries(input: {
  releaseId: string
  query: string
  dimensionId?: string
  categoryId?: string
  cursor?: string
}) {
  const { data } = await listKnowledgeEntries({
    client: apiClient,
    query: {
      knowledge_release_id: input.releaseId,
      query: input.query,
      dimension_id: input.dimensionId,
      category_id: input.categoryId,
      cursor: input.cursor,
      limit: 100,
    },
  })
  if (!data) throw new Error('知识服务暂时不可用')
  if (data.knowledge_release_id !== input.releaseId) {
    throw new Error('知识服务返回了不同发布版本，请重新进入知识库')
  }
  return {
    entries: data.entries.map(entrySummary),
    nextCursor: data.next_cursor ?? undefined,
  }
}
