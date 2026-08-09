import {
  KnowledgeGraphWorkspace,
  type KnowledgeGraphFocusEntry,
} from '../modules/knowledge-graph'

interface KnowledgeGraphIntegrationProps {
  releaseId: string
  focusEntry?: KnowledgeGraphFocusEntry
  onSelectKnowledge: (knowledgeId: string) => void
}

export function KnowledgeGraphIntegration({
  releaseId,
  focusEntry,
  onSelectKnowledge,
}: KnowledgeGraphIntegrationProps) {
  return (
    <KnowledgeGraphWorkspace
      releaseId={releaseId}
      focusEntry={focusEntry}
      onSelectKnowledge={onSelectKnowledge}
    />
  )
}
