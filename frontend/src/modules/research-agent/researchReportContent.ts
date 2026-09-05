import type { AgentCitation, AgentConversation } from './model'

// 研究报告直接沿用 Agent 对话本身：一轮问答就是一节，不另外让模型再写一遍。
// 这个文件只负责把对话整理成排版无关的中间结构，Word 与 PDF 两条导出各自消费它。

export type ResearchReportSection = {
  question: string
  answer: string
}

export type ResearchReferenceGroup = 'knowledge' | 'web' | 'material'

export type ResearchReference = {
  index: number
  group: ResearchReferenceGroup
  title: string
  detail: string | null
  url: string | null
}

export type ResearchReport = {
  title: string
  subtitle: string
  meta: string[]
  sections: ResearchReportSection[]
  references: ResearchReference[]
}

const CITATION_MARKER = /\[(?:citation_id:)?(?:knowledge|source):[A-Za-z0-9_.:-]+\]/g

/** 正文里的 `[knowledge:D1:C213]` 是模型给前端的锚点，读者不该看到它。 */
export function displayAgentText(value: string) {
  return value.replace(CITATION_MARKER, '')
}

/**
 * 卡片上那一句结论。取正文第一段实质内容——研究回答的第一段通常就是直接回应问题的
 * 判断句，标题行和引导语不算。
 */
export function conclusionDigest(answer: string, limit = 96) {
  const paragraphs = displayAgentText(answer)
    .split(/\n{2,}|\n(?=[#>\-*\d])/)
    .map((block) => block
      .replace(/^\s*#{1,6}\s*/, '')
      .replace(/^\s*[>\-*+]\s*/, '')
      .replace(/^\s*\d+[.)]\s*/, '')
      .replace(/[*_`]/g, '')
      .trim())
    .filter((block) => block.length > 12)
  const first = paragraphs[0] ?? ''
  if (first.length <= limit) return first
  // 尽量断在句号上，断不出来再硬截。
  const clipped = first.slice(0, limit)
  const boundary = Math.max(clipped.lastIndexOf('。'), clipped.lastIndexOf('；'), clipped.lastIndexOf('，'))
  return `${boundary > limit * 0.5 ? clipped.slice(0, boundary + 1) : clipped}…`
}

export function formatElapsed(seconds: number) {
  const total = Math.max(0, Math.round(seconds))
  if (total < 60) return `${total} 秒`
  return `${Math.floor(total / 60)} 分 ${total % 60} 秒`
}

function citationGroup(citation: AgentCitation): ResearchReferenceGroup {
  if (citation.source_kind === 'web') return 'web'
  if (citation.kind === 'material' || citation.kind === 'research_material') return 'material'
  return 'knowledge'
}

function citationUrl(citation: AgentCitation) {
  if (citation.source_kind !== 'web' || !citation.source_id) return null
  try {
    return new URL(citation.source_id).toString()
  } catch {
    return null
  }
}

const groupOrder: ResearchReferenceGroup[] = ['knowledge', 'web', 'material']

export const referenceGroupTitles: Record<ResearchReferenceGroup, string> = {
  knowledge: '群学知识库',
  web: '公开网页',
  material: '个人研究材料',
}

/**
 * 同一条知识条目会在多轮里反复被引，报告里只列一次；编号按知识库、网页、材料的顺序
 * 连排，和正文里"依据 1、2、3"的呈现顺序一致。
 */
export function collectReferences(citations: AgentCitation[]): ResearchReference[] {
  const seen = new Set<string>()
  const byGroup = new Map<ResearchReferenceGroup, ResearchReference[]>()
  for (const citation of citations) {
    if (citation.deleted) continue
    const group = citationGroup(citation)
    const url = citationUrl(citation)
    const key = `${group}:${citation.knowledge_id ?? citation.source_id ?? citation.label}`
    if (seen.has(key)) continue
    seen.add(key)
    const detail = group === 'web' ? null : citation.knowledge_id ?? null
    const bucket = byGroup.get(group) ?? []
    bucket.push({ index: 0, group, title: citation.label.trim() || '未命名来源', detail, url })
    byGroup.set(group, bucket)
  }
  let index = 0
  return groupOrder.flatMap((group) => (byGroup.get(group) ?? []).map((reference) => {
    index += 1
    return { ...reference, index }
  }))
}

function conversationDate(value: string | undefined) {
  const parsed = value ? new Date(value) : new Date()
  const date = Number.isNaN(parsed.valueOf()) ? new Date() : parsed
  return `${date.getFullYear()} 年 ${date.getMonth() + 1} 月 ${date.getDate()} 日`
}

export function buildResearchReport({
  conversation,
  elapsedSeconds,
  fallbackTitle,
}: {
  conversation: AgentConversation
  elapsedSeconds?: number | null
  fallbackTitle?: string
}): ResearchReport {
  const sections = conversation.turns
    .filter((turn) => turn.assistant.content.trim())
    .map((turn) => ({
      question: turn.user.content.trim(),
      answer: displayAgentText(turn.assistant.content).trim(),
    }))
  const citations = conversation.turns.flatMap((turn) => turn.assistant.citations)
  const references = collectReferences(citations)
  const knowledgeCount = references.filter((reference) => reference.group === 'knowledge').length
  const webCount = references.filter((reference) => reference.group === 'web').length
  const materialCount = references.filter((reference) => reference.group === 'material').length
  const meta = [conversationDate(conversation.updated_at)]
  if (elapsedSeconds != null && elapsedSeconds > 0) meta.push(`研究用时 ${formatElapsed(elapsedSeconds)}`)
  if (knowledgeCount) meta.push(`知识库 ${knowledgeCount} 条`)
  if (webCount) meta.push(`网页资料 ${webCount} 条`)
  if (materialCount) meta.push(`研究材料 ${materialCount} 份`)
  return {
    title: (conversation.title || fallbackTitle || sections[0]?.question || '研究报告').trim(),
    subtitle: '研究报告',
    meta,
    sections,
    references,
  }
}

export function researchReportFilename(report: ResearchReport, extension: string) {
  const safe = report.title.replace(/[\\/:*?"<>|\n\r]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 40) || '研究报告'
  return `群学致知-${safe}.${extension}`
}
