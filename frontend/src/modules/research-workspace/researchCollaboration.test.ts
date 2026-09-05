import { describe, expect, it } from 'vitest'
import { composeResearchDiscussion, latestResearchAsk, resolveResearchCitation, collapseDocumentNodes } from './researchCollaboration'
import type { AgentConversation } from '../research-agent'

describe('research collaboration', () => {
  it('shows one manuscript card while retaining the argument nodes and meaningful connections', () => {
    const nodes = ['question', 'document', 'document'].map((kind, i) => ({ id: String(i), kind, title: String(i), status: 'developing', provenance: 'agent', citationIds: [] }))
    const result = collapseDocumentNodes({ status: 'ready', question: '问题', nodes, edges: [{ id: 'a', source: '0', target: '1', relation: 'refines' }, { id: 'b', source: '1', target: '2', relation: 'refines' }] } as never, 'manuscript', '研究方案文稿')
    expect(result.nodes.map(node => node.id)).toEqual(['0', 'manuscript'])
    expect(result.edges).toEqual([{ id: 'a', source: '0', target: 'manuscript', relation: 'refines' }])
  })
  it('keeps the selected passage and researcher request together without replacing either', () => {
    expect(composeResearchDiscussion('这里是否推得太远？', { title: '作用机制', content: '平台改变了所有人的偏好。' }))
      .toBe('围绕「作用机制」继续讨论：\n> 平台改变了所有人的偏好。\n\n这里是否推得太远？')
    expect(composeResearchDiscussion('直接提问', null)).toBe('直接提问')
  })
  it('restores only the latest unanswered Ask from successful persisted tool output', () => {
    const turn = { tool_traces: [{ tool: 'ask_research_question', phase: 'finished', output: { question: '能接触到谁？', options: ['社团成员', '其他同学'] } }] }
    const conversation = { turns: [turn] } as unknown as AgentConversation
    expect(latestResearchAsk(conversation)).toEqual({ question: '能接触到谁？', options: ['社团成员', '其他同学'] })
    expect(latestResearchAsk({ ...conversation, turns: [...conversation.turns, { tool_traces: [] } as never] })).toBeNull()
    expect(latestResearchAsk({ turns: [{ tool_traces: [{ ...turn.tool_traces[0], phase: 'failed' }] }] } as unknown as AgentConversation)).toBeNull()
  })
  it('resolves formal source IDs and preserves the release of the cited turn', () => {
    const citation = { citation_id: 'cite-1', source_id: 'source-1', label: '原始文献', kind: 'knowledge' }
    const conversation = { turns: [{ knowledge_release_id: 'release-1', assistant: { citations: [citation] } }] } as unknown as AgentConversation
    expect(resolveResearchCitation(conversation, 'source-1')).toEqual({ citation, knowledgeReleaseId: 'release-1' })
    expect(resolveResearchCitation(conversation, 'missing')).toBeNull()
  })
})
