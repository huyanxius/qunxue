import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const buildUrl = vi.hoisted(() => vi.fn())

vi.mock('../../api/client', () => ({ apiClient: { buildUrl } }))

import {
  confirmResearchStartProposal,
  getAgentConversation,
  getResearchStartJourney,
  listAgentConversations,
  parseAgentEventStream,
  streamAgentTurn,
} from './researchAgentApi'

beforeEach(() => {
  buildUrl.mockReset()
  buildUrl.mockImplementation(({ path, url }: {
    path?: Record<string, unknown>
    url: string
  }) => {
    const resolvedPath = Object.entries(path ?? {}).reduce(
      (current, [key, value]) => current.replace(`{${key}}`, encodeURIComponent(String(value))),
      url,
    )
    return `https://api.qunxue.test${resolvedPath}`
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('research agent SSE adapter', () => {
  it('preserves the Agent runtime mode reported by the independent runner', () => {
    expect(parseAgentEventStream(
      'event: turn_started\ndata: {"conversation_id":"conversation-1","run_id":"run-1","replayed":false,"runtime_mode":"base"}\n',
    )).toEqual([{
      type: 'turn_started',
      conversation_id: 'conversation-1',
      run_id: 'run-1',
      replayed: false,
      runtime_mode: 'base',
    }])
  })

  it('parses streamed deltas and citation events without exposing framework messages', () => {
    const events = parseAgentEventStream([
      'event: agent_status',
      'data: {"status":"thinking"}',
      '',
      'event: assistant_delta',
      'data: {"delta":"知识"}',
      '',
      'event: citation_added',
      'data: {"citation_id":"knowledge:C1","label":"符号互动论","kind":"entry"}',
      '',
    ].join('\n'))

    expect(events).toEqual([
      { type: 'agent_status', status: 'thinking' },
      { type: 'assistant_delta', delta: '知识' },
      {
        type: 'citation_added',
        citation: { citation_id: 'knowledge:C1', label: '符号互动论', kind: 'entry' },
      },
    ])
  })

  it('ignores retired Agent statuses outside the frozen stream contract', () => {
    expect(parseAgentEventStream(
      'event: agent_status\ndata: {"status":"retrieving"}\n',
    )).toEqual([])
  })

  it('parses tool progress events for the visible Agent work trace', () => {
    const events = parseAgentEventStream([
      'event: tool_started',
      'data: {"tool":"search_knowledge","call_id":"tool-call-1","input":{"query":"青年孤独"}}',
      '',
      'event: tool_finished',
      'data: {"tool":"search_knowledge","call_id":"tool-call-1","output":{"summary":"找到 3 条可引用证据"}}',
      '',
    ].join('\n'))

    expect(events).toEqual([
      {
        type: 'tool_started',
        tool: 'search_knowledge',
        call_id: 'tool-call-1',
        input: { query: '青年孤独' },
        detail: null,
      },
      {
        type: 'tool_finished',
        tool: 'search_knowledge',
        call_id: 'tool-call-1',
        output: { summary: '找到 3 条可引用证据' },
        detail: null,
      },
    ])
  })

  it('parses a typed research canvas patch independently from tool activity', () => {
    const patch = {
      schema_version: 1 as const,
      nodes: [{
        id: 'claim-time-poverty',
        kind: 'claim' as const,
        title: '时间贫困压缩稳定关系的维护空间',
        summary: '高强度劳动与通勤使重复互动更难持续。',
        status: 'grounded' as const,
        citation_ids: [],
      }],
      relations: [],
      remove_node_ids: [],
      remove_relation_ids: [],
    }

    expect(parseAgentEventStream(
      `event: canvas_patch\ndata: ${JSON.stringify(patch)}\n`,
    )).toEqual([{ type: 'canvas_patch', patch }])
  })

  it('parses a failed tool call without turning it into a completed step', () => {
    expect(parseAgentEventStream([
      'event: tool_failed',
      'data: {"tool":"search_knowledge","call_id":"tool-call-2","input":{"query":"青年孤独"},"message":"知识库暂时不可用","error_code":"knowledge_unavailable","detail":"请稍后重试"}',
      '',
    ].join('\n'))).toEqual([
      {
        type: 'tool_failed',
        tool: 'search_knowledge',
        call_id: 'tool-call-2',
        input: { query: '青年孤独' },
        message: '知识库暂时不可用',
        error_code: 'knowledge_unavailable',
        detail: '请稍后重试',
      },
    ])
  })

  it('parses an explicit interruption event', () => {
    expect(parseAgentEventStream(
      'event: turn_interrupted\ndata: {"code":"interrupted","message":"已停止生成"}\n',
    )).toEqual([
      { type: 'turn_interrupted', code: 'interrupted', message: '已停止生成' },
    ])
  })

  it('builds every Agent request through the shared API client base URL', async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.endsWith('/api/agent/conversations')) {
        return new Response('{"items":[]}', { headers: { 'Content-Type': 'application/json' } })
      }
      if (url.includes('/api/agent/conversations/')) {
        return new Response('{"conversation_id":"conversation/1"}', {
          headers: { 'Content-Type': 'application/json' },
        })
      }
      return new Response(
        'event: turn_failed\ndata: {"code":"agent_unavailable","message":"暂不可用"}\n\n',
        { headers: { 'Content-Type': 'text/event-stream' } },
      )
    })
    vi.stubGlobal('fetch', fetch)

    await listAgentConversations()
    await getAgentConversation('conversation/1')
    await streamAgentTurn(
      { conversation_id: null, message: '你好', idempotencyKey: 'turn-1' },
      () => undefined,
    )

    expect(buildUrl.mock.calls.map(([options]) => options)).toEqual([
      { url: '/api/agent/conversations' },
      {
        url: '/api/agent/conversations/{conversation_id}',
        path: { conversation_id: 'conversation/1' },
      },
      { url: '/api/agent/turns' },
    ])
    expect(fetch.mock.calls.map(([input]) => input)).toEqual([
      'https://api.qunxue.test/api/agent/conversations',
      'https://api.qunxue.test/api/agent/conversations/conversation%2F1',
      'https://api.qunxue.test/api/agent/turns',
    ])
  })

  it('rejects a truncated SSE response that never reaches a terminal event', async () => {
    const fetch = vi.fn(async () => new Response(
      'event: turn_started\ndata: {"conversation_id":"conversation-1","run_id":"run-1","replayed":false}\n\n'
        + 'event: assistant_delta\ndata: {"delta":"半段回答"}\n\n',
      { headers: { 'Content-Type': 'text/event-stream' } },
    ))
    vi.stubGlobal('fetch', fetch)

    await expect(streamAgentTurn(
      { conversation_id: null, message: '问题', idempotencyKey: 'truncated-1' },
      () => undefined,
    )).rejects.toThrow('Agent 流在完成前中断')
  })

  it('surfaces a validation response as an actionable input error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 422 })))

    await expect(streamAgentTurn(
      { conversation_id: null, message: '超长问题', idempotencyKey: 'invalid-1' },
      () => undefined,
    )).rejects.toThrow('问题长度或格式不符合要求')
  })

  it('loads and confirms the conversation-owned research start through the shared client', async () => {
    const journey = {
      conversation_id: 'conversation/1',
      status: 'proposal_pending',
      proposal: {
        proposal_id: 'proposal-1',
        version: 3,
        status: 'pending_confirmation',
        phenomenon: '社区互助正在减少',
        research_intent: '理解互助衰退的机制',
        context: '大城市老旧小区',
        knowledge_release_id: 'release-formal-1',
        source_turn_id: 'turn-1',
        source_run_id: 'run-1',
      },
      task_id: null,
      navigation: null,
    }
    const confirmed = {
      ...journey,
      status: 'task_bound',
      proposal: { ...journey.proposal, status: 'confirmed' },
      task_id: 'task-1',
      navigation: {
        task_id: 'task-1',
        status: 'in_progress',
        current_stage: 'theory_matching',
        current_framework_id: null,
        allowed_actions: ['start_matching'],
        resume_path: '/research/task-1/match',
        blocker: null,
        retry: null,
      },
    }
    const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input
      return new Response(JSON.stringify(init?.method === 'POST' ? confirmed : journey), {
        headers: { 'Content-Type': 'application/json' },
      })
    })
    vi.stubGlobal('fetch', fetch)

    await expect(getResearchStartJourney('conversation/1')).resolves.toEqual({
      conversationId: 'conversation/1',
      status: 'proposal_pending',
      taskId: null,
      proposal: {
        proposalId: 'proposal-1',
        phenomenon: '社区互助正在减少',
        researchIntent: '理解互助衰退的机制',
        context: '大城市老旧小区',
        version: 3,
        status: 'pending_confirmation',
      },
      resumePath: null,
    })
    await expect(confirmResearchStartProposal({
      proposalId: 'proposal-1',
      expectedVersion: 3,
      phenomenon: '社区互助正在减少',
      researchIntent: '理解互助衰退的机制',
      context: '大城市老旧小区',
      idempotencyKey: 'research-start:proposal-1',
    })).resolves.toEqual({
      conversationId: 'conversation/1',
      status: 'task_bound',
      taskId: 'task-1',
      proposal: {
        proposalId: 'proposal-1',
        phenomenon: '社区互助正在减少',
        researchIntent: '理解互助衰退的机制',
        context: '大城市老旧小区',
        version: 3,
        status: 'confirmed',
      },
      resumePath: '/research/task-1/match',
    })

    expect(buildUrl.mock.calls.map(([options]) => options)).toEqual([
      {
        url: '/api/agent/conversations/{conversation_id}/journey',
        path: { conversation_id: 'conversation/1' },
      },
      {
        url: '/api/agent/research-start-proposals/{proposal_id}/confirm',
        path: { proposal_id: 'proposal-1' },
      },
    ])
    expect(fetch).toHaveBeenNthCalledWith(1, 'https://api.qunxue.test/api/agent/conversations/conversation%2F1/journey', {
      credentials: 'include',
      signal: undefined,
    })
    expect(fetch).toHaveBeenNthCalledWith(2, 'https://api.qunxue.test/api/agent/research-start-proposals/proposal-1/confirm', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': 'research-start:proposal-1',
      },
      body: JSON.stringify({
        expected_version: 3,
        phenomenon: '社区互助正在减少',
        research_intent: '理解互助衰退的机制',
        context: '大城市老旧小区',
      }),
      signal: undefined,
    })
  })
})
