import { StrictMode } from 'react'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { NewResearchWorkspacePage } from './NewResearchWorkspacePage'

const cytoscapeMock = vi.hoisted(() => vi.fn(() => ({
  add: vi.fn(),
  destroy: vi.fn(),
  elements: vi.fn(() => ({ remove: vi.fn() })),
  fit: vi.fn(),
  layout: vi.fn(() => ({ run: vi.fn() })),
  on: vi.fn(),
})))

vi.mock('cytoscape', () => ({ default: cytoscapeMock }))

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  window.sessionStorage.clear()
  cytoscapeMock.mockClear()
})

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function conversationFixture(prompt = '为什么同一社区里的互助正在减少？', answer = '可以从信任、资源压力与互动机会三个层面分析。'): import('../../modules/research-agent').AgentConversation {
  return {
    conversation_id: 'conversation-research-new',
    title: prompt,
    created_at: '2026-08-19T00:00:00Z',
    updated_at: '2026-08-19T00:00:01Z',
    turn_count: 1,
    turns: [{
      turn_id: 'turn-research-new',
      user: {
        message_id: 'message-user',
        role: 'user' as const,
        content: prompt,
        citations: [],
        sequence: 1,
        created_at: '2026-08-19T00:00:00Z',
      },
      assistant: {
        message_id: 'message-assistant',
        role: 'assistant' as const,
        content: answer,
        citations: [],
        sequence: 2,
        created_at: '2026-08-19T00:00:01Z',
      },
      tool_traces: [],
      knowledge_release_id: null,
    }],
  }
}

function researchStartJourneyFixture(overrides: Record<string, unknown> = {}) {
  return {
    conversation_id: 'conversation-research-new',
    status: 'proposal_pending',
    task_id: null,
    proposal: {
      proposal_id: 'proposal-research-new',
      conversation_id: 'conversation-research-new',
      source_run_id: 'run-research-new',
      source_turn_id: 'turn-research-new',
      knowledge_release_id: 'release-formal-1',
      phenomenon: '同一社区里的互助正在减少',
      research_intent: '理解互助衰退背后的社会机制',
      context: '大城市老旧小区的日常生活',
      version: 1,
      status: 'pending_confirmation',
      requires_user_confirmation: true,
      confirmed_task_id: null,
      created_at: '2026-08-19T00:00:01Z',
      confirmed_at: null,
    },
    navigation: null,
    ...overrides,
  }
}

function researchStartNavigationFixture(overrides: Record<string, unknown> = {}) {
  return {
    task_id: 'task-created-once',
    entry_type: 'direct_input',
    status: 'in_progress',
    current_stage: 'theory_matching',
    stage_label: '理论匹配',
    next_action_label: '开始理论匹配',
    version: 1,
    allowed_actions: ['start_matching'],
    seed_theory_id: null,
    seed_theory_name: null,
    phenomenon_summary: {
      phenomenon_query_id: 'phenomenon-query-1',
      version: 1,
      phenomenon: '同一社区里的互助正在减少',
      research_intent: '理解互助衰退背后的社会机制',
    },
    adopted_theory_count: 0,
    current_phenomenon_candidate_id: 'phenomenon-candidate-1',
    current_material_intake_run_id: null,
    current_match_run_id: null,
    current_theory_plan_id: null,
    current_framework_id: null,
    resume_path: '/server-owned-next',
    blocker: null,
    retry: null,
    knowledge_release_id: 'release-formal-1',
    conversation_id: 'conversation-research-new',
    source_turn_id: 'turn-research-new',
    source_run_id: 'run-research-new',
    created_at: '2026-08-19T00:00:01Z',
    updated_at: '2026-08-19T00:00:02Z',
    ...overrides,
  }
}

function streamResponse(conversation: ReturnType<typeof conversationFixture>, runtimeMode: 'mock' | 'base' | 'sft' = 'mock') {
  const events = [
    ['turn_started', { conversation_id: conversation.conversation_id, run_id: 'run-1', replayed: false, runtime_mode: runtimeMode }],
    ['agent_status', { status: 'answering' }],
    ['assistant_delta', { delta: conversation.turns[0].assistant.content }],
    ['turn_completed', { conversation, knowledge_release_id: 'release-a' }],
  ]
    .map(([name, payload]) => `event: ${name}\ndata: ${JSON.stringify(payload)}`)
    .join('\n\n')
  return new Response(`${events}\n\n`, { headers: { 'Content-Type': 'text/event-stream' } })
}

function streamWithToolTrace(
  conversation: ReturnType<typeof conversationFixture>,
  detail = '找到 1 条知识库预览内容（未审核）',
) {
  const events = [
    ['turn_started', { conversation_id: conversation.conversation_id, run_id: 'run-tool', replayed: false, runtime_mode: 'mock' }],
    ['agent_status', { status: 'thinking' }],
    ['tool_started', { tool: 'search_knowledge', call_id: 'tool-search', input: { query: '社区互助' } }],
    ['tool_finished', { tool: 'search_knowledge', call_id: 'tool-search', output: { items: [{ title: '社会资本与互助', knowledge_id: 'D1:C001' }] }, detail }],
    ['assistant_delta', { delta: conversation.turns[0].assistant.content }],
    ['turn_completed', { conversation, knowledge_release_id: 'release-a' }],
  ]
    .map(([name, payload]) => `event: ${name}\ndata: ${JSON.stringify(payload)}`)
    .join('\n\n')
  return new Response(`${events}\n\n`, { headers: { 'Content-Type': 'text/event-stream' } })
}

function pausableStream() {
  const encoder = new TextEncoder()
  let close = () => undefined
  const response = new Response(new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode([
        'event: turn_started\ndata: {"conversation_id":"conversation-research-new","run_id":"run-stop","replayed":false,"runtime_mode":"mock"}',
        'event: agent_status\ndata: {"status":"thinking"}',
        'event: tool_started\ndata: {"tool":"search_knowledge","call_id":"stop-tool","input":{"query":"青年孤独"}}',
        '',
      ].join('\n\n')))
      close = () => controller.close()
    },
  }), { headers: { 'Content-Type': 'text/event-stream' } })
  return { close: () => close(), response }
}

function renderPage(path = '/research/new', strict = false, userId = 'user-a') {
  function LocationProbe() {
    const location = useLocation()
    return <output aria-label="当前测试路径">{location.pathname}{location.search}</output>
  }
  const page = <MemoryRouter initialEntries={[path]}><NewResearchWorkspacePage userId={userId} /><LocationProbe /></MemoryRouter>
  return render(strict ? <StrictMode>{page}</StrictMode> : page)
}

describe('NewResearchWorkspacePage', () => {
  it('restores the pending research proposal beside its persisted conversation', async () => {
    const conversation = conversationFixture()
    const journey = researchStartJourneyFixture()
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname.endsWith('/journey')) return json(journey)
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))

    renderPage(`/research/new?conversation_id=${conversation.conversation_id}`)

    const proposal = await screen.findByRole('region', { name: '研究建立确认' })
    expect(within(proposal).getByText(journey.proposal!.phenomenon)).toBeVisible()
    expect(within(proposal).getByText(journey.proposal!.research_intent!)).toBeVisible()
    expect(within(proposal).getByText(journey.proposal!.context!)).toBeVisible()
    expect(within(proposal).getByRole('button', { name: '确认并进入理论匹配' })).toBeEnabled()
    expect(within(proposal).getByRole('button', { name: '继续修改' })).toBeEnabled()
  })

  it('keeps one confirmation transaction across duplicate clicks and an explicit retry', async () => {
    const conversation = conversationFixture()
    const journey = researchStartJourneyFixture()
    const confirmedResearchStart = {
      conversation_id: journey.conversation_id,
      status: 'task_bound' as const,
      task_id: 'task-created-once',
      proposal: {
        ...journey.proposal!,
        status: 'confirmed' as const,
        requires_user_confirmation: false,
        confirmed_task_id: 'task-created-once',
        confirmed_at: '2026-08-19T00:00:02Z',
      },
      navigation: researchStartNavigationFixture(),
    }
    let releaseFirstConfirmation!: (response: Response) => void
    const firstConfirmation = new Promise<Response>((resolve) => { releaseFirstConfirmation = resolve })
    let confirmationAttempts = 0
    const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname.endsWith('/journey')) return json(journey)
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      if (url.pathname.endsWith('/confirm') && init?.method === 'POST') {
        confirmationAttempts += 1
        return confirmationAttempts === 1 ? firstConfirmation : json(confirmedResearchStart)
      }
      return json({}, 404)
    })
    vi.stubGlobal('fetch', fetch)
    renderPage(`/research/new?conversation_id=${conversation.conversation_id}`)

    const proposal = await screen.findByRole('region', { name: '研究建立确认' })
    const textbox = screen.getByRole('textbox', { name: '和 Agent 讨论你的研究' })
    fireEvent.change(textbox, { target: { value: '我还想补充一个社区情境' } })
    const confirm = within(proposal).getByRole('button', { name: '确认并进入理论匹配' })
    fireEvent.click(confirm)
    fireEvent.click(confirm)

    await waitFor(() => expect(confirmationAttempts).toBe(1))
    expect(confirm).toBeDisabled()
    releaseFirstConfirmation(json({}, 503))

    expect(await within(proposal).findByRole('alert')).toHaveTextContent('你的内容已保留')
    expect(textbox).toHaveValue('我还想补充一个社区情境')
    expect(within(proposal).getByText(journey.proposal!.phenomenon)).toBeVisible()
    expect(within(proposal).getByRole('button', { name: '返回继续修改' })).toBeEnabled()

    fireEvent.click(within(proposal).getByRole('button', { name: '重试建立研究' }))
    expect(await screen.findByText('/server-owned-next')).toBeVisible()

    const confirmationRequests = fetch.mock.calls.filter(([input, init]) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      return url.pathname.endsWith('/confirm') && init?.method === 'POST'
    })
    expect(confirmationRequests).toHaveLength(2)
    expect(confirmationRequests.map(([, init]) => new Headers(init?.headers).get('Idempotency-Key'))).toEqual([
      'research-start:proposal-research-new',
      'research-start:proposal-research-new',
    ])
    expect(confirmationRequests.map(([, init]) => JSON.parse(String(init?.body)))).toEqual([
      {
        expected_version: 1,
        phenomenon: journey.proposal!.phenomenon,
        research_intent: journey.proposal!.research_intent,
        context: journey.proposal!.context,
      },
      {
        expected_version: 1,
        phenomenon: journey.proposal!.phenomenon,
        research_intent: journey.proposal!.research_intent,
        context: journey.proposal!.context,
      },
    ])
  })

  it('resumes an already bound conversation only from the server navigation path', async () => {
    const conversation = conversationFixture()
    const journey = researchStartJourneyFixture({
      status: 'task_bound',
      task_id: 'task-bound',
      proposal: { ...researchStartJourneyFixture().proposal!, status: 'confirmed' },
      navigation: researchStartNavigationFixture({
        task_id: 'task-bound',
        resume_path: '/resume/from-server',
      }),
    })
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname.endsWith('/journey')) return json(journey)
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))

    renderPage(`/research/new?conversation_id=${conversation.conversation_id}&knowledge_release_id=must-not-drive-routing`)

    expect(await screen.findByText('/resume/from-server')).toBeVisible()
    expect(screen.queryByRole('region', { name: '研究建立确认' })).not.toBeInTheDocument()
  })

  it('loads the proposal persisted by a completed Agent turn', async () => {
    const conversation = conversationFixture()
    const journey = researchStartJourneyFixture()
    const journeyRequests: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/turns') return streamResponse(conversation, 'base')
      if (url.pathname.endsWith('/journey')) {
        journeyRequests.push(url.pathname)
        return json(journey)
      }
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    renderPage()

    const workspace = await screen.findByRole('region', { name: '新建研究工作区' })
    const textbox = within(workspace).getByRole('textbox', { name: '和 Agent 讨论你的研究' })
    fireEvent.change(textbox, { target: { value: conversation.title } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)

    const proposal = await within(workspace).findByRole('region', { name: '研究建立确认' })
    expect(within(proposal).getByText(journey.proposal!.phenomenon)).toBeVisible()
    expect(journeyRequests).toEqual([
      `/api/agent/conversations/${conversation.conversation_id}/journey`,
    ])
  })

  it('retries a disconnected Agent turn with the original question and idempotency key', async () => {
    const question = '为什么青年在熟人社区里也会感到孤独？'
    const conversation = conversationFixture(question, '可以从关系稳定性与情感劳动继续分析。')
    const turnRequests: RequestInit[] = []
    const randomUUID = vi.fn(() => turnRequests.length ? 'must-not-be-used' : 'turn-stable-key')
    vi.stubGlobal('crypto', { randomUUID })
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/turns') {
        turnRequests.push(init ?? {})
        return turnRequests.length === 1
          ? new Response(
              'event: turn_started\ndata: {"conversation_id":"conversation-research-new","run_id":"run-disconnected","replayed":false}\n\n'
                + 'event: assistant_delta\ndata: {"delta":"只有半段"}\n\n',
              { headers: { 'Content-Type': 'text/event-stream' } },
            )
          : streamResponse(conversation, 'base')
      }
      if (url.pathname.endsWith('/journey')) return json(researchStartJourneyFixture({ proposal: null }))
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    renderPage()

    const workspace = await screen.findByRole('region', { name: '新建研究工作区' })
    const textbox = within(workspace).getByRole('textbox', { name: '和 Agent 讨论你的研究' })
    fireEvent.change(textbox, { target: { value: question } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)

    expect(await within(workspace).findByRole('alert')).toHaveTextContent('回答完成前中断')
    expect(textbox).toHaveValue(question)
    fireEvent.click(within(workspace).getByRole('button', { name: '重试本轮' }))

    expect(await within(workspace).findByText(conversation.turns[0].assistant.content)).toBeVisible()
    expect(turnRequests).toHaveLength(2)
    expect(turnRequests.map((request) => new Headers(request.headers).get('Idempotency-Key'))).toEqual([
      'turn-stable-key',
      'turn-stable-key',
    ])
    expect(turnRequests.map((request) => JSON.parse(String(request.body)).message)).toEqual([question, question])
    expect(randomUUID).toHaveBeenCalledTimes(1)
  })

  it('restores an interrupted request after refresh and reuses its idempotency key', async () => {
    const question = '刷新后继续研究社区照护为什么变弱'
    const conversation = conversationFixture(question, '可以继续从照护资源与关系网络分析。')
    const turnRequests: RequestInit[] = []
    const randomUUID = vi.fn(() => 'turn-survives-refresh')
    vi.stubGlobal('crypto', { randomUUID })
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/turns') {
        turnRequests.push(init ?? {})
        return turnRequests.length === 1
          ? new Response(
              'event: turn_started\ndata: {"conversation_id":"conversation-research-new","run_id":"run-refresh","replayed":false}\n\n'
                + 'event: assistant_delta\ndata: {"delta":"未完成"}\n\n',
              { headers: { 'Content-Type': 'text/event-stream' } },
            )
          : streamResponse(conversation, 'base')
      }
      if (url.pathname.endsWith('/journey')) return json(researchStartJourneyFixture({ status: 'collecting', proposal: null }))
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))

    const firstPage = renderPage()
    const firstWorkspace = await screen.findByRole('region', { name: '新建研究工作区' })
    const firstTextbox = within(firstWorkspace).getByRole('textbox', { name: '和 Agent 讨论你的研究' })
    fireEvent.change(firstTextbox, { target: { value: question } })
    fireEvent.submit(firstTextbox.closest('form') as HTMLFormElement)
    expect(await within(firstWorkspace).findByRole('alert')).toHaveTextContent('回答完成前中断')
    firstPage.unmount()

    renderPage()
    const refreshedWorkspace = await screen.findByRole('region', { name: '新建研究工作区' })
    const refreshedTextbox = within(refreshedWorkspace).getByRole('textbox', { name: '和 Agent 讨论你的研究' })
    expect(refreshedTextbox).toHaveValue(question)
    fireEvent.submit(refreshedTextbox.closest('form') as HTMLFormElement)

    expect(await within(refreshedWorkspace).findByText(conversation.turns[0].assistant.content)).toBeVisible()
    expect(turnRequests.map((request) => new Headers(request.headers).get('Idempotency-Key'))).toEqual([
      'turn-survives-refresh',
      'turn-survives-refresh',
    ])
    expect(randomUUID).toHaveBeenCalledTimes(1)
  })

  it('keeps an unsent composer draft across refresh in this browser tab', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    const firstPage = renderPage()
    const draft = '我还没有发送的研究背景也不能在刷新时丢失'
    fireEvent.change(await screen.findByRole('textbox', { name: '和 Agent 讨论你的研究' }), {
      target: { value: draft },
    })
    firstPage.unmount()

    renderPage()
    expect(await screen.findByRole('textbox', { name: '和 Agent 讨论你的研究' })).toHaveValue(draft)
  })

  it('does not restore another account\'s research draft in the same tab', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ items: [] })))
    renderPage('/research/new', false, 'user-a')
    const privateDraft = '账号 A 尚未发送的田野笔记'
    fireEvent.change(await screen.findByRole('textbox', { name: '和 Agent 讨论你的研究' }), {
      target: { value: privateDraft },
    })

    cleanup()
    renderPage('/research/new', false, 'user-b')

    expect(await screen.findByRole('textbox', { name: '和 Agent 讨论你的研究' })).toHaveValue('')
  })

  it('keeps the conversation available when journey recovery needs an explicit retry', async () => {
    const conversation = conversationFixture()
    const journey = researchStartJourneyFixture()
    let journeyAttempts = 0
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname.endsWith('/journey')) {
        journeyAttempts += 1
        return journeyAttempts === 1 ? json({}, 503) : json(journey)
      }
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    renderPage(`/research/new?conversation_id=${conversation.conversation_id}`)

    expect(await screen.findByText(conversation.turns[0].assistant.content)).toBeVisible()
    const recovery = await screen.findByRole('alert', { name: '研究状态恢复失败' })
    expect(within(recovery).getByText('对话已保留')).toBeVisible()
    expect(within(recovery).getByRole('button', { name: '返回继续对话' })).toBeEnabled()

    fireEvent.click(within(recovery).getByRole('button', { name: '重试恢复研究状态' }))
    const proposal = await screen.findByRole('region', { name: '研究建立确认' })
    expect(within(proposal).getByText(journey.proposal!.phenomenon)).toBeVisible()
    expect(journeyAttempts).toBe(2)
  })

  it('never lets a late journey response leak into another history conversation', async () => {
    const conversationA = conversationFixture('研究 A：社区互助为什么减少？')
    const conversationB = {
      ...conversationFixture('研究 B：青年职业选择如何变化？'),
      conversation_id: 'conversation-b',
      title: '研究 B：青年职业选择如何变化？',
    }
    const journeyA = researchStartJourneyFixture({
      proposal: {
        ...researchStartJourneyFixture().proposal!,
        phenomenon: '这是 A 的待确认现象',
      },
    })
    const journeyB = researchStartJourneyFixture({
      conversation_id: conversationB.conversation_id,
      proposal: {
        ...researchStartJourneyFixture().proposal!,
        proposal_id: 'proposal-b',
        phenomenon: '这是 B 的待确认现象',
      },
    })
    let releaseJourneyA!: (response: Response) => void
    const delayedJourneyA = new Promise<Response>((resolve) => { releaseJourneyA = resolve })
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/conversations') {
        return json({ items: [{ conversation_id: conversationB.conversation_id, title: conversationB.title, updated_at: conversationB.updated_at, turn_count: 1 }] })
      }
      if (url.pathname === `/api/agent/conversations/${conversationA.conversation_id}`) return json(conversationA)
      if (url.pathname === `/api/agent/conversations/${conversationB.conversation_id}`) return json(conversationB)
      if (url.pathname === `/api/agent/conversations/${conversationA.conversation_id}/journey`) return delayedJourneyA
      if (url.pathname === `/api/agent/conversations/${conversationB.conversation_id}/journey`) return json(journeyB)
      return json({}, 404)
    }))
    renderPage(`/research/new?conversation_id=${conversationA.conversation_id}`)

    fireEvent.click((await screen.findAllByRole('button', { name: '打开研究记录' }))[0])
    fireEvent.click(await screen.findByRole('button', { name: new RegExp(conversationB.title) }))
    await waitFor(() => expect(screen.getByText(journeyB.proposal!.phenomenon)).toBeVisible())

    releaseJourneyA(json(journeyA))
    await waitFor(() => expect(screen.queryByText(journeyA.proposal!.phenomenon)).not.toBeInTheDocument())
    expect(screen.getByText(journeyB.proposal!.phenomenon)).toBeVisible()
  })

  it('labels the configured mock runtime as a preview and never as a real model run', async () => {
    const conversation = conversationFixture()
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/turns') return streamResponse(conversation, 'mock')
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))

    const workspace = renderPage().container

    expect(await screen.findByText('运行模式待确认')).toBeVisible()
    const region = within(workspace).getByRole('region', { name: '新建研究工作区' })
    const textbox = within(region).getByRole('textbox', { name: '和 Agent 讨论你的研究' })
    fireEvent.change(textbox, { target: { value: conversation.title } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)

    expect(await within(region).findByText('预览 Agent')).toBeVisible()
    expect(within(region).queryByText('真实 Agent 运行')).not.toBeInTheDocument()
  })

  it('keeps the composer within the server message contract', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    const workspace = renderPage().container
    const region = await within(workspace).findByRole('region', { name: '新建研究工作区' })
    expect(within(region).getByRole('textbox', { name: '和 Agent 讨论你的研究' })).toHaveAttribute('maxlength', '12000')
  })

  it('shows the external base-model runtime reported by the Agent stream', async () => {
    const conversation = conversationFixture('请解释社区互助的变化。')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/turns') return streamResponse(conversation, 'base')
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    renderPage()

    const workspace = await screen.findByRole('region', { name: '新建研究工作区' })
    const textbox = within(workspace).getByRole('textbox', { name: '和 Agent 讨论你的研究' })
    fireEvent.change(textbox, { target: { value: conversation.title } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)

    expect(await within(workspace).findByText('基础模型运行')).toBeVisible()
    expect(within(workspace).queryByText('预览 Agent')).not.toBeInTheDocument()
  })

  it('marks an uncited answer as a working hypothesis instead of implying sourced evidence', async () => {
    const conversation = conversationFixture(
      '请先不用检索，解释社区互助为什么会减少。',
      '可以先从信任、资源压力与互动机会三个层面提出解释。',
    )
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/turns') return streamResponse(conversation)
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    renderPage()

    const workspace = await screen.findByRole('region', { name: '新建研究工作区' })
    const textbox = within(workspace).getByRole('textbox', { name: '和 Agent 讨论你的研究' })
    fireEvent.change(textbox, { target: { value: conversation.title } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)

    expect(await within(workspace).findByText(/未调用知识库/)).toBeVisible()
    expect(within(workspace).getByText(/工作假设/)).toBeVisible()
  })

  it('renders a real GFM table in the Agent answer', async () => {
    const conversation = conversationFixture(
      '平台算法如何改变年轻人的职业选择？',
      '| 机制 | 观察线索 |\n| --- | --- |\n| 推荐排序 | 职业可见性变化 |',
    )
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/turns') return streamResponse(conversation)
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    renderPage()

    const workspace = await screen.findByRole('region', { name: '新建研究工作区' })
    const textbox = within(workspace).getByRole('textbox', { name: '和 Agent 讨论你的研究' })
    fireEvent.change(textbox, { target: { value: conversation.title } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)

    const table = await within(workspace).findByRole('table')
    expect(within(table).getByRole('columnheader', { name: '机制' })).toBeVisible()
    expect(within(table).getByRole('cell', { name: '职业可见性变化' })).toBeVisible()
  })

  it('regenerates by starting a real follow-up Agent turn and exposes no dead feedback controls', async () => {
    const first = conversationFixture('为什么同一社区里的互助正在减少？', '第一版回答。')
    const second = conversationFixture('为什么同一社区里的互助正在减少？', '重新生成后的回答。')
    let turnCalls = 0
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/turns') {
        turnCalls += 1
        return streamResponse(turnCalls === 1 ? first : second)
      }
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    })
    vi.stubGlobal('fetch', fetch)

    const workspace = renderPage().container
    const region = await within(workspace).findByRole('region', { name: '新建研究工作区' })
    const textbox = within(region).getByRole('textbox', { name: '和 Agent 讨论你的研究' })
    fireEvent.change(textbox, { target: { value: first.title } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)

    expect(await within(region).findByText('第一版回答。', { exact: true })).toBeVisible()
    expect(within(region).queryByRole('button', { name: '有帮助' })).not.toBeInTheDocument()
    expect(within(region).queryByRole('button', { name: '没帮助' })).not.toBeInTheDocument()

    fireEvent.click(within(region).getByRole('button', { name: '重新生成' }))

    await waitFor(() => expect(turnCalls).toBe(2))
    expect(await within(region).findByText('重新生成后的回答。', { exact: true })).toBeVisible()
  })

  it('does not claim a copy succeeded when the browser clipboard rejects it', async () => {
    const conversation = conversationFixture('复制测试问题', '需要复制的回答。')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/turns') return streamResponse(conversation)
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    const originalClipboard = navigator.clipboard
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) } })
    try {
      const workspace = renderPage().container
      const region = await within(workspace).findByRole('region', { name: '新建研究工作区' })
      const textbox = within(region).getByRole('textbox', { name: '和 Agent 讨论你的研究' })
      fireEvent.change(textbox, { target: { value: conversation.title } })
      fireEvent.submit(textbox.closest('form') as HTMLFormElement)
      fireEvent.click(await within(region).findByRole('button', { name: '复制回答' }))
      expect(await within(region).findByRole('button', { name: '复制回答' })).toHaveTextContent('复制失败')
    } finally {
      Object.defineProperty(navigator, 'clipboard', { configurable: true, value: originalClipboard })
    }
  })

  it('shows one interruption note and leaves the composer available after stopping', async () => {
    const stream = pausableStream()
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/turns') return stream.response
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    renderPage()

    const workspace = await screen.findByRole('region', { name: '新建研究工作区' })
    const textbox = within(workspace).getByRole('textbox', { name: '和 Agent 讨论你的研究' })
    fireEvent.change(textbox, { target: { value: '怎么理解青年孤独？' } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)
    fireEvent.click(await within(workspace).findByRole('button', { name: '停止生成' }))
    stream.close()

    expect(await within(workspace).findByText('本轮已停止，未保存未完成的回答。')).toBeVisible()
    expect(within(workspace).getAllByText(/未保存未完成/)).toHaveLength(1)
    expect(within(workspace).getByRole('textbox', { name: '和 Agent 讨论你的研究' })).toHaveValue('怎么理解青年孤独？')
    expect(within(workspace).getByRole('button', { name: '重试本轮' })).toBeEnabled()
  })

  it('turns a truncated Agent stream into a recoverable error instead of a stuck composer', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/turns') {
        return new Response(
          'event: turn_started\ndata: {"conversation_id":"conversation-research-new","run_id":"run-truncated","replayed":false,"runtime_mode":"mock"}\n\n'
            + 'event: assistant_delta\ndata: {"delta":"半段回答"}\n\n',
          { headers: { 'Content-Type': 'text/event-stream' } },
        )
      }
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    const workspace = renderPage().container
    const region = await within(workspace).findByRole('region', { name: '新建研究工作区' })
    const textbox = within(region).getByRole('textbox', { name: '和 Agent 讨论你的研究' })
    fireEvent.change(textbox, { target: { value: '这个流会被截断吗？' } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)

    expect(await within(region).findByRole('alert')).toHaveTextContent('连接在回答完成前中断')
    expect(within(region).getByRole('textbox', { name: '和 Agent 讨论你的研究' })).toBeEnabled()
  })

  it('opens citation context in Basis before offering the knowledge entry link', async () => {
    const conversation = conversationFixture()
    conversation.turns[0].assistant.citations = [{
      citation_id: 'citation-basis',
      label: '互惠规范',
      kind: 'entry',
      excerpt: '互惠规范描述了持续互动中信任与回报的关系。',
      knowledge_id: 'D1:C001',
    }]
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/conversations') return json({ items: [{ conversation_id: conversation.conversation_id, title: conversation.title, updated_at: conversation.updated_at, turn_count: 1 }] })
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      return json({}, 404)
    }))
    renderPage(`/research/new?conversation_id=${conversation.conversation_id}&knowledge_release_id=release-a`)

    const workspace = await screen.findByRole('region', { name: '新建研究工作区' })
    fireEvent.click(await within(workspace).findByRole('button', { name: /查看证据：互惠规范/ }))
    const sources = await screen.findByRole('tabpanel', { name: 'Sources' })
    fireEvent.click(within(sources).getByRole('button', { name: /互惠规范/ }))

    const basis = await screen.findByRole('tabpanel', { name: 'Basis' })
    expect(basis).toHaveTextContent('互惠规范描述了持续互动中信任与回报的关系。')
    expect(within(basis).getByRole('link', { name: /打开知识条目/ })).toHaveAttribute(
      'href',
      '/knowledge/D1%3AC001?knowledge_release_id=release-a&return_to=%2Fresearch%2Fnew%3Fconversation_id%3Dconversation-research-new%26knowledge_release_id%3Drelease-a',
    )
  })

  it('labels preview citations as unreviewed evidence in Sources and Basis', async () => {
    const conversation = conversationFixture('请检索预览知识。')
    conversation.turns[0].assistant.citations = [{
      citation_id: 'citation-preview',
      label: '社区互助工作笔记',
      kind: 'preview',
      excerpt: '这是一条尚未审核的工作材料。',
      knowledge_id: 'D1:C099',
    }]
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      return json({}, 404)
    }))
    renderPage(`/research/new?conversation_id=${conversation.conversation_id}&knowledge_release_id=release-preview`)

    const workspace = await screen.findByRole('region', { name: '新建研究工作区' })
    fireEvent.click(await within(workspace).findByRole('button', { name: /查看证据：社区互助工作笔记/ }))
    const sources = await screen.findByRole('tabpanel', { name: 'Sources' })
    expect(sources).toHaveTextContent('未审核预览')
    fireEvent.click(within(sources).getByRole('button', { name: /社区互助工作笔记/ }))

    const basis = await screen.findByRole('tabpanel', { name: 'Basis' })
    expect(basis).toHaveTextContent('未审核预览')
    expect(basis).toHaveTextContent('这是一条尚未审核的工作材料。')
  })

  it('withholds a knowledge entry link when the conversation release is unknown', async () => {
    const conversation = conversationFixture()
    conversation.turns[0].assistant.citations = [{
      citation_id: 'citation-without-release',
      label: '互惠规范',
      kind: 'entry',
      excerpt: '互惠规范描述了持续互动中信任与回报的关系。',
      knowledge_id: 'D1:C001',
    }]
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      return json({}, 404)
    }))
    renderPage(`/research/new?conversation_id=${conversation.conversation_id}`)

    const workspace = await screen.findByRole('region', { name: '新建研究工作区' })
    fireEvent.click(await within(workspace).findByRole('button', { name: /查看证据：互惠规范/ }))
    const sources = await screen.findByRole('tabpanel', { name: 'Sources' })
    fireEvent.click(within(sources).getByRole('button', { name: /互惠规范/ }))

    const basis = await screen.findByRole('tabpanel', { name: 'Basis' })
    expect(within(basis).queryByRole('link', { name: /打开知识条目/ })).not.toBeInTheDocument()
    expect(basis).toHaveTextContent('当前回合的知识版本尚未确认，暂不提供跳转。')
  })

  it('restores a persisted turn release after a research page refresh', async () => {
    const conversation = conversationFixture('请检索知识库解释社区互助。')
    conversation.turns[0].assistant.citations = [{
      citation_id: 'citation-persisted-release',
      label: '社会资本与互助',
      kind: 'entry',
      excerpt: '社会资本与互助的关系。',
      knowledge_id: 'D1:C213',
    }]
    conversation.turns[0].knowledge_release_id = 'release-a'
    let firstRender = true
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/turns' && firstRender) {
        firstRender = false
        return streamResponse(conversation)
      }
      if (url.pathname === '/api/agent/conversations') {
        return json({ items: [{ conversation_id: conversation.conversation_id, title: conversation.title, updated_at: conversation.updated_at, turn_count: 1 }] })
      }
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      return json({}, 404)
    }))

    const firstPage = renderPage()
    const firstWorkspace = await screen.findByRole('region', { name: '新建研究工作区' })
    const firstTextbox = within(firstWorkspace).getByRole('textbox', { name: '和 Agent 讨论你的研究' })
    fireEvent.change(firstTextbox, { target: { value: conversation.title } })
    fireEvent.submit(firstTextbox.closest('form') as HTMLFormElement)
    await within(firstWorkspace).findByText(conversation.turns[0].assistant.content, { exact: true })
    firstPage.unmount()
    window.sessionStorage.clear()

    renderPage(`/research/new?conversation_id=${conversation.conversation_id}`)
    const refreshedWorkspace = await screen.findByRole('region', { name: '新建研究工作区' })
    fireEvent.click(await within(refreshedWorkspace).findByRole('button', { name: /查看证据：社会资本与互助/ }))
    const sources = await screen.findByRole('tabpanel', { name: 'Sources' })
    fireEvent.click(within(sources).getByRole('button', { name: /社会资本与互助/ }))
    const basis = await screen.findByRole('tabpanel', { name: 'Basis' })

    expect(within(basis).getByRole('link', { name: /打开知识条目/ })).toHaveAttribute(
      'href',
      '/knowledge/D1%3AC213?knowledge_release_id=release-a&return_to=%2Fresearch%2Fnew%3Fconversation_id%3Dconversation-research-new%26knowledge_release_id%3Drelease-a',
    )
  })

  it('cancels an active stream before restoring another research record', async () => {
    const stream = pausableStream()
    const restored = conversationFixture('已保存的社区互助研究', '这是一段已保存的研究回答。')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/turns') return stream.response
      if (url.pathname === '/api/agent/conversations') return json({ items: [{ conversation_id: restored.conversation_id, title: restored.title, updated_at: restored.updated_at, turn_count: 1 }] })
      if (url.pathname === `/api/agent/conversations/${restored.conversation_id}`) return json(restored)
      return json({}, 404)
    }))
    renderPage()

    const workspace = await screen.findByRole('region', { name: '新建研究工作区' })
    const textbox = within(workspace).getByRole('textbox', { name: '和 Agent 讨论你的研究' })
    fireEvent.change(textbox, { target: { value: '正在运行的旧研究问题' } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)
    expect(await within(workspace).findByRole('button', { name: '停止生成' })).toBeVisible()

    fireEvent.click(within(workspace).getAllByRole('button', { name: '打开研究记录' })[0])
    fireEvent.click(await screen.findByRole('button', { name: /已保存的社区互助研究/ }))
    stream.close()

    expect(await within(workspace).findByText(restored.turns[0].assistant.content, { exact: true })).toBeVisible()
    expect(within(workspace).queryByText('正在运行的旧研究问题')).not.toBeInTheDocument()
    expect(within(workspace).getByRole('textbox', { name: '和 Agent 讨论你的研究' })).toBeEnabled()
  })

  it('treats research history as a dismissible dialog with an Escape route', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    const workspace = renderPage().container
    const region = await within(workspace).findByRole('region', { name: '新建研究工作区' })
    fireEvent.click(within(region).getAllByRole('button', { name: '打开研究记录' })[0])

    const dialog = await within(region).findByRole('dialog', { name: '研究记录' })
    fireEvent.keyDown(dialog, { key: 'Escape' })
    expect(within(region).queryByRole('dialog', { name: '研究记录' })).not.toBeInTheDocument()
  })

  it('turns a selected question node into an explicit follow-up prompt', async () => {
    const conversation = conversationFixture('为什么社区互助正在减少？', '可以先从信任与资源压力分析。')
    conversation.research_map = {
      schema_version: 1,
      nodes: [{
        id: 'question-community-help',
        kind: 'question',
        title: '为什么社区互助正在减少？',
        summary: '追问关系结构与资源压力如何共同变化。',
        status: 'developing',
        citation_ids: [],
      }],
      relations: [],
    }
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      return json({}, 404)
    }))
    const workspace = renderPage(`/research/new?conversation_id=${conversation.conversation_id}`)
    const region = await within(workspace.container).findByRole('region', { name: '新建研究工作区' })
    const map = within(region).getByRole('region', { name: '研究论证地图' })
    fireEvent.click(within(map).getByRole('button', { name: '打开节点目录' }))
    fireEvent.click(within(map).getByRole('button', { name: /为什么社区互助正在减少/ }))
    fireEvent.click(await within(map).findByRole('button', { name: /让 Agent 继续推进/ }))

    expect(within(region).getByRole('textbox', { name: '和 Agent 讨论你的研究' })).toHaveValue(
      '请继续拆解这个研究问题：为什么社区互助正在减少？',
    )
  })

  it('keeps local tool trace visible after the server completes without echoing traces', async () => {
    const conversation = conversationFixture('请检索知识库解释社区互助。')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/turns') return streamWithToolTrace(conversation)
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    renderPage()

    const workspace = await screen.findByRole('region', { name: '新建研究工作区' })
    const textbox = within(workspace).getByRole('textbox', { name: '和 Agent 讨论你的研究' })
    fireEvent.change(textbox, { target: { value: conversation.title } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)

    expect(await within(workspace).findByText('Agent 已完成工具调用')).toBeVisible()
    fireEvent.click(within(workspace).getAllByRole('button', { name: '查看活动' })[0])
    const activityPanel = await screen.findByRole('tabpanel', { name: 'Activity' })
    expect(activityPanel).toHaveTextContent('检索知识库')
    expect(activityPanel).toHaveTextContent('找到 1 条知识库预览内容（未审核）')
  })

  it('summarizes oversized tool output while keeping the complete trace expandable', async () => {
    const conversation = conversationFixture('请检索知识库解释社区互助。')
    const completeDetail = `完整工具返回：${'社会资本与社区互助的检索证据。'.repeat(80)}`
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/turns') return streamWithToolTrace(conversation, completeDetail)
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    renderPage()

    const workspace = await screen.findByRole('region', { name: '新建研究工作区' })
    const textbox = within(workspace).getByRole('textbox', { name: '和 Agent 讨论你的研究' })
    fireEvent.change(textbox, { target: { value: conversation.title } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)

    const detailDisclosure = await within(workspace).findByRole('button', { name: '查看完整工具返回' })
    expect(within(workspace).queryByText(completeDetail)).not.toBeVisible()
    fireEvent.click(detailDisclosure)
    expect(within(workspace).getByText(completeDetail)).toBeVisible()
  })

  it('does not turn an aborted history request into a visible product error', async () => {
    let listCalls = 0
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
      if (url.pathname === '/api/agent/conversations') {
        listCalls += 1
        if (listCalls === 1) throw new DOMException('The operation was aborted.', 'AbortError')
        return json({ items: [] })
      }
      return json({}, 404)
    }))
    renderPage('/research/new', true)

    await waitFor(() => expect(listCalls).toBeGreaterThanOrEqual(2))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
