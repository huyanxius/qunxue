import type {
  KnowledgeExplorerDataSource,
  KnowledgeExplorerDetail,
  KnowledgeExplorerEntry,
  KnowledgeExplorerRelease,
} from './types'

const release: KnowledgeExplorerRelease = {
  knowledgeReleaseId: 'demo-preview-2026-08',
  level: 'preview',
  contentHash: 'demo-content-not-for-verification',
}

const details: readonly KnowledgeExplorerDetail[] = [
  {
    entry: {
      knowledgeId: 'demo-context-concept',
      contentVersion: 1,
      title: '情境概念（演示）',
      category: '概念占位',
      dimension: '分析对象',
      reviewStatus: 'pending',
    },
    content:
      '这是一段用于验证详情信息结构的演示说明，不代表正式知识定义，也不用于研究判断。',
    sources: [
      {
        sourceId: 'demo-source-context-note',
        title: '演示来源记录 A',
        sourceType: '演示占位记录',
        verificationStatus: 'pending',
        usageBoundary: '仅用于验证来源字段和待核验状态，不对应真实文献。',
      },
    ],
    relations: [
      {
        relationId: 'demo-relation-context-observation',
        sourceKnowledgeId: 'demo-context-concept',
        targetKnowledgeId: 'demo-observation-method',
        relatedTitle: '观察方法（演示）',
        relationType: '演示关联',
        direction: 'directed',
        description: '仅用于验证关系导航，关系含义尚未经过审核。',
        evidenceSourceIds: [],
        reviewStatus: 'pending',
        contentVersion: 1,
      },
    ],
    useEligibility: {
      browseEligible: true,
      ragEligible: false,
      trainingCandidateEligible: false,
      matchEligible: false,
      reviewRecordIds: [],
    },
  },
  {
    entry: {
      knowledgeId: 'demo-observation-method',
      contentVersion: 1,
      title: '观察方法（演示）',
      category: '方法占位',
      dimension: '研究方法',
      reviewStatus: 'draft',
    },
    content:
      '这是一段用于验证列表选择和关系跳转的演示说明，不构成方法建议。',
    sources: [
      {
        sourceId: 'demo-source-observation-note',
        title: '演示来源记录 B',
        sourceType: '演示占位记录',
        verificationStatus: 'pending',
        usageBoundary: '仅用于页面开发和评审，不对应真实文献。',
      },
    ],
    relations: [
      {
        relationId: 'demo-relation-context-observation',
        sourceKnowledgeId: 'demo-context-concept',
        targetKnowledgeId: 'demo-observation-method',
        relatedTitle: '情境概念（演示）',
        relationType: '演示关联',
        direction: 'directed',
        description: '仅用于验证关系导航，关系含义尚未经过审核。',
        evidenceSourceIds: [],
        reviewStatus: 'pending',
        contentVersion: 1,
      },
    ],
    useEligibility: {
      browseEligible: true,
      ragEligible: false,
      trainingCandidateEligible: false,
      matchEligible: false,
      reviewRecordIds: [],
    },
  },
]

function entryMatches(
  detail: KnowledgeExplorerDetail,
  normalizedQuery: string,
) {
  const searchable = [
    detail.entry.title,
    detail.entry.category,
    detail.entry.dimension,
    detail.content,
  ]
    .join(' ')
    .toLocaleLowerCase('zh-CN')

  return searchable.includes(normalizedQuery)
}

function assertRelease(releaseId: string) {
  if (releaseId !== release.knowledgeReleaseId) {
    throw new Error('演示数据发布版本不匹配，请重新进入知识库')
  }
}

export const demoKnowledgeDataSource: KnowledgeExplorerDataSource = {
  async currentRelease() {
    return release
  },

  async search({ releaseId, query }) {
    assertRelease(releaseId)
    const normalizedQuery = query?.trim().toLocaleLowerCase('zh-CN')
    const entries: readonly KnowledgeExplorerEntry[] = normalizedQuery
      ? details
          .filter((detail) => entryMatches(detail, normalizedQuery))
          .map((detail) => detail.entry)
      : details.map((detail) => detail.entry)

    return { release, entries }
  },

  async getEntry({ knowledgeId, releaseId }) {
    assertRelease(releaseId)
    const detail = details.find(
      (candidate) => candidate.entry.knowledgeId === knowledgeId,
    )
    if (!detail) throw new Error('没有找到对应的演示知识条目')
    return detail
  },
}
