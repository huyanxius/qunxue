export type KnowledgeDimensionTone =
  | 'ontology'
  | 'practice'
  | 'method'
  | 'value'
  | 'epistemology'
  | 'tradition'
  | 'history'

export type KnowledgeNodeKind = 'section' | 'family' | 'concept' | 'stage' | 'category'

export interface KnowledgeNodePresentation {
  badge?: string
  kind: KnowledgeNodeKind
  label: string
  stage?: string
}

const dimensionTones: Record<string, KnowledgeDimensionTone> = {
  D1: 'ontology',
  D2: 'practice',
  D3: 'method',
  D4: 'value',
  D5: 'epistemology',
  D6: 'tradition',
  D7: 'history',
}

export function dimensionTone(dimensionId: string): KnowledgeDimensionTone {
  return dimensionTones[dimensionId] ?? 'ontology'
}

export function describeTaxonomyNode(title: string): KnowledgeNodePresentation {
  const section = title.match(/^([IVXLCDM]+)\.\s*(.+)$/)
  if (section) return { badge: section[1], kind: 'section', label: section[2] }

  const family = title.match(/^(\d+)\.\s*(.+)$/)
  if (family) return { badge: family[1], kind: 'family', label: family[2] }

  const concept = title.match(/^(C\d+)\s+(.+)$/)
  if (concept) return { badge: concept[1], kind: 'concept', label: concept[2] }

  const stage = title.match(/^T([1-4])\s+(.+)$/)
  if (stage) return { badge: `T${stage[1]}`, kind: 'stage', label: stage[2], stage: stage[1] }

  return { badge: undefined, kind: 'category', label: title }
}
