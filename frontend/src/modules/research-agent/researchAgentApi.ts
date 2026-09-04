import { apiClient } from '../../api/client'
import type {
  AgentResearchJourneyResponse,
} from '../../api/generated'
import type {
  AgentCitation,
  AgentConversation,
  AgentConversationSummary,
  AgentEvent,
  AgentResearchMapPatch,
} from './model'
import type { ResearchStartJourney } from './researchStart'

function toResearchStartJourney(response: AgentResearchJourneyResponse): ResearchStartJourney {
  return {
    conversationId: response.conversation_id,
    status: response.status,
    taskId: response.task_id,
    proposal: response.proposal
      ? {
          proposalId: response.proposal.proposal_id,
          phenomenon: response.proposal.phenomenon,
          researchIntent: response.proposal.research_intent,
          context: response.proposal.context,
          version: response.proposal.version,
          status: response.proposal.status,
        }
      : null,
    resumePath: response.navigation?.resume_path ?? null,
  }
}

export function parseAgentEventStream(stream: string): AgentEvent[] {
  const events: AgentEvent[] = []
  for (const block of stream.split(/\n\n+/)) {
    const eventName = block.match(/^event:\s*(.+)$/m)?.[1]
    const data = block.match(/^data:\s*(.+)$/m)?.[1]
    if (!eventName || !data) continue
    const payload = JSON.parse(data) as Record<string, unknown>
    if (eventName === 'agent_status' && (payload.status === 'thinking' || payload.status === 'answering')) {
      events.push({ type: eventName, status: payload.status })
    } else if (eventName === 'tool_started' && typeof payload.tool === 'string') {
      const event: Extract<AgentEvent, { type: 'tool_started' }> = {
        type: eventName,
        tool: payload.tool,
        call_id: typeof payload.call_id === 'string' ? payload.call_id : null,
        detail: typeof payload.detail === 'string' ? payload.detail : null,
      }
      if ('input' in payload || 'arguments' in payload) {
        event.input = payload.input ?? payload.arguments
      }
      events.push(event)
    } else if (eventName === 'tool_finished' && typeof payload.tool === 'string') {
      const event: Extract<AgentEvent, { type: 'tool_finished' }> = {
        type: eventName,
        tool: payload.tool,
        call_id: typeof payload.call_id === 'string' ? payload.call_id : null,
        detail: typeof payload.detail === 'string' ? payload.detail : null,
      }
      if ('output' in payload) event.output = payload.output
      events.push(event)
    } else if (eventName === 'tool_failed' && typeof payload.tool === 'string') {
      const event: Extract<AgentEvent, { type: 'tool_failed' }> = {
        type: eventName,
        tool: payload.tool,
        call_id: typeof payload.call_id === 'string' ? payload.call_id : null,
        message: String(payload.message ?? payload.detail ?? payload.error ?? '工具调用失败'),
        error_code: typeof payload.error_code === 'string' ? payload.error_code : null,
        detail: typeof payload.detail === 'string' ? payload.detail : null,
      }
      if ('input' in payload) event.input = payload.input
      events.push(event)
    } else if (eventName === 'assistant_delta' && typeof payload.delta === 'string') {
      events.push({ type: eventName, delta: payload.delta })
    } else if (eventName === 'research_ask' && typeof payload.question === 'string' && Array.isArray(payload.options)) {
      events.push({
        type: eventName,
        question: payload.question,
        options: payload.options.filter((item): item is string => typeof item === 'string'),
      })
    } else if (eventName === 'research_plan' && typeof payload.title === 'string' && Array.isArray(payload.steps)) {
      events.push({
        type: eventName,
        title: payload.title,
        steps: payload.steps.filter((item): item is string => typeof item === 'string'),
      })
    } else if (eventName === 'research_step' && typeof payload.step === 'string') {
      events.push({ type: eventName, step: payload.step, status: typeof payload.status === 'string' ? payload.status : undefined })
    } else if (eventName === 'research_result') {
      events.push({
        type: eventName,
        summary: typeof payload.summary === 'string' ? payload.summary : undefined,
        knowledge_count: typeof payload.knowledge_count === 'number' ? payload.knowledge_count : undefined,
        web_count: typeof payload.web_count === 'number' ? payload.web_count : undefined,
      })
    } else if (eventName === 'research_waiting' && typeof payload.run_id === 'string' && (payload.state === 'awaiting_clarification' || payload.state === 'awaiting_plan_confirmation')) {
      events.push({
        type: eventName,
        run_id: payload.run_id,
        state: payload.state,
        title: typeof payload.title === 'string' ? payload.title : undefined,
        question: typeof payload.question === 'string' ? payload.question : undefined,
        options: Array.isArray(payload.options) ? payload.options.filter((item): item is string => typeof item === 'string') : undefined,
        steps: Array.isArray(payload.steps) ? payload.steps.filter((item): item is string => typeof item === 'string') : undefined,
        prompt: typeof payload.prompt === 'string' ? payload.prompt : undefined,
        selected_intent: typeof payload.selected_intent === 'string' ? payload.selected_intent : undefined,
      })
    } else if (eventName === 'citation_added' && payload.citation_id) {
      events.push({ type: eventName, citation: payload as unknown as AgentCitation })
    } else if (eventName === 'canvas_patch' && isResearchMapPatch(payload)) {
      events.push({ type: eventName, patch: payload })
    } else if (eventName === 'turn_started' && payload.conversation_id && payload.run_id) {
      events.push({
        type: eventName,
        conversation_id: String(payload.conversation_id),
        run_id: String(payload.run_id),
        replayed: payload.replayed === true,
        ...(payload.runtime_mode === 'mock' || payload.runtime_mode === 'base' || payload.runtime_mode === 'sft'
          ? { runtime_mode: payload.runtime_mode }
          : {}),
      })
    } else if (eventName === 'turn_completed' && payload.conversation) {
      events.push({
        type: eventName,
        conversation: payload.conversation as AgentConversation,
        knowledge_release_id: String(payload.knowledge_release_id ?? ''),
      })
    } else if (eventName === 'turn_interrupted') {
      events.push({
        type: eventName,
        code: String(payload.code ?? 'interrupted'),
        message: String(payload.message ?? '已停止生成。'),
      })
    } else if (eventName === 'turn_failed') {
      events.push({
        type: eventName,
        code: String(payload.code ?? 'agent_unavailable'),
        message: String(payload.message ?? 'Agent 暂时无法完成回答。'),
      })
    }
  }
  return events
}

function isResearchMapPatch(value: Record<string, unknown>): value is AgentResearchMapPatch {
  return value.schema_version === 1
    && Array.isArray(value.nodes)
    && Array.isArray(value.relations)
    && Array.isArray(value.remove_node_ids)
    && Array.isArray(value.remove_relation_ids)
    && value.nodes.every(isResearchMapNode)
    && value.relations.every(isResearchMapRelation)
    && value.remove_node_ids.every((id) => typeof id === 'string' && id.length > 0)
    && value.remove_relation_ids.every((id) => typeof id === 'string' && id.length > 0)
}

const researchNodeKinds = new Set(['question', 'theory', 'claim', 'evidence', 'gap', 'synthesis'])
const researchNodeStatuses = new Set(['developing', 'grounded', 'open', 'verified', 'challenged', 'complete'])
const researchRelationKinds = new Set(['explains', 'supports', 'challenges', 'derives', 'refines'])

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function isResearchMapNode(value: unknown): boolean {
  return isRecord(value)
    && typeof value.id === 'string'
    && value.id.length > 0
    && typeof value.kind === 'string'
    && researchNodeKinds.has(value.kind)
    && typeof value.title === 'string'
    && value.title.length > 0
    && (value.summary === undefined || value.summary === null || typeof value.summary === 'string')
    && typeof value.status === 'string'
    && researchNodeStatuses.has(value.status)
    && Array.isArray(value.citation_ids)
    && value.citation_ids.every((id) => typeof id === 'string' && id.length > 0)
}

function isResearchMapRelation(value: unknown): boolean {
  return isRecord(value)
    && typeof value.id === 'string'
    && value.id.length > 0
    && typeof value.source === 'string'
    && value.source.length > 0
    && typeof value.target === 'string'
    && value.target.length > 0
    && typeof value.relation === 'string'
    && researchRelationKinds.has(value.relation)
    && (value.label === undefined || value.label === null || typeof value.label === 'string')
}

export async function listAgentConversations(signal?: AbortSignal): Promise<AgentConversationSummary[]> {
  const response = await fetch(apiClient.buildUrl({ url: '/api/agent/conversations' }), {
    credentials: 'include',
    signal,
  })
  if (!response.ok) throw new Error('无法加载对话记录')
  return ((await response.json()) as { items: AgentConversationSummary[] }).items
}

export async function getAgentConversation(
  conversationId: string,
  signal?: AbortSignal,
): Promise<AgentConversation> {
  const response = await fetch(apiClient.buildUrl({
    url: '/api/agent/conversations/{conversation_id}',
    path: { conversation_id: conversationId },
  }), {
    credentials: 'include',
    signal,
  })
  if (!response.ok) throw new Error('无法加载这段对话')
  return await response.json() as AgentConversation
}

export async function renameAgentConversation(
  conversationId: string,
  title: string,
): Promise<AgentConversationSummary> {
  const response = await fetch(apiClient.buildUrl({
    url: '/api/agent/conversations/{conversation_id}',
    path: { conversation_id: conversationId },
  }), {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  if (!response.ok) throw new Error(response.status === 404 ? '这段对话不存在或无权访问。' : '对话名称修改失败')
  return await response.json() as AgentConversationSummary
}

export async function deleteAgentConversation(conversationId: string): Promise<void> {
  const response = await fetch(apiClient.buildUrl({
    url: '/api/agent/conversations/{conversation_id}',
    path: { conversation_id: conversationId },
  }), {
    method: 'DELETE',
    credentials: 'include',
    headers: { 'Idempotency-Key': `delete-agent-conversation:${conversationId}` },
  })
  if (!response.ok) throw new Error(response.status === 404 ? '这段对话不存在或无权访问。' : '对话删除失败')
}

export async function getResearchStartJourney(
  conversationId: string,
  signal?: AbortSignal,
): Promise<ResearchStartJourney> {
  const response = await fetch(apiClient.buildUrl({
    url: '/api/agent/conversations/{conversation_id}/journey',
    path: { conversation_id: conversationId },
  }), {
    credentials: 'include',
    signal,
  })
  if (!response.ok) throw new Error(response.status === 404
    ? '这段研究对话不存在或无权访问。'
    : '无法恢复这次研究的建立状态')
  return toResearchStartJourney(await response.json() as AgentResearchJourneyResponse)
}

export async function confirmResearchStartProposal(
  request: {
    proposalId: string
    expectedVersion: number
    phenomenon: string
    researchIntent: string | null
    context: string | null
    idempotencyKey: string
  },
  signal?: AbortSignal,
): Promise<ResearchStartJourney> {
  const response = await fetch(apiClient.buildUrl({
    url: '/api/agent/research-start-proposals/{proposal_id}/confirm',
    path: { proposal_id: request.proposalId },
  }), {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': request.idempotencyKey,
    },
    body: JSON.stringify({
      expected_version: request.expectedVersion,
      phenomenon: request.phenomenon,
      research_intent: request.researchIntent,
      context: request.context,
    }),
    signal,
  })
  if (response.ok) return toResearchStartJourney(await response.json() as AgentResearchJourneyResponse)
  if (response.status === 409) throw new Error('研究状态已更新，请重新加载后继续。')
  throw new Error('研究暂时未能建立，你的内容已保留。')
}

async function streamAgentTurnOnce(
  payload: { conversation_id: string | null; message: string; idempotencyKey: string; mode?: 'standard' | 'deep_research'; workspace?: 'agent' | 'research'; web_search?: boolean; task_id?: string | null; document_id?: string | null; section_id?: string | null; document_version?: number | null; theory_plan_id?: string | null; material_ids?: string[]; deep_research_run_id?: string | null; deep_research_action?: 'clarify' | 'confirm' | 'skip' | null; deep_research_selection?: string | null },
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(apiClient.buildUrl({ url: '/api/agent/turns' }), {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
      'Idempotency-Key': payload.idempotencyKey,
    },
    body: JSON.stringify({
      conversation_id: payload.conversation_id,
      message: payload.message,
      mode: payload.mode ?? 'standard',
      workspace: payload.workspace ?? 'agent',
      web_search: payload.web_search ?? false,
      task_id: payload.task_id ?? null,
      document_id: payload.document_id ?? null,
      section_id: payload.section_id ?? null,
      document_version: payload.document_version ?? null,
      theory_plan_id: payload.theory_plan_id ?? null,
      material_ids: payload.material_ids ?? [],
      deep_research_run_id: payload.deep_research_run_id ?? null,
      deep_research_action: payload.deep_research_action ?? null,
      deep_research_selection: payload.deep_research_selection ?? null,
    }),
    signal,
  })
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) throw new Error('登录状态已失效，请重新登录后继续研究。')
    if (response.status === 422) throw new Error('问题长度或格式不符合要求，请修改后重试。')
    throw new Error('Agent 暂时无法连接')
  }
  if (!response.body) throw new Error('Agent 暂时无法连接')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let terminalEventSeen = false
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done })
    const blocks = buffer.split(/\n\n+/)
    buffer = blocks.pop() ?? ''
    for (const event of parseAgentEventStream(`${blocks.join('\n\n')}\n\n`)) {
      if (event.type === 'turn_completed' || event.type === 'turn_interrupted' || event.type === 'turn_failed' || event.type === 'research_waiting') {
        terminalEventSeen = true
      }
      onEvent(event)
    }
    if (done) break
  }
  if (buffer.trim()) {
    for (const event of parseAgentEventStream(buffer)) {
      if (event.type === 'turn_completed' || event.type === 'turn_interrupted' || event.type === 'turn_failed' || event.type === 'research_waiting') {
        terminalEventSeen = true
      }
      onEvent(event)
    }
  }
  if (!terminalEventSeen) throw new Error('Agent 流在完成前中断，请重试。')
}

export async function streamAgentTurn(
  payload: { conversation_id: string | null; message: string; idempotencyKey: string; mode?: 'standard' | 'deep_research'; workspace?: 'agent' | 'research'; web_search?: boolean; task_id?: string | null; document_id?: string | null; section_id?: string | null; document_version?: number | null; theory_plan_id?: string | null; material_ids?: string[]; deep_research_run_id?: string | null; deep_research_action?: 'clarify' | 'confirm' | 'skip' | null; deep_research_selection?: string | null },
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  while (true) {
    try {
      await streamAgentTurnOnce(payload, onEvent, signal)
      return
    } catch (cause: unknown) {
      if (signal?.aborted || (cause as { name?: string } | null)?.name === 'AbortError') throw cause
      const recoverable = cause instanceof TypeError
        || (cause instanceof Error && cause.message.includes('完成前中断'))
      if (!recoverable) throw cause
      await new Promise<void>((resolve, reject) => {
        const timeout = globalThis.setTimeout(resolve, 250)
        signal?.addEventListener('abort', () => {
          globalThis.clearTimeout(timeout)
          reject(new DOMException('Aborted', 'AbortError'))
        }, { once: true })
      })
    }
  }
}

export async function stopAgentRun(runId: string): Promise<void> {
  const response = await fetch(apiClient.buildUrl({
    url: '/api/agent/runs/{run_id}/stop',
    path: { run_id: runId },
  }), {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Idempotency-Key': globalThis.crypto?.randomUUID?.() ?? `stop-agent-run:${runId}`,
    },
  })
  if (!response.ok) throw new Error('无法停止当前回答')
}
