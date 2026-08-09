import { describe, expect, it } from 'vitest'

import {
  mergeRelationCandidates,
  mergeReviewedRelations,
  mergeStructuralConnections,
  projectKnowledgeGraph,
} from './knowledgeGraphAdapter'

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
          algorithm_weight: null,
          algorithm_config_version: null,
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

  it('keeps structural, pending candidate, and reviewed edges as distinct layers', () => {
    const structural = mergeStructuralConnections(
      {
        releaseId: 'release-preview-2026-08',
        nodes: [],
        edges: [],
      },
      [
        {
          connection_id: 'structure:d1-category',
          connection_kind: 'structure',
          source_node_id: 'D1',
          source_node_type: 'dimension',
          source_title: '本体论',
          target_node_id: 'D1:C001',
          target_node_type: 'category',
          target_title: '社会关系',
          connection_type: 'contains',
          direction: 'outbound',
        },
      ],
    )
    const withCandidates = mergeRelationCandidates(structural, [
      {
        candidate_id: 'candidate:one',
        source_knowledge_id: 'D1:C001:E001',
        target_knowledge_id: 'D1:C001:E002',
        suggested_relation_type: 'extends',
        direction: 'outbound',
        evidence_excerpt: '条目一扩展了条目二。',
        evidence_locator: '本体论/社会关系.md#content-line-9',
        evidence_source_id: 'source:D1:C001:E001',
        source_content_version: 1,
        target_content_version: 2,
        producer: 'explicit-title-trigger',
        producer_config_version: 'explicit-title-trigger-v1',
        score: 1,
        trigger_reason: 'trigger=扩展了',
        review_status: 'pending',
        review_record_id: null,
      },
    ], new Map([
      ['D1:C001:E001', '条目一'],
      ['D1:C001:E002', '条目二'],
    ]))
    const graph = mergeReviewedRelations(withCandidates, [
      {
        relation_id: 'relation:one',
        source_knowledge_id: 'D1:C001:E001',
        target_knowledge_id: 'D1:C001:E003',
        relation_type: 'contrasts_with',
        direction: 'outbound',
        description: '两者在分析层次上形成对照。',
        evidence_source_ids: ['source:D1:C001:E001'],
        evidence_grade: 'reviewed',
        algorithm_weight: null,
        algorithm_config_version: null,
        content_version: 3,
        review_status: 'reviewed',
      },
    ])

    expect(graph.nodes).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'D1', nodeType: 'dimension' }),
      expect.objectContaining({ id: 'D1:C001', nodeType: 'category' }),
      expect.objectContaining({ id: 'D1:C001:E001', nodeType: 'entry' }),
    ]))
    expect(graph.edges).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'structure:d1-category', layer: 'structure' }),
      expect.objectContaining({
        id: 'candidate:one',
        layer: 'candidate',
        reviewStatus: 'pending',
        evidenceExcerpt: '条目一扩展了条目二。',
        sourceTitle: '条目一',
        targetTitle: '条目二',
      }),
      expect.objectContaining({
        id: 'relation:one',
        layer: 'reviewed',
        description: '两者在分析层次上形成对照。',
      }),
    ]))
  })
})
