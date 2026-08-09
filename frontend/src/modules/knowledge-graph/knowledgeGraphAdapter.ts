import type {
  KnowledgeEntrySummaryResponse,
  KnowledgeRelationResponse,
  KnowledgeReleaseResponse,
  RelationCandidateResponse,
  StructuralConnectionResponse,
} from '../../api/generated'
import type {
  KnowledgeGraphEdge,
  KnowledgeGraphFocusEntry,
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

function mergeProjection(
  projection: KnowledgeGraphProjection,
  nodes: readonly KnowledgeGraphNode[],
  edges: readonly KnowledgeGraphEdge[],
): KnowledgeGraphProjection {
  const mergedNodes = new Map(projection.nodes.map((node) => [node.id, node]))
  const mergedEdges = new Map(projection.edges.map((edge) => [edge.id, edge]))
  nodes.forEach((node) => {
    const current = mergedNodes.get(node.id)
    const label = current && node.label === node.id && current.label !== current.id
      ? current.label
      : node.label
    mergedNodes.set(node.id, { ...current, ...node, label })
  })
  edges.forEach((edge) => mergedEdges.set(edge.id, edge))
  return {
    ...projection,
    nodes: [...mergedNodes.values()],
    edges: [...mergedEdges.values()],
  }
}

export function mergeGraphEntries(
  projection: KnowledgeGraphProjection,
  entries: readonly KnowledgeGraphFocusEntry[],
): KnowledgeGraphProjection {
  return mergeProjection(
    projection,
    entries.map((entry) => ({
      id: entry.knowledgeId,
      label: entry.title,
      nodeType: 'entry',
      reviewStatus: entry.reviewStatus,
    })),
    [],
  )
}

export function mergeDirectoryPath(
  projection: KnowledgeGraphProjection,
  focus: KnowledgeGraphFocusEntry,
): KnowledgeGraphProjection {
  const path = [
    ...focus.directoryPath,
    {
      nodeId: focus.knowledgeId,
      nodeType: 'entry' as const,
      title: focus.title,
    },
  ]
  return mergeProjection(
    projection,
    path.map((node) => ({
      id: node.nodeId,
      label: node.title,
      nodeType: node.nodeType,
      ...(node.nodeId === focus.knowledgeId
        ? { reviewStatus: focus.reviewStatus }
        : {}),
    })),
    path.slice(0, -1).flatMap((source, index) => {
      const target = path[index + 1]
      return target ? [{
        id: `structure:path:${source.nodeId}:${target.nodeId}`,
        source: source.nodeId,
        target: target.nodeId,
        relationType: 'contains',
        direction: 'outbound',
        layer: 'structure' as const,
      }] : []
    }),
  )
}

export function mergeStructuralConnections(
  projection: KnowledgeGraphProjection,
  connections: readonly StructuralConnectionResponse[],
): KnowledgeGraphProjection {
  return mergeProjection(
    projection,
    connections.flatMap((connection) => [
      {
        id: connection.source_node_id,
        label: connection.source_title,
        nodeType: connection.source_node_type as KnowledgeGraphNode['nodeType'],
      },
      {
        id: connection.target_node_id,
        label: connection.target_title,
        nodeType: connection.target_node_type as KnowledgeGraphNode['nodeType'],
      },
    ]),
    connections.map((connection) => ({
      id: connection.connection_id,
      source: connection.source_node_id,
      target: connection.target_node_id,
      relationType: connection.connection_type,
      direction: connection.direction,
      layer: 'structure' as const,
    })),
  )
}

export function mergeRelationCandidates(
  projection: KnowledgeGraphProjection,
  candidates: readonly RelationCandidateResponse[],
  endpointTitles: ReadonlyMap<string, string> = new Map(),
): KnowledgeGraphProjection {
  return mergeProjection(
    projection,
    candidates.flatMap((candidate) => [candidate.source_knowledge_id, candidate.target_knowledge_id])
      .map((id) => ({ id, label: endpointTitles.get(id) ?? id, nodeType: 'entry' as const })),
    candidates.map((candidate) => ({
      id: candidate.candidate_id,
      source: candidate.source_knowledge_id,
      target: candidate.target_knowledge_id,
      relationType: candidate.suggested_relation_type,
      direction: candidate.direction,
      layer: 'candidate' as const,
      reviewStatus: 'pending' as const,
      evidenceExcerpt: candidate.evidence_excerpt,
      evidenceLocator: candidate.evidence_locator,
      producer: candidate.producer,
      producerConfigVersion: candidate.producer_config_version,
      score: candidate.score ?? undefined,
      triggerReason: candidate.trigger_reason,
      sourceTitle: endpointTitles.get(candidate.source_knowledge_id),
      targetTitle: endpointTitles.get(candidate.target_knowledge_id),
    })),
  )
}

export function mergeReviewedRelations(
  projection: KnowledgeGraphProjection,
  relations: readonly KnowledgeRelationResponse[],
): KnowledgeGraphProjection {
  return mergeProjection(
    projection,
    relations.flatMap((relation) => [relation.source_knowledge_id, relation.target_knowledge_id])
      .map((id) => ({ id, label: id, nodeType: 'entry' as const })),
    relations.map((relation) => ({
      id: relation.relation_id,
      source: relation.source_knowledge_id,
      target: relation.target_knowledge_id,
      relationType: relation.relation_type,
      direction: relation.direction,
      layer: 'reviewed' as const,
      reviewStatus: 'reviewed' as const,
      description: relation.description,
      evidenceSourceIds: relation.evidence_source_ids,
      contentVersion: relation.content_version,
    })),
  )
}
