import { beforeEach, describe, expect, it, vi } from 'vitest'

const listKnowledgeConnections = vi.hoisted(() => vi.fn())
const listKnowledgeRelationCandidates = vi.hoisted(() => vi.fn())
const listKnowledgeRelations = vi.hoisted(() => vi.fn())
const getKnowledgeEntry = vi.hoisted(() => vi.fn())

vi.mock('../../api/generated/sdk.gen', () => ({
  listKnowledgeConnections,
  listKnowledgeRelationCandidates,
  listKnowledgeRelations,
  getKnowledgeEntry,
}))
vi.mock('../../api/client', () => ({ apiClient: { kind: 'generated-client' } }))

import {
  readIncidentCandidatePage,
  readIncidentRelationPage,
  readKnowledgeGraphEntry,
  readStructuralConnectionPage,
} from './knowledgeGraphApi'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('knowledge graph API adapter', () => {
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
