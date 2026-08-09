import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  readCurrentKnowledgeRelease,
  readKnowledgeDirectory,
  readKnowledgeEntry,
  searchKnowledgeEntries,
} from './knowledgeApi'

function entry(knowledgeId: string, title: string) {
  return {
    category: '概念',
    category_id: 'C001',
    content_version: 1,
    dimension: '本体论',
    dimension_id: 'D1',
    directory_path: [
      { node_id: 'D1', node_type: 'dimension', title: '本体论' },
      { node_id: 'C001', node_type: 'category', title: '概念' },
    ],
    eligibility: {
      browse_eligible: true,
      match_eligible: false,
      rag_eligible: false,
      review_record_ids: [],
      training_candidate_eligible: false,
    },
    knowledge_id: knowledgeId,
    review_status: 'pending',
    title,
  }
}

function page(input: {
  releaseId: string
  entries: readonly ReturnType<typeof entry>[]
  nextCursor?: string
  totalCount?: number
}) {
  return {
    entries: input.entries,
    knowledge_release_id: input.releaseId,
    next_cursor: input.nextCursor ?? null,
    stable_order: input.entries.map((candidate) => candidate.knowledge_id),
    total_count: input.totalCount ?? input.entries.length,
  }
}

function directory(releaseId = 'release-a') {
  return {
    knowledge_release_id: releaseId,
    nodes: [
      { entry_count: 12, node_id: 'D1', node_type: 'dimension', parent_node_id: null, title: '本体论' },
      { entry_count: 4, node_id: 'C001', node_type: 'category', parent_node_id: 'D1', title: '概念' },
    ],
  }
}

function detail(releaseId: string) {
  return {
    aliases: ['概念别名'],
    category: '概念',
    category_id: 'C001',
    content: '一段真实条目正文。',
    content_version: 2,
    dimension: '本体论',
    dimension_id: 'D1',
    directory_path: [
      { node_id: 'D1', node_type: 'dimension', title: '本体论' },
      { node_id: 'C001', node_type: 'category', title: '概念' },
    ],
    eligibility: {
      browse_eligible: true,
      match_eligible: false,
      rag_eligible: false,
      review_record_ids: [],
      training_candidate_eligible: false,
    },
    knowledge_id: 'D1:C001',
    knowledge_release_id: releaseId,
    relations: [
      {
        content_version: 1,
        description: '经审核的概念关系。',
        direction: 'directed',
        evidence_grade: 'A',
        evidence_source_ids: ['source-1'],
        relation_id: 'relation-reviewed',
        relation_type: '概念关联',
        review_status: 'reviewed',
        source_knowledge_id: 'D1:C001',
        target_knowledge_id: 'D1:C002',
      },
      {
        content_version: 1,
        description: '尚未审核的关系。',
        direction: 'directed',
        evidence_grade: '',
        evidence_source_ids: [],
        relation_id: 'relation-pending',
        relation_type: '概念关联',
        review_status: 'pending',
        source_knowledge_id: 'D1:C001',
        target_knowledge_id: 'D1:C003',
      },
    ],
    review_status: 'pending',
    sources: [
      {
        authors_or_institution: ['知识库导入'],
        locator: 'knowledge/D1.md#c001',
        publication: null,
        source_id: 'source-1',
        source_type: 'repository_markdown',
        title: '知识库原始 Markdown',
        url: null,
        use_boundary: '待学术核验',
        verification_status: 'pending',
        year: null,
      },
    ],
    theory_profile: {
      analysis_levels: ['中观'],
      applicable_phenomena: ['社会行动'],
      competing_or_complementary_theory_ids: [],
      content_version: 1,
      core_propositions: ['概念命题'],
      exclusion_signals: [],
      match_eligible: false,
      observable_evidence: [],
      prerequisites: [],
      related_knowledge_ids: ['D1:C001'],
      review_status: 'pending',
      source_ids: ['source-1'],
      theory_id: 'theory-1',
      title: '概念理论',
    },
    title: '概念',
  }
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function urlFor(input: RequestInfo | URL) {
  if (typeof input === 'string') return new URL(input)
  if (input instanceof URL) return input
  return new URL(input.url)
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('knowledge API', () => {
  it('reads one compact directory summary without paging through entries', async () => {
    const requests: URL[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = urlFor(input)
      requests.push(request)
      return json(directory())
    }))

    const nodes = await readKnowledgeDirectory('release-a')

    expect(nodes).toEqual([
      { entryCount: 12, nodeId: 'D1', nodeType: 'dimension', parentNodeId: undefined, title: '本体论' },
      { entryCount: 4, nodeId: 'C001', nodeType: 'category', parentNodeId: 'D1', title: '概念' },
    ])
    expect(requests).toHaveLength(1)
    expect(requests[0]?.pathname).toBe('/api/knowledge/directory')
    expect(requests[0]?.searchParams.get('knowledge_release_id')).toBe('release-a')
  })

  it('rejects a directory that changes the fixed release', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      json(directory('release-b')),
    ))

    await expect(readKnowledgeDirectory('release-a')).rejects.toThrow(
      '不同发布版本',
    )
  })

  it('sends a fixed release query with directory filters to the real search endpoint', async () => {
    const requests: URL[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = urlFor(input)
      requests.push(request)
      return json(page({
        releaseId: 'release-a',
        entries: [entry('D1:C001', '概念')],
        totalCount: 37,
      }))
    }))

    const result = await searchKnowledgeEntries({
      categoryId: 'C001',
      dimensionId: 'D1',
      query: '概念',
      releaseId: 'release-a',
    })

    expect(result.entries.map((candidate) => candidate.knowledgeId)).toEqual([
      'D1:C001',
    ])
    expect(result.totalCount).toBe(37)
    expect(requests[0]?.searchParams.get('knowledge_release_id')).toBe('release-a')
    expect(requests[0]?.searchParams.get('query')).toBe('概念')
    expect(requests[0]?.searchParams.get('dimension_id')).toBe('D1')
    expect(requests[0]?.searchParams.get('category_id')).toBe('C001')
  })

  it('pins detail reads to the selected release', async () => {
    const requests: URL[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = urlFor(input)
      requests.push(request)
      if (request.pathname.endsWith('/releases/current')) {
        return json({
          content_hash: 'sha256:release-a',
          knowledge_release_id: 'release-a',
          level: 'preview',
        })
      }
      return json(detail('release-a'))
    }))

    const release = await readCurrentKnowledgeRelease()
    const knowledge = await readKnowledgeEntry({
      knowledgeId: 'D1:C001',
      releaseId: release.knowledgeReleaseId,
    })

    expect(release).toEqual({
      contentHash: 'sha256:release-a',
      knowledgeReleaseId: 'release-a',
      level: 'preview',
    })
    expect(knowledge.content).toBe('一段真实条目正文。')
    expect(knowledge.sources[0]?.verificationStatus).toBe('pending')
    expect(knowledge.relations.map((relation) => relation.relationId)).toEqual([
      'relation-reviewed',
    ])
    expect(knowledge.theoryProfile).toEqual({
      matchEligible: false,
      relatedKnowledgeIds: ['D1:C001'],
      reviewStatus: 'pending',
      theoryId: 'theory-1',
      title: '概念理论',
    })
    expect(requests[1]?.searchParams.get('knowledge_release_id')).toBe('release-a')
  })
})
