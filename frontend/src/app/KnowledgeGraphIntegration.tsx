import {
  KnowledgeGraph,
  type KnowledgeGraphProjection,
} from '../modules/knowledge-graph'
import type { KnowledgeEntryDetail } from '../modules/knowledge-explorer'
import { DegradedState } from './ui/States'

interface KnowledgeGraphIntegrationProps {
  detail: KnowledgeEntryDetail
  onSelectKnowledge: (knowledgeId: string) => void
}

export function KnowledgeGraphIntegration({
  detail,
  onSelectKnowledge,
}: KnowledgeGraphIntegrationProps) {
  if (detail.relations.length > 0) {
    return (
      <DegradedState
        title="知识关系图"
        detail="关系端点尚未加载，图暂不可用。"
      />
    )
  }

  const projection: KnowledgeGraphProjection = {
    releaseId: detail.knowledgeReleaseId,
    nodes: [
      {
        id: detail.knowledgeId,
        label: detail.title,
        reviewStatus: detail.reviewStatus,
      },
    ],
    edges: [],
  }

  return (
    <KnowledgeGraph
      projection={projection}
      onSelectKnowledge={onSelectKnowledge}
    />
  )
}
