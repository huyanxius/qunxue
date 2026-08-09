export interface KnowledgeGraphNode {
  readonly id: string
  readonly label: string
  readonly reviewStatus: string
}

export interface KnowledgeGraphEdge {
  readonly id: string
  readonly source: string
  readonly target: string
  readonly relationType: string
  readonly direction: string
}

export interface KnowledgeGraphProjection {
  readonly releaseId: string
  readonly nodes: readonly KnowledgeGraphNode[]
  readonly edges: readonly KnowledgeGraphEdge[]
}
