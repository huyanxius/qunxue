import type {
  KnowledgeEntrySummaryResponse,
  KnowledgeRelationResponse,
  KnowledgeReleaseResponse,
} from '../../api/generated'

interface KnowledgeGraphInput {
  readonly release: KnowledgeReleaseResponse
  readonly entries: readonly KnowledgeEntrySummaryResponse[]
  readonly relations: readonly KnowledgeRelationResponse[]
}

export interface KnowledgeGraphRelease {
  readonly knowledgeReleaseId: string
  readonly level: string
  readonly contentHash: string
}

export interface KnowledgeGraphDirectoryNode {
  readonly id: string
  readonly type: string
  readonly title: string
}

export interface KnowledgeGraphNode {
  readonly id: string
  readonly label: string
  readonly dimensionId: string
  readonly dimension: string
  readonly categoryId: string
  readonly category: string
  /** Navigation context only; directory membership never becomes a graph edge. */
  readonly directoryPath: readonly KnowledgeGraphDirectoryNode[]
  readonly reviewStatus: string
  readonly contentVersion: number
}

export interface KnowledgeGraphEdge {
  readonly id: string
  readonly source: string
  readonly target: string
  readonly relationType: string
  readonly direction: string
  readonly description: string
  readonly evidenceSourceIds: readonly string[]
  readonly evidenceGrade: string
  readonly reviewStatus: string
  readonly contentVersion: number
}

export interface KnowledgeGraphProjection {
  readonly release: KnowledgeGraphRelease
  readonly nodes: readonly KnowledgeGraphNode[]
  readonly edges: readonly KnowledgeGraphEdge[]
}

function toDirectoryNode(
  node: KnowledgeEntrySummaryResponse['directory_path'][number],
): KnowledgeGraphDirectoryNode {
  return {
    id: node.node_id,
    type: node.node_type,
    title: node.title,
  }
}

function toNode(entry: KnowledgeEntrySummaryResponse): KnowledgeGraphNode {
  return {
    id: entry.knowledge_id,
    label: entry.title,
    dimensionId: entry.dimension_id,
    dimension: entry.dimension,
    categoryId: entry.category_id,
    category: entry.category,
    directoryPath: entry.directory_path.map(toDirectoryNode),
    reviewStatus: entry.review_status,
    contentVersion: entry.content_version,
  }
}

function toEdge(relation: KnowledgeRelationResponse): KnowledgeGraphEdge {
  return {
    id: relation.relation_id,
    source: relation.source_knowledge_id,
    target: relation.target_knowledge_id,
    relationType: relation.relation_type,
    direction: relation.direction,
    description: relation.description,
    evidenceSourceIds: relation.evidence_source_ids,
    evidenceGrade: relation.evidence_grade,
    reviewStatus: relation.review_status,
    contentVersion: relation.content_version,
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
    release: {
      knowledgeReleaseId: release.knowledge_release_id,
      level: release.level,
      contentHash: release.content_hash,
    },
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
