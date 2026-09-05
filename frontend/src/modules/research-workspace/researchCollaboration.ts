import type { AgentConversation } from '../research-agent'
import type { ResearchCanvasProjection } from './researchCanvasProjection'

export type ResearchDiscussion = { title: string; content: string; sectionId?: string | null; nodeId?: string | null }
export type ResearchAsk = { question: string; options: string[] }

export function collapseDocumentNodes(projection: ResearchCanvasProjection, id: string, title: string): ResearchCanvasProjection {
  const sections = projection.nodes.filter(node => node.kind === 'document')
  const sectionIds = new Set(sections.map(node => node.id))
  const edges = projection.edges.map(edge => ({ ...edge, source: sectionIds.has(edge.source) ? id : edge.source, target: sectionIds.has(edge.target) ? id : edge.target }))
    .filter((edge, index, all) => edge.source !== edge.target && all.findIndex(other => other.source === edge.source && other.target === edge.target && other.relation === edge.relation) === index)
  return { ...projection, edges, nodes: [
    ...projection.nodes.filter(node => node.kind !== 'document'),
    { id, kind: 'document', title, summary: sections.some(section => section.summary) ? '展开阅读全文、编辑与讨论' : '随研究推进形成草稿，点击展开', status: 'developing', provenance: 'user', citationIds: [...new Set(sections.flatMap(section => section.citationIds))] },
  ] }
}

export function composeResearchDiscussion(question: string, focus: ResearchDiscussion | null): string {
  if (!focus) return question
  const quoted = focus.content.slice(0, 2400).split('\n').map(line => `> ${line}`).join('\n')
  return `${focus.nodeId ? `当前画布卡片 ID：${focus.nodeId}（修改此卡请复用该 ID；正式研究记录请使用对应工具）。\n` : ''}围绕「${focus.title}」继续讨论：\n${quoted}\n\n${question}`
}

export function latestResearchAsk(conversation: AgentConversation | null): ResearchAsk | null {
  const traces = conversation?.turns.at(-1)?.tool_traces ?? []
  for (const trace of [...traces].reverse()) {
    if (trace.tool !== 'ask_research_question' || trace.phase !== 'finished') continue
    const value = trace.output as Partial<ResearchAsk> | null
    if (typeof value?.question !== 'string' || !value.question.trim() || !Array.isArray(value.options)) continue
    return { question: value.question, options: value.options.filter((item): item is string => typeof item === 'string') }
  }
  return null
}

export function resolveResearchCitation(conversation: AgentConversation | null, id: string) {
  for (const turn of [...(conversation?.turns ?? [])].reverse()) {
    const citation = turn.assistant.citations.find(item => item.citation_id === id || item.source_id === id || item.knowledge_id === id)
    if (citation) return { citation, knowledgeReleaseId: turn.knowledge_release_id ?? null }
  }
  return null
}
