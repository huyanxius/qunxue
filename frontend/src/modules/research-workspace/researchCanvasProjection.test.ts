import { describe, expect, it } from 'vitest'

import {
  createEmptyResearchCanvasProjection,
  projectResearchCanvas,
} from './researchCanvasProjection'
import type { AgentConversation, AgentResearchMapPatch, AgentToolStep } from '../research-agent'

const patch: AgentResearchMapPatch = {
  schema_version: 1,
  nodes: [
    {
      id: 'question-youth-loneliness',
      kind: 'question',
      title: '为什么年轻人越来越孤独？',
      summary: '把个体体验放回关系结构与制度节奏中解释。',
      status: 'developing',
      citation_ids: [],
    },
    {
      id: 'claim-time-poverty',
      kind: 'claim',
      title: '时间贫困压缩稳定关系的维护空间',
      summary: '高强度劳动与通勤使重复互动更难持续。',
      status: 'grounded',
      citation_ids: ['knowledge:loneliness'],
    },
  ],
  relations: [{
    id: 'relation-time-explains-question',
    source: 'claim-time-poverty',
    target: 'question-youth-loneliness',
    relation: 'explains',
    label: '结构机制',
  }],
  remove_node_ids: [],
  remove_relation_ids: [],
}

const conversation: AgentConversation = {
  conversation_id: 'conversation-1',
  title: '年轻人的孤独',
  created_at: '2026-08-19T01:00:00Z',
  updated_at: '2026-08-19T01:02:00Z',
  turn_count: 1,
  research_map: {
    schema_version: 1,
    nodes: patch.nodes,
    relations: patch.relations,
  },
  turns: [
    {
      turn_id: 'turn-1',
      user: {
        message_id: 'message-1',
        role: 'user',
        content: '怎么解释年轻人越来越孤独？',
        citations: [],
        sequence: 0,
        created_at: '2026-08-19T01:00:00Z',
      },
      assistant: {
        message_id: 'message-2',
        role: 'assistant',
        content: '可以从关系结构、劳动节奏与城市流动三个层面继续分析。',
        citations: [],
        sequence: 1,
        created_at: '2026-08-19T01:02:00Z',
      },
      canvas_patches: [patch],
      tool_traces: [{
        tool: 'update_research_map',
        phase: 'finished',
        call_id: 'call-map-1',
        output: patch,
      }],
    },
  ],
}

const runningSearch: AgentToolStep = {
  id: 'call-search',
  tool: 'search_knowledge',
  label: '检索知识库',
  status: 'running',
  input: { query: '青年孤独' },
}

describe('research canvas projection', () => {
  it('starts with an honest empty projection', () => {
    expect(createEmptyResearchCanvasProjection()).toEqual({
      status: 'empty',
      nodes: [],
      edges: [],
      question: null,
    })
  })

  it('keeps tool activity out of the canvas while the Agent is structuring', () => {
    const projection = projectResearchCanvas({
      conversation: null,
      streamingTurn: {
        question: '请检索知识库解释青年孤独',
        answer: '',
        citations: [],
        toolSteps: [runningSearch],
        canvasPatches: [],
      },
    })

    expect(projection.status).toBe('retrieving')
    expect(projection.question).toBe('请检索知识库解释青年孤独')
    expect(projection.nodes).toEqual([])
  })

  it('projects only the persisted Agent-authored research structure', () => {
    const projection = projectResearchCanvas({ conversation })

    expect(projection.status).toBe('ready')
    expect(projection.nodes).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'question-youth-loneliness', kind: 'question' }),
      expect.objectContaining({
        id: 'claim-time-poverty',
        kind: 'claim',
        status: 'grounded',
        citationIds: ['knowledge:loneliness'],
      }),
    ]))
    expect(projection.edges).toEqual([
      expect.objectContaining({
        source: 'claim-time-poverty',
        target: 'question-youth-loneliness',
        relation: 'explains',
      }),
    ])
    expect(projection.nodes.map((node) => node.kind)).toEqual(['question', 'claim'])
  })

  it('applies live patches over the persisted map without inventing answer cards', () => {
    const livePatch: AgentResearchMapPatch = {
      schema_version: 1,
      nodes: [{
        id: 'gap-comparison-group',
        kind: 'gap',
        title: '缺少不同城市层级的比较',
        summary: '需要补充可比较材料。',
        status: 'open',
        citation_ids: [],
      }],
      relations: [{
        id: 'relation-gap-refines-question',
        source: 'gap-comparison-group',
        target: 'question-youth-loneliness',
        relation: 'refines',
      }],
      remove_node_ids: [],
      remove_relation_ids: [],
    }

    const projection = projectResearchCanvas({
      conversation,
      streamingTurn: {
        question: '还缺什么证据？',
        answer: '需要补充比较。',
        citations: [],
        toolSteps: [],
        canvasPatches: [livePatch],
      },
    })

    expect(projection.nodes).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'gap-comparison-group', kind: 'gap' }),
    ]))
    expect(projection.nodes.some((node) => node.title === 'Agent 综合')).toBe(false)
  })

  it.each([
    { interrupted: true, failure: undefined },
    { interrupted: false, failure: '研究地图更新失败' },
  ])('discards uncommitted live patches after an unsuccessful turn', (settlement) => {
    const uncommittedPatch: AgentResearchMapPatch = {
      schema_version: 1,
      nodes: [{
        id: 'claim-uncommitted',
        kind: 'claim',
        title: '尚未提交的临时判断',
        status: 'developing',
        citation_ids: [],
      }],
      relations: [],
      remove_node_ids: [],
      remove_relation_ids: [],
    }

    const projection = projectResearchCanvas({
      conversation,
      streamingTurn: {
        question: '继续分析',
        answer: '',
        citations: [],
        toolSteps: [],
        canvasPatches: [uncommittedPatch],
        ...settlement,
      },
    })

    expect(projection.nodes.some((node) => node.id === 'claim-uncommitted')).toBe(false)
    expect(projection.nodes.map((node) => node.id)).toEqual([
      'question-youth-loneliness',
      'claim-time-poverty',
    ])
  })
})
