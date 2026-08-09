import type { KnowledgeEntrySummary } from './types'

const taxonomy = [
  { nodeId: 'D1', title: '本体论' },
  { nodeId: 'D2', title: '实践论' },
  { nodeId: 'D3', title: '方法论' },
  { nodeId: 'D4', title: '价值论' },
  { nodeId: 'D5', title: '认识论' },
  { nodeId: 'D6', title: '学派传统' },
  { nodeId: 'D7', title: '学科史' },
] as const

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

interface MutableKnowledgeDirectoryCategory {
  nodeId: string
  title: string
  entryCount: number
  children: Map<string, MutableKnowledgeDirectoryCategory>
}

function readCategories(
  categories: Map<string, MutableKnowledgeDirectoryCategory>,
): readonly KnowledgeDirectoryCategory[] {
  return [...categories.values()].map((category) => ({
    nodeId: category.nodeId,
    title: category.title,
    entryCount: category.entryCount,
    children: readCategories(category.children),
  }))
}

export function buildKnowledgeDirectory(
  entries: readonly KnowledgeEntrySummary[],
): readonly KnowledgeDirectoryDimension[] {
  const dimensions = new Map<string, {
    nodeId: string
    title: string
    entryCount: number
    categories: Map<string, MutableKnowledgeDirectoryCategory>
  }>(
    taxonomy.map((dimension) => [
      dimension.nodeId,
      { ...dimension, entryCount: 0, categories: new Map<string, MutableKnowledgeDirectoryCategory>() },
    ]),
  )

  for (const entry of entries) {
    const [root, ...categories] = entry.directoryPath
    if (!root || categories.length === 0) {
      throw contractError(`${entry.knowledgeId} 缺少目录路径`)
    }
    if (root.nodeType !== 'dimension') {
      throw contractError(`${entry.knowledgeId} 的根节点不是维度`)
    }
    const dimension = dimensions.get(root.nodeId)
    if (!dimension || root.title !== dimension.title) {
      throw contractError(`${entry.knowledgeId} 的维度不在固定 taxonomy 中`)
    }
    if (root.nodeId !== entry.dimensionId || root.title !== entry.dimension) {
      throw contractError(`${entry.knowledgeId} 的维度字段与目录路径不一致`)
    }
    const leaf = categories[categories.length - 1]
    if (!leaf || leaf.nodeId !== entry.categoryId || leaf.title !== entry.category) {
      throw contractError(`${entry.knowledgeId} 的分类字段与目录路径不一致`)
    }

    dimension.entryCount += 1
    let currentCategories = dimension.categories
    for (const category of categories) {
      if (category.nodeType !== 'category') {
        throw contractError(`${entry.knowledgeId} 缺少分类节点`)
      }
      let current = currentCategories.get(category.nodeId)
      if (!current) {
        current = {
          nodeId: category.nodeId,
          title: category.title,
          entryCount: 0,
          children: new Map<string, MutableKnowledgeDirectoryCategory>(),
        }
        currentCategories.set(category.nodeId, current)
      }
      current.entryCount += 1
      currentCategories = current.children
    }
  }

  return taxonomy.map((dimension) => {
    const current = dimensions.get(dimension.nodeId)
    if (!current) throw contractError(`${dimension.nodeId} 未初始化`)
    return {
      nodeId: current.nodeId,
      title: current.title,
      entryCount: current.entryCount,
      categories: readCategories(current.categories),
    }
  })
}
