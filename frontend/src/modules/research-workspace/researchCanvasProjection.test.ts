import { describe, expect, it } from 'vitest'

import {
  createEmptyResearchCanvasProjection,
  projectResearchCanvas,
} from './researchCanvasProjection'
import type { AgentConversation, AgentToolStep } from '../research-agent'

const conversation: AgentConversation = {
  conversation_id: 'conversation-1',
  title: '年轻人的孤独',
  created_at: '2026-08-19T01:00:00Z',
  updated_at: '2026-08-19T01:02:00Z',
  turn_count: 1,
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
        citations: [
          {
            citation_id: 'knowledge:loneliness',
            label: '青年孤独与社会联结',
            kind: 'entry',
            excerpt: '稳定关系机会与城市流动共同影响孤独经验。',
            knowledge_id: 'D1:C001',
          },
        ],
        sequence: 1,
        created_at: '2026-08-19T01:02:00Z',
      },
      tool_traces: [],
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

  it('exposes the live question and tool state while the Agent is working', () => {
    const projection = projectResearchCanvas({
      conversation: null,
      streamingTurn: {
        question: '请检索知识库解释青年孤独',
        answer: '',
        citations: [],
        toolSteps: [runningSearch],
      },
    })

    expect(projection.status).toBe('retrieving')
    expect(projection.question).toBe('请检索知识库解释青年孤独')
    expect(projection.nodes).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'question:streaming', kind: 'question', status: 'running' }),
      expect.objectContaining({ id: 'tool:call-search', kind: 'tool', status: 'running', title: '检索知识库' }),
    ]))
    expect(projection.edges).toContainEqual(expect.objectContaining({ source: 'question:streaming', target: 'tool:call-search' }))
  })

  it('rehydrates evidence and synthesis from the real completed conversation', () => {
    const projection = projectResearchCanvas({ conversation })

    expect(projection.status).toBe('ready')
    expect(projection.question).toBe('怎么解释年轻人越来越孤独？')
    expect(projection.nodes).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'question:turn-1', kind: 'question', status: 'complete' }),
      expect.objectContaining({ id: 'evidence:knowledge:loneliness', kind: 'evidence', provenance: 'knowledge' }),
      expect.objectContaining({ id: 'synthesis:turn-1', kind: 'synthesis', status: 'complete' }),
    ]))
    expect(projection.edges).toEqual(expect.arrayContaining([
      expect.objectContaining({ source: 'question:turn-1', target: 'synthesis:turn-1' }),
      expect.objectContaining({ source: 'evidence:knowledge:loneliness', target: 'synthesis:turn-1' }),
    ]))
  })

  it('uses the product label for persisted tool traces instead of exposing adapter names', () => {
    const projection = projectResearchCanvas({
      conversation: {
        ...conversation,
        turns: [{
          ...conversation.turns[0],
          tool_traces: [{
            tool: 'search_knowledge',
            phase: 'finished',
            call_id: 'call-persisted-search',
            input: { query: '青年孤独' },
            output: { items: [] },
            detail: '检索完成',
            error: null,
          }],
        }],
      },
    })

    expect(projection.nodes).toEqual(expect.arrayContaining([
      expect.objectContaining({
        id: 'tool:call-persisted-search',
        title: '检索知识库',
      }),
    ]))
    expect(projection.nodes).not.toEqual(expect.arrayContaining([
      expect.objectContaining({
        id: 'tool:call-persisted-search',
        title: 'search_knowledge',
      }),
    ]))
  })

  it('keeps failure visible without inventing an evidence node', () => {
    const projection = projectResearchCanvas({
      conversation: null,
      streamingTurn: {
        question: '请找出关于平台劳动的证据',
        answer: '',
        citations: [],
        toolSteps: [{
          id: 'call-failed',
          tool: 'search_knowledge',
          label: '检索知识库',
          status: 'failed',
          detail: '知识库检索暂时失败',
        }],
        failure: 'Agent 暂时无法完成回答',
      },
    })

    expect(projection.status).toBe('failed')
    expect(projection.nodes).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'tool:call-failed', kind: 'tool', status: 'failed' }),
    ]))
    expect(projection.nodes.some((node) => node.kind === 'evidence')).toBe(false)
  })

  it('marks interrupted question and tool nodes as interrupted', () => {
    const projection = projectResearchCanvas({
      conversation: null,
      streamingTurn: {
        question: '请检索关于青年孤独的证据',
        answer: '',
        citations: [],
        toolSteps: [{
          id: 'call-interrupted',
          tool: 'search_knowledge',
          label: '检索知识库',
          status: 'failed',
          interrupted: true,
          detail: '已停止',
        }],
        interrupted: true,
      },
    })

    expect(projection.status).toBe('interrupted')
    expect(projection.nodes).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'question:streaming', status: 'interrupted' }),
      expect.objectContaining({ id: 'tool:call-interrupted', status: 'interrupted' }),
    ]))
  })
})
