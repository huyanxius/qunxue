import type { KnowledgeDirectoryFacet } from './types'

const taxonomy = [
  { nodeId: 'D1', title: '本体论' },
  { nodeId: 'D2', title: '实践论' },
  { nodeId: 'D3', title: '方法论' },
  { nodeId: 'D4', title: '价值论' },
  { nodeId: 'D5', title: '认识论' },
  { nodeId: 'D6', title: '学派传统' },
  { nodeId: 'D7', title: '学科史' },
] as const

const directoryCollator = new Intl.Collator('zh-CN', { numeric: true, sensitivity: 'base' })

export interface KnowledgeDirectoryCategory {
  nodeId: string
  title: string
  entryCount: number
  children: readonly KnowledgeDirectoryCategory[]
}

export interface KnowledgeDirectoryDimension {
  nodeId: string
  title: string
  entryCount: number
  categories: readonly KnowledgeDirectoryCategory[]
}

function contractError(detail: string) {
  return new Error(`知识目录契约错误：${detail}`)
}

export function buildKnowledgeDirectory(
  facets: readonly KnowledgeDirectoryFacet[],
): readonly KnowledgeDirectoryDimension[] {
  const nodes = new Map<string, KnowledgeDirectoryFacet>()
  const children = new Map<string, KnowledgeDirectoryFacet[]>()
  for (const facet of facets) {
    if (nodes.has(facet.nodeId)) throw contractError(`${facet.nodeId} 重复`)
    nodes.set(facet.nodeId, facet)
    if (facet.parentNodeId) {
      const siblings = children.get(facet.parentNodeId) ?? []
      siblings.push(facet)
      children.set(facet.parentNodeId, siblings)
    }
  }

  for (const facet of facets) {
    if (facet.parentNodeId && !nodes.has(facet.parentNodeId)) {
      throw contractError(`${facet.nodeId} 的父节点不存在`)
    }
    if (facet.nodeType === 'dimension' && facet.parentNodeId) {
      throw contractError(`${facet.nodeId} 的维度节点不能有父节点`)
    }
  }

  const visited = new Set<string>()
  function readCategories(parentNodeId: string, ancestors: Set<string>): readonly KnowledgeDirectoryCategory[] {
    return [...(children.get(parentNodeId) ?? [])]
      .sort((left, right) => directoryCollator.compare(left.title, right.title))
      .map((facet) => {
      if (facet.nodeType !== 'category') throw contractError(`${facet.nodeId} 不是分类节点`)
      if (ancestors.has(facet.nodeId)) throw contractError(`${facet.nodeId} 形成循环`)
      visited.add(facet.nodeId)
      return {
        nodeId: facet.nodeId,
        title: facet.title,
        entryCount: facet.entryCount,
        children: readCategories(facet.nodeId, new Set([...ancestors, facet.nodeId])),
      }
      })
  }

  const directory = taxonomy.map((expected) => {
    const facet = nodes.get(expected.nodeId)
    if (!facet || facet.nodeType !== 'dimension' || facet.title !== expected.title) {
      throw contractError(`${expected.nodeId} 与固定 taxonomy 不一致`)
    }
    visited.add(facet.nodeId)
    return {
      nodeId: facet.nodeId,
      title: facet.title,
      entryCount: facet.entryCount,
      categories: readCategories(facet.nodeId, new Set([facet.nodeId])),
    }
  })
  if (visited.size !== facets.length) throw contractError('存在未归入七维目录的节点')
  return directory
}
