import { beforeEach, describe, expect, it, vi } from 'vitest'

const listKnowledgeConnections = vi.hoisted(() => vi.fn())
const listKnowledgeRelationCandidates = vi.hoisted(() => vi.fn())
const listKnowledgeRelations = vi.hoisted(() => vi.fn())
const getKnowledgeEntry = vi.hoisted(() => vi.fn())
const getCurrentKnowledgeRelease = vi.hoisted(() => vi.fn())
const listKnowledgeEntries = vi.hoisted(() => vi.fn())

vi.mock('../../api/generated/sdk.gen', () => ({
  listKnowledgeConnections,
  listKnowledgeRelationCandidates,
  listKnowledgeRelations,
  getKnowledgeEntry,
  getCurrentKnowledgeRelease,
  listKnowledgeEntries,
}))
vi.mock('../../api/client', () => ({ apiClient: { kind: 'generated-client' } }))

import {
  readIncidentCandidatePage,
  readIncidentRelationPage,
  readCurrentKnowledgeGraphRelease,
  readKnowledgeGraphFocusEntry,
  readKnowledgeGraphEntry,
  readStructuralConnectionPage,
  searchKnowledgeGraphEntries,
} from './knowledgeGraphApi'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('knowledge graph API adapter', () => {
  it('resolves the current release through the generated SDK', async () => {
    getCurrentKnowledgeRelease.mockResolvedValue({ data: {
      content_hash: 'sha256:release-a',
      knowledge_release_id: 'release-a',
      level: 'preview',
    } })

    await expect(readCurrentKnowledgeGraphRelease()).resolves.toBe('release-a')
  })

  it('searches one bounded page and maps entries for graph focus', async () => {
    listKnowledgeEntries.mockResolvedValue({ data: {
      entries: [{
        category: '社会关系',
        category_id: 'D1:C001',
        content_version: 1,
        dimension: '本体论',
        dimension_id: 'D1',
        directory_path: [
          { node_id: 'D1', node_type: 'dimension', title: '本体论' },
          { node_id: 'D1:C001', node_type: 'category', title: '社会关系' },
        ],
        eligibility: {
          browse_eligible: true,
          match_eligible: false,
          rag_eligible: false,
          review_record_ids: [],
          training_candidate_eligible: false,
        },
        knowledge_id: 'D1:C001:E001',
        review_status: 'reviewed',
        title: '社会资本',
      }],
      knowledge_release_id: 'release-a',
      next_cursor: 'search-2',
      stable_order: ['D1:C001:E001'],
    } })

    const page = await searchKnowledgeGraphEntries({
      releaseId: 'release-a',
      query: '社会',
      cursor: 'search-1',
    })

    expect(page).toEqual({
      entries: [{
        knowledgeId: 'D1:C001:E001',
        title: '社会资本',
        reviewStatus: 'reviewed',
        directoryPath: [
          { nodeId: 'D1', nodeType: 'dimension', title: '本体论' },
          { nodeId: 'D1:C001', nodeType: 'category', title: '社会关系' },
        ],
      }],
      nextCursor: 'search-2',
    })
    expect(listKnowledgeEntries).toHaveBeenCalledWith({
      client: { kind: 'generated-client' },
      query: {
        knowledge_release_id: 'release-a',
        query: '社会',
        cursor: 'search-1',
        limit: 20,
      },
    })
  })

  it('maps one detail to the complete focus path', async () => {
    getKnowledgeEntry.mockResolvedValue({ data: {
      category: '社会关系', category_id: 'D1:C001', content_version: 1,
      dimension: '本体论', dimension_id: 'D1',
      directory_path: [
        { node_id: 'D1', node_type: 'dimension', title: '本体论' },
        { node_id: 'D1:C001', node_type: 'category', title: '社会关系' },
      ],
      eligibility: {
        browse_eligible: true, match_eligible: false, rag_eligible: false,
        review_record_ids: [], training_candidate_eligible: false,
      },
      knowledge_id: 'D1:C001:E001', knowledge_release_id: 'release-a',
      review_status: 'reviewed', title: '社会资本', aliases: [], content: '',
      relations: [], sources: [], theory_profile: null,
    } })

    await expect(readKnowledgeGraphFocusEntry({
      releaseId: 'release-a',
      knowledgeId: 'D1:C001:E001',
    })).resolves.toEqual({
      knowledgeId: 'D1:C001:E001',
      title: '社会资本',
      reviewStatus: 'reviewed',
      directoryPath: [
        { nodeId: 'D1', nodeType: 'dimension', title: '本体论' },
        { nodeId: 'D1:C001', nodeType: 'category', title: '社会关系' },
      ],
    })
  })

  it('keeps source-node pagination on the generated connections SDK', async () => {
    listKnowledgeConnections.mockResolvedValue({ data: {
      knowledge_release_id: 'release-a',
      connections: [],
      stable_order: [],
      total_count: 3,
      next_cursor: 'cursor-2',
    } })

    const page = await readStructuralConnectionPage({
      releaseId: 'release-a',
      sourceNodeId: 'D1',
      cursor: 'cursor-1',
    })

    expect(page.nextCursor).toBe('cursor-2')
    expect(listKnowledgeConnections).toHaveBeenCalledWith({
      client: { kind: 'generated-client' },
      query: {
        knowledge_release_id: 'release-a',
        source_node_id: 'D1',
        cursor: 'cursor-1',
        limit: 50,
      },
    })
  })

  it('loads pending and reviewed incident edges through separate endpoints', async () => {
    listKnowledgeRelationCandidates.mockResolvedValue({ data: {
      knowledge_release_id: 'release-a', candidates: [], stable_order: [],
      total_count: 0, next_cursor: null,
    } })
    listKnowledgeRelations.mockResolvedValue({ data: {
      knowledge_release_id: 'release-a', relations: [], stable_order: [],
      total_count: 0, next_cursor: null,
    } })

    await readIncidentCandidatePage({ releaseId: 'release-a', knowledgeId: 'entry-a' })
    await readIncidentRelationPage({ releaseId: 'release-a', knowledgeId: 'entry-a' })

    expect(listKnowledgeRelationCandidates).toHaveBeenCalledWith(expect.objectContaining({
      query: expect.objectContaining({ knowledge_id: 'entry-a' }),
    }))
    expect(listKnowledgeRelations).toHaveBeenCalledWith(expect.objectContaining({
      query: expect.objectContaining({ knowledge_id: 'entry-a' }),
    }))
  })

  it('loads an endpoint title through the generated detail SDK', async () => {
    getKnowledgeEntry.mockResolvedValue({ data: {
      knowledge_release_id: 'release-a',
      knowledge_id: 'entry-b',
      title: '数据殖民主义',
    } })

    await expect(readKnowledgeGraphEntry({
      releaseId: 'release-a',
      knowledgeId: 'entry-b',
    })).resolves.toEqual({ knowledgeId: 'entry-b', title: '数据殖民主义' })
    expect(getKnowledgeEntry).toHaveBeenCalledWith({
      client: { kind: 'generated-client' },
      path: { knowledge_id: 'entry-b' },
      query: { knowledge_release_id: 'release-a' },
    })
  })
})
