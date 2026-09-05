import type { ResearchCanvasNode } from './researchCanvasProjection'

export const CANVAS_CARD_SIZE = { width: 304, height: 220 }
export const CANVAS_COLUMN_GAP = 440
export const CANVAS_ROW_GAP = 284
export const researchCanvasStages = [
  { title: '研究起点', description: '问题与现象', kinds: ['question', 'phenomenon'] },
  { title: '解释与主张', description: '如何理解这个问题', kinds: ['theory', 'claim'] },
  { title: '证据与待证', description: '已有依据与尚待回答', kinds: ['evidence', 'gap'] },
  { title: '综合与写作', description: '形成判断，写入文稿', kinds: ['synthesis', 'document'] },
] as const

export type CanvasPosition = { x: number; y: number }

// 按研究角色分层；连线保留真实方向，不把“证据支持主张”倒写成流程依赖。
export function arrangeResearchCanvas(nodes: ResearchCanvasNode[], previous = new Map<string, CanvasPosition>()) {
  const positions = new Map<string, CanvasPosition>()
  for (const node of nodes) {
    const saved = previous.get(node.id)
    if (saved) { positions.set(node.id, saved) }
  }
  const stageIndex = (node: ResearchCanvasNode) => researchCanvasStages.findIndex(stage => (stage.kinds as readonly string[]).includes(node.kind))
  const sorted = [...nodes].sort((a, b) => stageIndex(a) - stageIndex(b)
    || researchCanvasStages[stageIndex(a)].kinds.indexOf(a.kind as never) - researchCanvasStages[stageIndex(b)].kinds.indexOf(b.kind as never)
    || a.id.localeCompare(b.id))
  for (const node of sorted) {
    if (positions.has(node.id)) continue
    const x = stageIndex(node) * CANVAS_COLUMN_GAP
    let y = 84
    while ([...positions.values()].some(point => Math.abs(point.x - x) < CANVAS_CARD_SIZE.width + 24 && Math.abs(point.y - y) < CANVAS_CARD_SIZE.height + 32)) y += CANVAS_ROW_GAP
    positions.set(node.id, { x, y })
  }
  return positions
}
