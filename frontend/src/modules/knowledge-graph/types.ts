export interface KnowledgeGraphNode {
  readonly id: string
  readonly label: string
  readonly nodeType?: 'dimension' | 'category' | 'entry'
  readonly reviewStatus?: string
}

export interface KnowledgeGraphEdge {
  readonly id: string
  readonly source: string
  readonly target: string
  readonly relationType: string
  readonly direction: string
  readonly layer?: 'structure' | 'candidate' | 'reviewed'
  readonly reviewStatus?: 'pending' | 'reviewed'
  readonly evidenceExcerpt?: string
  readonly evidenceLocator?: string
  readonly evidenceSourceIds?: readonly string[]
  readonly producer?: string
  readonly producerConfigVersion?: string
  readonly score?: number
  readonly triggerReason?: string
  readonly sourceTitle?: string
  readonly targetTitle?: string
  readonly description?: string
  readonly contentVersion?: number
}

export interface KnowledgeGraphProjection {
  readonly releaseId: string
  readonly nodes: readonly KnowledgeGraphNode[]
  readonly edges: readonly KnowledgeGraphEdge[]
}

export interface KnowledgeGraphFocusEntry {
  readonly knowledgeId: string
  readonly title: string
  readonly reviewStatus: string
  readonly directoryPath: readonly {
    readonly nodeId: string
    readonly nodeType: 'dimension' | 'category'
    readonly title: string
  }[]
}
