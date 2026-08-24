import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const cytoscapeMock = vi.hoisted(() => vi.fn())
const readStructuralConnectionPage = vi.hoisted(() => vi.fn())
const readIncidentCandidatePage = vi.hoisted(() => vi.fn())
const readIncidentRelationPage = vi.hoisted(() => vi.fn())
const readKnowledgeGraphEntry = vi.hoisted(() => vi.fn())

vi.mock('cytoscape', () => ({ default: cytoscapeMock }))
vi.mock('./knowledgeGraphApi', () => ({
  readStructuralConnectionPage,
  readIncidentCandidatePage,
  readIncidentRelationPage,
  readKnowledgeGraphEntry,
}))

import { KnowledgeGraphWorkspace } from './KnowledgeGraphWorkspace'

const cores: Array<{ on: ReturnType<typeof vi.fn> }> = []

beforeEach(() => {
  cores.length = 0
  cytoscapeMock.mockReset()
  cytoscapeMock.mockImplementation(() => {
    const core = {
      destroy: vi.fn(),
      fit: vi.fn(),
      getElementById: vi.fn(() => ({
        nonempty: () => true,
        predecessors: () => ({ kind: 'predecessors' }),
        union: () => ({ kind: 'focused-path' }),
      })),
      on: vi.fn(),
    }
    cores.push(core)
    return core
  })
  readStructuralConnectionPage.mockImplementation(async ({ sourceNodeId }) => ({
    connections: sourceNodeId === 'D1'
      ? [{
          connection_id: 'structure:dimension-category',
          connection_kind: 'structure',
          source_node_id: 'D1', source_node_type: 'dimension', source_title: '本体论',
          target_node_id: 'D1:C001', target_node_type: 'category', target_title: '社会关系',
          connection_type: 'contains', direction: 'outbound',
        }]
      : [{
          connection_id: 'structure:category-entry',
          connection_kind: 'structure',
          source_node_id: 'D1:C001', source_node_type: 'category', source_title: '社会关系',
          target_node_id: 'D1:C001:E001', target_node_type: 'entry', target_title: '社会资本',
          connection_type: 'contains', direction: 'outbound',
        }],
  }))
  readIncidentRelationPage.mockResolvedValue({ relations: [], totalCount: 0 })
  readIncidentCandidatePage.mockResolvedValue({
    totalCount: 1,
    candidates: [{
      candidate_id: 'candidate:one',
      source_knowledge_id: 'D1:C001:E001',
      target_knowledge_id: 'D1:C001:E002',
      suggested_relation_type: 'extends',
      direction: 'outbound',
      evidence_excerpt: '社会资本扩展了关系资源讨论。',
      evidence_locator: '本体论/社会关系.md#content-line-9',
      evidence_source_id: 'source:D1:C001:E001',
      source_content_version: 1,
      target_content_version: 1,
      producer: 'explicit-title-trigger',
      producer_config_version: 'explicit-title-trigger-v1',
      score: 1,
      trigger_reason: 'trigger=扩展了',
      review_status: 'pending',
      review_record_id: null,
    }],
  })
  readKnowledgeGraphEntry.mockResolvedValue({
    knowledgeId: 'D1:C001:E002',
    title: '关系资源',
  })
})

afterEach(cleanup)

it('restores a searched entry path and keeps pending evidence opt-in', async () => {
  render(
    <KnowledgeGraphWorkspace
      releaseId="release-a"
      focusEntry={{
        knowledgeId: 'D1:C001:E001',
        title: '社会资本',
        reviewStatus: 'pending',
        directoryPath: [
          { nodeId: 'D1', nodeType: 'dimension', title: '本体论' },
          { nodeId: 'D1:C001', nodeType: 'category', title: '社会关系' },
        ],
      }}
      onSelectKnowledge={vi.fn()}
    />,
  )

  await waitFor(() => {
    expect(readStructuralConnectionPage).toHaveBeenCalledWith(expect.objectContaining({
      sourceNodeId: 'D1:C001',
    }))
  })
  expect(screen.getByText('当前条目：社会资本')).toBeVisible()
  expect(screen.getByText('当前条目没有知识关系。')).toBeVisible()
  expect(readIncidentCandidatePage).not.toHaveBeenCalled()

  fireEvent.click(screen.getByRole('button', { name: '开启候选关系' }))
  await waitFor(() => expect(readIncidentCandidatePage).toHaveBeenCalled())
  expect(readKnowledgeGraphEntry).toHaveBeenCalledWith({
    releaseId: 'release-a',
    knowledgeId: 'D1:C001:E002',
  })

  const latestOptions = cytoscapeMock.mock.calls.at(-1)?.[0]
  expect(latestOptions.elements.find(
    (element: { data: { id: string } }) => element.data.id === 'D1:C001:E001',
  )?.data.displayLabel).toBe('社会资本')

  const edgeTap = cores.at(-1)?.on.mock.calls.find(
    ([event, selector]) => event === 'tap' && selector === 'edge',
  )?.[2]
  edgeTap?.({ target: { id: () => 'candidate:one' } })

  const panel = await screen.findByLabelText('候选关系详情')
  expect(within(panel).getByText('社会资本（D1:C001:E001） → 关系资源（D1:C001:E002）')).toBeVisible()
  expect(within(panel).getByText('社会资本扩展了关系资源讨论。')).toBeVisible()
  expect(within(panel).getByText(/确定性规则命中，不是校准置信度/)).toBeVisible()
  expect(within(panel).getByText('本体论/社会关系.md#content-line-9')).toBeVisible()
})
