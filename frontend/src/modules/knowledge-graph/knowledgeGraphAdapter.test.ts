import { describe, expect, it } from 'vitest'

import { projectKnowledgeGraph } from './knowledgeGraphAdapter'

const release = {
  knowledge_release_id: 'release-preview-2026-08',
  level: 'preview' as const,
  content_hash: 'sha256:preview-content',
}

const entries = [
  {
    knowledge_id: 'knowledge-field',
    content_version: 3,
    title: '场域理论',
    category_id: 'category-theory',
    category: '理论',
    dimension_id: 'D6',
    dimension: '学派传统',
    directory_path: [
      { node_id: 'D6', node_type: 'dimension' as const, title: '学派传统' },
      { node_id: 'category-theory', node_type: 'category' as const, title: '理论' },
    ],
    review_status: 'reviewed' as const,
    eligibility: {
      browse_eligible: true,
      rag_eligible: false,
      training_candidate_eligible: false,
      match_eligible: true,
      review_record_ids: ['review-field'],
    },
  },
  {
    knowledge_id: 'knowledge-habitus',
    content_version: 2,
    title: '惯习',
    category_id: 'category-concept',
    category: '概念',
    dimension_id: 'D1',
    dimension: '本体论',
    directory_path: [
      { node_id: 'D1', node_type: 'dimension' as const, title: '本体论' },
      { node_id: 'category-concept', node_type: 'category' as const, title: '概念' },
    ],
    review_status: 'pending' as const,
    eligibility: {
      browse_eligible: true,
      rag_eligible: false,
      training_candidate_eligible: false,
      match_eligible: false,
      review_record_ids: [],
    },
  },
]

describe('projectKnowledgeGraph', () => {
  it('projects only reviewed relations whose endpoints are supplied', () => {
    const graph = projectKnowledgeGraph({
      release,
      entries,
      relations: [
        {
          relation_id: 'relation-field-habitus',
          source_knowledge_id: 'knowledge-field',
          target_knowledge_id: 'knowledge-habitus',
          relation_type: '概念依赖',
          direction: 'directed',
          description: '场域分析需要结合行动者的惯习。',
          evidence_source_ids: ['source-book-1'],
          evidence_grade: 'A',
          content_version: 2,
          review_status: 'reviewed',
        },
        {
          relation_id: 'relation-pending',
          source_knowledge_id: 'knowledge-field',
          target_knowledge_id: 'knowledge-habitus',
          relation_type: '待核验关系',
          direction: 'directed',
          description: '不应在图中显示。',
          evidence_source_ids: [],
          evidence_grade: 'C',
          content_version: 1,
          review_status: 'pending',
        },
        {
          relation_id: 'relation-missing-target',
          source_knowledge_id: 'knowledge-field',
          target_knowledge_id: 'knowledge-not-loaded',
          relation_type: '概念依赖',
          direction: 'directed',
          description: '不能凭 ID 伪造节点。',
          evidence_source_ids: ['source-book-1'],
          evidence_grade: 'A',
          content_version: 1,
          review_status: 'reviewed',
        },
      ],
    })

    expect(graph.release).toEqual({
      knowledgeReleaseId: 'release-preview-2026-08',
      level: 'preview',
      contentHash: 'sha256:preview-content',
    })
    expect(graph.nodes).toEqual([
      {
        id: 'knowledge-field',
        label: '场域理论',
        dimensionId: 'D6',
        dimension: '学派传统',
        categoryId: 'category-theory',
        category: '理论',
        directoryPath: [
          { id: 'D6', type: 'dimension', title: '学派传统' },
          { id: 'category-theory', type: 'category', title: '理论' },
        ],
        reviewStatus: 'reviewed',
        contentVersion: 3,
      },
      {
        id: 'knowledge-habitus',
        label: '惯习',
        dimensionId: 'D1',
        dimension: '本体论',
        categoryId: 'category-concept',
        category: '概念',
        directoryPath: [
          { id: 'D1', type: 'dimension', title: '本体论' },
          { id: 'category-concept', type: 'category', title: '概念' },
        ],
        reviewStatus: 'pending',
        contentVersion: 2,
      },
    ])
    expect(graph.edges).toEqual([
      {
        id: 'relation-field-habitus',
        source: 'knowledge-field',
        target: 'knowledge-habitus',
        relationType: '概念依赖',
        direction: 'directed',
        description: '场域分析需要结合行动者的惯习。',
        evidenceSourceIds: ['source-book-1'],
        evidenceGrade: 'A',
        reviewStatus: 'reviewed',
        contentVersion: 2,
      },
    ])
  })

  it('keeps a relation-free preview as an empty edge projection', () => {
    const graph = projectKnowledgeGraph({ release, entries, relations: [] })

    expect(graph.nodes).toHaveLength(2)
    expect(graph.edges).toEqual([])
  })
})
