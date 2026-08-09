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
  it('projects reviewed relations whose endpoints are supplied', () => {
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
          algorithm_weight: 0.91,
          algorithm_config_version: 'relation-rules-v1',
          content_version: 2,
          review_status: 'reviewed',
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
          algorithm_weight: null,
          algorithm_config_version: null,
          content_version: 1,
          review_status: 'reviewed',
        },
      ],
    })

    expect(graph.releaseId).toBe('release-preview-2026-08')
    expect(graph.nodes).toEqual([
      {
        id: 'knowledge-field',
        label: '场域理论',
        reviewStatus: 'reviewed',
      },
      {
        id: 'knowledge-habitus',
        label: '惯习',
        reviewStatus: 'pending',
      },
    ])
    expect(graph.edges).toEqual([
      {
        id: 'relation-field-habitus',
        source: 'knowledge-field',
        target: 'knowledge-habitus',
        relationType: '概念依赖',
        direction: 'directed',
      },
    ])
  })

  it('keeps a relation-free preview as an empty edge projection', () => {
    const graph = projectKnowledgeGraph({ release, entries, relations: [] })

    expect(graph.nodes).toHaveLength(2)
    expect(graph.edges).toEqual([])
  })
})
