import type {
  KnowledgeEntrySummaryResponse,
  KnowledgeRelationResponse,
  KnowledgeReleaseResponse,
} from '../../api/generated'
import type {
  KnowledgeGraphEdge,
  KnowledgeGraphNode,
  KnowledgeGraphProjection,
} from './types'

interface KnowledgeGraphInput {
  readonly release: KnowledgeReleaseResponse
  readonly entries: readonly KnowledgeEntrySummaryResponse[]
  readonly relations: readonly KnowledgeRelationResponse[]
}

function toNode(entry: KnowledgeEntrySummaryResponse): KnowledgeGraphNode {
  return {
    id: entry.knowledge_id,
    label: entry.title,
    reviewStatus: entry.review_status,
  }
}

function toEdge(relation: KnowledgeRelationResponse): KnowledgeGraphEdge {
  return {
    id: relation.relation_id,
    source: relation.source_knowledge_id,
    target: relation.target_knowledge_id,
    relationType: relation.relation_type,
    direction: relation.direction,
  }
}

export function projectKnowledgeGraph({
  release,
  entries,
  relations,
}: KnowledgeGraphInput): KnowledgeGraphProjection {
  const nodes = entries.map(toNode)
  const visibleNodeIds = new Set(nodes.map((node) => node.id))

  return {
    releaseId: release.knowledge_release_id,
    nodes,
    edges: relations
      .filter(
        (relation) =>
          relation.review_status === 'reviewed'
          && visibleNodeIds.has(relation.source_knowledge_id)
          && visibleNodeIds.has(relation.target_knowledge_id),
      )
      .map(toEdge),
  }
}
