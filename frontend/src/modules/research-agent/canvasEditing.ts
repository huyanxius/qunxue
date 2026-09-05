import type { AgentConversation, AgentResearchMapNode } from './model'

export function canvasSuggestions(conversation: AgentConversation | null, node: AgentResearchMapNode) {
  return (conversation?.turns ?? []).flatMap(turn => turn.tool_traces ?? []).flatMap(trace => {
    if (trace.tool !== 'update_research_map' || trace.phase !== 'finished') return []
    const output = trace.output as { suggested_nodes?: Array<AgentResearchMapNode & { expected_title: string; expected_summary?: string | null }> } | null
    return (output?.suggested_nodes ?? []).filter(item => item.id === node.id && item.expected_title === node.title
      && (item.expected_summary ?? '') === (node.summary ?? '')
      && (item.title !== node.title || (item.summary ?? '') !== (node.summary ?? '')))
      .map(item => ({ ...item, key: `${trace.call_id}:${item.id}` }))
  }).reverse()
}
