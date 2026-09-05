import type { ResearchMemory } from '../../modules/research-memory'

// Preview records stay in component state; they never enter the user's memory store.
export function memoryPreview(taskId: string | null): ResearchMemory[] {
  const entries: Array<[string, string, ResearchMemory['origin'], string | null]> = taskId ? [
    ['research.question', '研究学生如何判断 Agent 的知识权威。', 'manual', null],
    ['method.coding', '先开放编码，暂不套用理论。', 'explicit', '这个项目先做开放编码，不急着套理论。'],
    ['method.silence', '分析沉默与犹豫时，保留上下文和停顿信息，避免直接把沉默解释为不信任。', 'learned', '这里的沉默可能是在想怎么表达，也可能是不同意，先把前后文留下。'],
    ['writing.anonymity', '用 A、B、C 匿名标记参与者。', 'manual', null],
  ] : [
    ['interests', '关注知识生产、教育与技术。', 'explicit', '记住，我更关心人怎样判断和使用这些知识。'],
    ['writing.style', '用连贯中文讨论研究，避免堆砌术语。', 'manual', null],
    ['research.habits', '比较不同解释时，习惯先回到原始材料核验，并记录解释成立的条件和可能的反例。', 'learned', '我们先回到原话看看，也找一找有没有不符合这个解释的例子。'],
    ['collaboration', '建议说明依据，由研究者判断。', 'explicit', '建议可以给，但最后的解释需要由我来判断。'],
    ['reading.preferences', '阅读笔记希望保留论点、证据和疑问，便于之后跨文献比较。', 'learned', '这篇也按论点、证据、疑问来整理吧，后面方便放在一起比较。'],
  ]
  return entries.map(([key, content, origin, source_quote], i) => ({
    memory_id: `preview-memory-${i}`, task_id: taskId, key, content, origin, version: 1,
    created_at: `2026-09-0${5 - i}T08:30:00Z`, updated_at: `2026-09-0${5 - i}T08:30:00Z`,
    source_conversation_id: null, source_message_id: null, source_quote,
  }))
}
