import { apiClient } from '../../api/client'
import {
  getKnowledgeEntry,
  listKnowledgeConnections,
  listKnowledgeRelationCandidates,
  listKnowledgeRelations,
} from '../../api/generated/sdk.gen'
import type {
  KnowledgeRelationResponse,
  RelationCandidateResponse,
  StructuralConnectionResponse,
} from '../../api/generated/types.gen'

function requireRelease(actual: string, expected: string) {
  if (actual !== expected) {
    throw new Error('知识图谱返回了不同发布版本，请重新进入知识库')
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
      limit: 200,
    },
  })
  if (!data) throw new Error('待审核发现关系暂时不可用')
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
      limit: 200,
    },
  })
  if (!data) throw new Error('已审核知识关系暂时不可用')
  requireRelease(data.knowledge_release_id, input.releaseId)
  return {
    relations: data.relations,
    nextCursor: data.next_cursor ?? undefined,
    totalCount: data.total_count,
  }
}
