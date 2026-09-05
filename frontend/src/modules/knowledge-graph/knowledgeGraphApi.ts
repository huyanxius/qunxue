import { apiClient } from '../../api/client'
import {
  getCurrentKnowledgeRelease,
  getKnowledgeEntry,
  listKnowledgeConnections,
  listKnowledgeEntries,
  listKnowledgeRelationCandidates,
  listKnowledgeRelations,
} from '../../api/generated/sdk.gen'
import type {
  KnowledgeRelationResponse,
  RelationCandidateResponse,
  StructuralConnectionResponse,
} from '../../api/generated/types.gen'
import type { KnowledgeGraphFocusEntry } from './types'

function requireRelease(actual: string, expected: string) {
  if (actual !== expected) {
    throw new Error('知识图谱返回了不同发布版本，请重新进入知识库')
  }
}

function focusEntry(entry: {
  knowledge_id: string
  title: string
  review_status: string
  directory_path: readonly {
    node_id: string
    node_type: 'dimension' | 'category'
    title: string
  }[]
}): KnowledgeGraphFocusEntry {
  return {
    knowledgeId: entry.knowledge_id,
    title: entry.title,
    reviewStatus: entry.review_status,
    directoryPath: entry.directory_path.map((node) => ({
      nodeId: node.node_id,
      nodeType: node.node_type,
      title: node.title,
    })),
  }
}

export async function readCurrentKnowledgeGraphRelease() {
  const { data } = await getCurrentKnowledgeRelease({ client: apiClient })
  if (!data || data.level === 'working') throw new Error('当前知识发布不可浏览')
  return data.knowledge_release_id
}

export async function searchKnowledgeGraphEntries(input: {
  releaseId: string
  query: string
  cursor?: string
}): Promise<{ entries: readonly KnowledgeGraphFocusEntry[]; nextCursor?: string }> {
  const { data } = await listKnowledgeEntries({
    client: apiClient,
    query: {
      knowledge_release_id: input.releaseId,
      query: input.query,
      cursor: input.cursor,
      limit: 20,
    },
  })
  if (!data) throw new Error('知识搜索暂时不可用')
  requireRelease(data.knowledge_release_id, input.releaseId)
  return {
    entries: data.entries.map(focusEntry),
    nextCursor: data.next_cursor ?? undefined,
  }
}

export async function readKnowledgeGraphFocusEntry(input: {
  releaseId: string
  knowledgeId: string
}): Promise<KnowledgeGraphFocusEntry> {
  const { data } = await getKnowledgeEntry({
    client: apiClient,
    path: { knowledge_id: input.knowledgeId },
    query: { knowledge_release_id: input.releaseId },
  })
  if (!data) throw new Error('未找到当前发布中的知识条目')
  requireRelease(data.knowledge_release_id, input.releaseId)
  return {
    ...focusEntry(data),
    content: data.content,
    sources: data.sources?.map((source) => ({
      sourceId: source.source_id, title: source.title, locator: source.locator ?? undefined,
      url: source.url ?? undefined, status: source.verification_status,
    })),
  }
}

export async function readKnowledgeGraphEntry(input: {
  releaseId: string
  knowledgeId: string
}): Promise<{ knowledgeId: string; title: string }> {
  const { data } = await getKnowledgeEntry({
    client: apiClient,
    path: { knowledge_id: input.knowledgeId },
    query: { knowledge_release_id: input.releaseId },
  })
  if (!data) throw new Error('未找到关系端点知识条目')
  requireRelease(data.knowledge_release_id, input.releaseId)
  return { knowledgeId: data.knowledge_id, title: data.title }
}

export async function readStructuralConnectionPage(input: {
  releaseId: string
  sourceNodeId: string
  cursor?: string
}): Promise<{
  connections: readonly StructuralConnectionResponse[]
  nextCursor?: string
}> {
  const { data } = await listKnowledgeConnections({
    client: apiClient,
    query: {
      knowledge_release_id: input.releaseId,
      source_node_id: input.sourceNodeId,
      cursor: input.cursor,
      limit: 50,
    },
  })
  if (!data) throw new Error('知识结构暂时不可用')
  requireRelease(data.knowledge_release_id, input.releaseId)
  return {
    connections: data.connections,
    nextCursor: data.next_cursor ?? undefined,
  }
}

export async function readIncidentCandidatePage(input: {
  releaseId: string
  knowledgeId: string
  cursor?: string
}): Promise<{
  candidates: readonly RelationCandidateResponse[]
  nextCursor?: string
  totalCount: number
}> {
  const { data } = await listKnowledgeRelationCandidates({
    client: apiClient,
    query: {
      knowledge_release_id: input.releaseId,
      knowledge_id: input.knowledgeId,
      cursor: input.cursor,
      limit: 50,
    },
  })
  if (!data) throw new Error('候选关系暂时不可用')
  requireRelease(data.knowledge_release_id, input.releaseId)
  return {
    candidates: data.candidates,
    nextCursor: data.next_cursor ?? undefined,
    totalCount: data.total_count,
  }
}

export async function readIncidentRelationPage(input: {
  releaseId: string
  knowledgeId: string
  cursor?: string
}): Promise<{
  relations: readonly KnowledgeRelationResponse[]
  nextCursor?: string
  totalCount: number
}> {
  const { data } = await listKnowledgeRelations({
    client: apiClient,
    query: {
      knowledge_release_id: input.releaseId,
      knowledge_id: input.knowledgeId,
      cursor: input.cursor,
      limit: 50,
    },
  })
  if (!data) throw new Error('知识关系暂时不可用')
  requireRelease(data.knowledge_release_id, input.releaseId)
  return {
    relations: data.relations,
    nextCursor: data.next_cursor ?? undefined,
    totalCount: data.total_count,
  }
}
