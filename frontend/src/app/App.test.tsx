import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AppRoutes } from './App'
import { AccountProvider } from '../modules/account'

const cytoscapeMock = vi.hoisted(() => vi.fn(() => ({
  destroy: vi.fn(),
  elements: vi.fn(() => ({})),
  fit: vi.fn(),
  on: vi.fn(),
})))

vi.mock('cytoscape', () => ({ default: cytoscapeMock }))

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function renderRoute(
  path: string,
  sessionState: { status: 'authenticated' | 'anonymous' | 'expired' | 'loading' } = {
    status: 'anonymous',
  },
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={queryClient}>
        <AppRoutes sessionState={sessionState} />
        <RouteLocation />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

function RouteLocation() {
  const location = useLocation()
  return <div data-testid="route-location">{`${location.pathname}${location.search}${location.hash}`}</div>
}

function knowledgeSummary() {
  return {
    category: '概念',
    category_id: 'C001',
    content_version: 1,
    dimension: '本体论',
    dimension_id: 'D1',
    directory_path: [
      { node_id: 'D1', node_type: 'dimension', title: '本体论' },
      { node_id: 'C001', node_type: 'category', title: '概念' },
    ],
    eligibility: {
      browse_eligible: true,
      match_eligible: false,
      rag_eligible: false,
      review_record_ids: [],
      training_candidate_eligible: false,
    },
    knowledge_id: 'D1:C001',
    review_status: 'pending',
    title: '概念',
  }
}

function knowledgePage() {
  return {
    entries: [knowledgeSummary()],
    knowledge_release_id: 'release-a',
    next_cursor: null,
    stable_order: ['D1:C001'],
    total_count: 1,
  }
}

function knowledgeDirectory() {
  return {
    knowledge_release_id: 'release-a',
    nodes: [
      { entry_count: 1, node_id: 'D1', node_type: 'dimension', parent_node_id: null, title: '本体论' },
      { entry_count: 1, node_id: 'C001', node_type: 'category', parent_node_id: 'D1', title: '概念' },
      ...['D2', 'D3', 'D4', 'D5', 'D6', 'D7'].map((nodeId, index) => ({
        entry_count: 0,
        node_id: nodeId,
        node_type: 'dimension',
        parent_node_id: null,
        title: ['实践论', '方法论', '价值论', '认识论', '学派传统', '学科史'][index],
      })),
    ],
  }
}

function knowledgeResponse(input: RequestInfo | URL) {
  const request = requestUrl(input)
  return request.pathname === '/api/knowledge/directory'
    ? json(knowledgeDirectory())
    : json(knowledgePage())
}

function knowledgeDetail() {
  return {
    ...knowledgeSummary(),
    aliases: [],
    content: '一段真实条目正文。',
    knowledge_release_id: 'release-a',
    relations: [],
    sources: [],
    theory_profile: null,
  }
}

function knowledgeDetailWithRelation() {
  return {
    ...knowledgeDetail(),
    relations: [
      {
        content_version: 1,
        description: '真实已审核关系。',
        direction: 'directed',
        evidence_grade: 'A',
        evidence_source_ids: [],
        relation_id: 'relation-1',
        relation_type: '概念关联',
        review_status: 'reviewed',
        source_knowledge_id: 'D1:C001',
        target_knowledge_id: 'D1:C002',
      },
    ],
  }
}

function knowledgeDetailWithTheoryProfile() {
  return {
    ...knowledgeDetail(),
    theory_profile: {
      analysis_levels: [],
      applicable_phenomena: [],
      competing_or_complementary_theory_ids: [],
      content_version: 1,
      core_propositions: [],
      exclusion_signals: [],
      match_eligible: true,
      observable_evidence: [],
      prerequisites: [],
      related_knowledge_ids: ['D1:C001'],
      review_status: 'reviewed',
      source_ids: [],
      theory_id: 'theory-social-capital',
      title: '社会资本理论',
    },
  }
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function requestUrl(input: RequestInfo | URL) {
  if (typeof input === 'string') return new URL(input, 'http://localhost')
  if (input instanceof URL) return input
  return new URL(input.url)
}

function agentConversationFixture(prompt = '为什么同一社区里的互助正在减少？') {
  return {
    conversation_id: 'agent-conversation-1',
    title: prompt,
    created_at: '2026-08-18T00:00:00Z',
    updated_at: '2026-08-18T00:00:01Z',
    turn_count: 1,
    turns: [
      {
        turn_id: 'agent-turn-1',
        user: {
          message_id: 'agent-user-message-1',
          role: 'user',
          content: prompt,
          citations: [],
          sequence: 1,
          created_at: '2026-08-18T00:00:00Z',
        },
        assistant: {
          message_id: 'agent-assistant-message-1',
          role: 'assistant',
          content: '知识库回答：互助关系会受到资源压力、信任和互动机会的共同影响。',
          citations: [],
          sequence: 2,
          created_at: '2026-08-18T00:00:01Z',
        },
        tool_traces: [],
      },
    ],
  }
}

function agentStreamResponse(conversation: ReturnType<typeof agentConversationFixture>) {
  const events = [
    ['turn_started', { conversation_id: conversation.conversation_id, run_id: 'agent-run-1', replayed: false }],
    ['agent_status', { status: 'thinking' }],
    ['tool_started', { tool: 'search_knowledge', call_id: 'tool-call-1', input: { query: '社区互助减少' } }],
    ['tool_finished', { tool: 'search_knowledge', call_id: 'tool-call-1', output: { summary: '找到 1 条可引用证据' } }],
    ['agent_status', { status: 'answering' }],
    ['assistant_delta', { delta: conversation.turns[0].assistant.content }],
    ['turn_completed', { conversation, knowledge_release_id: 'release-a' }],
  ]
    .map(([name, payload]) => `event: ${name}\ndata: ${JSON.stringify(payload)}`)
    .join('\n\n')
  return new Response(`${events}\n\n`, {
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

function pausableDirectAgentStream(conversation: ReturnType<typeof agentConversationFixture>) {
  const encoder = new TextEncoder()
  let finish = () => undefined
  let close = () => undefined
  const response = new Response(new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode([
        `event: turn_started\ndata: ${JSON.stringify({
          conversation_id: conversation.conversation_id,
          run_id: 'agent-run-direct',
          replayed: false,
        })}`,
        'event: agent_status\ndata: {"status":"thinking"}',
        '',
      ].join('\n\n')))
      finish = () => {
        controller.enqueue(encoder.encode([
          `event: assistant_delta\ndata: ${JSON.stringify({ delta: conversation.turns[0].assistant.content })}`,
          `event: turn_completed\ndata: ${JSON.stringify({ conversation, knowledge_release_id: 'release-a' })}`,
          '',
        ].join('\n\n')))
        controller.close()
      }
      close = () => controller.close()
    },
  }), { headers: { 'Content-Type': 'text/event-stream' } })
  return { close: () => close(), finish: () => finish(), response }
}

function failedToolStreamResponse(conversation: ReturnType<typeof agentConversationFixture>) {
  const events = [
    ['turn_started', { conversation_id: conversation.conversation_id, run_id: 'agent-run-2', replayed: false }],
    ['agent_status', { status: 'thinking' }],
    ['tool_started', { tool: 'search_knowledge', call_id: 'tool-call-2', input: { query: '青年孤独' } }],
    ['tool_failed', { tool: 'search_knowledge', call_id: 'tool-call-2', message: '知识库暂时不可用' }],
    ['assistant_delta', { delta: conversation.turns[0].assistant.content }],
    ['turn_completed', { conversation, knowledge_release_id: 'release-a' }],
  ]
    .map(([name, payload]) => `event: ${name}\ndata: ${JSON.stringify(payload)}`)
    .join('\n\n')
  return new Response(`${events}\n\n`, {
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

function repeatedToolStreamResponse(conversation: ReturnType<typeof agentConversationFixture>) {
  const events = [
    ['turn_started', { conversation_id: conversation.conversation_id, run_id: 'agent-run-3', replayed: false }],
    ['agent_status', { status: 'thinking' }],
    ['tool_started', { tool: 'search_knowledge', call_id: 'tool-call-a', input: { query: '青年' } }],
    ['tool_started', { tool: 'search_knowledge', call_id: 'tool-call-a', input: { query: '青年' } }],
    ['tool_finished', { tool: 'search_knowledge', call_id: 'tool-call-a', detail: '找到 2 条证据' }],
    ['tool_started', { tool: 'search_knowledge', call_id: 'tool-call-b', input: { query: '孤独' } }],
    ['tool_finished', { tool: 'search_knowledge', call_id: 'tool-call-b', detail: '找到 1 条证据' }],
    ['assistant_delta', { delta: conversation.turns[0].assistant.content }],
    ['turn_completed', { conversation, knowledge_release_id: 'release-a' }],
  ]
    .map(([name, payload]) => `event: ${name}\ndata: ${JSON.stringify(payload)}`)
    .join('\n\n')
  return new Response(`${events}\n\n`, {
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

function pausableToolAgentStream(conversation: ReturnType<typeof agentConversationFixture>) {
  const encoder = new TextEncoder()
  let close = () => undefined
  const response = new Response(new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode([
        `event: turn_started\ndata: ${JSON.stringify({
          conversation_id: conversation.conversation_id,
          run_id: 'agent-run-stop',
          replayed: false,
        })}`,
        'event: agent_status\ndata: {"status":"thinking"}',
        'event: tool_started\ndata: {"tool":"search_knowledge","call_id":"tool-call-stop","input":{"query":"青年孤独"}}',
        '',
      ].join('\n\n')))
      close = () => controller.close()
    },
  }), { headers: { 'Content-Type': 'text/event-stream' } })
  return { close: () => close(), response }
}

describe('App routes', () => {
  it('uses one task-oriented navigation model across desktop and mobile', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ items: [], next_cursor: null })))
    renderRoute('/app', { status: 'authenticated' })

    const desktopNavigation = await screen.findByRole('navigation', { name: '桌面主导航' })
    const desktopRail = screen.getByRole('complementary', { name: '群学致知功能栏' })
    const mobileNavigation = screen.getByRole('navigation', { name: '移动主导航' })

    expect(desktopNavigation).toBeInTheDocument()
    expect(mobileNavigation).toBeInTheDocument()
    expect(within(desktopRail).getByRole('link', { name: '群学致知工作台' })).toHaveAttribute('href', '/app')
    expect(
      within(desktopNavigation).getAllByRole('link').every((link) => Boolean(link.querySelector('svg'))),
    ).toBe(true)
    expect(within(desktopNavigation).getAllByRole('link').map((link) => link.textContent)).toEqual([
      '工作台',
      '研究 Agent',
      '新建研究',
      '我的研究',
      '知识库',
      '知识图谱',
    ])
    expect(within(mobileNavigation).getAllByRole('link')).toHaveLength(6)
    expect(within(desktopNavigation).getByRole('link', { name: '研究 Agent' })).toHaveAttribute(
      'href',
      '/agent',
    )
    expect(within(desktopNavigation).queryByRole('link', { name: '首页' })).not.toBeInTheDocument()
    expect(within(mobileNavigation).getByRole('link', { name: '图谱' })).toHaveAttribute(
      'href',
      '/knowledge/graph',
    )
  })

  it('renders the work home as a focused research library instead of a dashboard card grid', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ items: [], next_cursor: null })))

    renderRoute('/app', { status: 'authenticated' })

    expect(await screen.findByRole('heading', { level: 1, name: '工作台' })).toBeVisible()
    expect(screen.getByRole('navigation', { name: '研究视图' })).toBeVisible()
    expect(screen.getByRole('region', { name: '最近研究' })).toBeVisible()
    expect(await screen.findByRole('heading', { level: 2, name: '还没有研究任务' })).toBeVisible()
    expect(
      within(screen.getByRole('main')).getByRole('link', { name: '新建研究' }),
    ).toHaveAttribute('href', '/research/new')
    expect(screen.queryByRole('region', { name: '研究资料' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '从现象到框架' })).not.toBeInTheDocument()
  })

  it.each([
    ['/research/task-1/match', '理论判断文档'],
    ['/research/task-1/framework', '研究框架文档'],
  ])('shows %s as an honest research-stage workbench', async (path, title) => {
    renderRoute(path, { status: 'authenticated' })

    expect(await screen.findByRole('heading', { name: title })).toBeVisible()
    expect(screen.getByRole('navigation', { name: '研究章节' })).toBeVisible()
    expect(screen.getByRole('heading', { name: title }).closest('main')).toHaveClass(
      'research-document-workbench',
    )
  })

  it('renders my research as a compact task library inside the shared app shell', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ items: [], next_cursor: null })))
    renderRoute('/my', { status: 'authenticated' })

    expect(await screen.findByRole('heading', { level: 1, name: '我的研究' })).toBeVisible()
    expect(screen.getByRole('navigation', { name: '研究库视图' })).toBeVisible()
    expect(screen.getByRole('region', { name: '研究任务列表' })).toBeVisible()
    expect(within(screen.getByRole('main')).getByRole('link', { name: '新建研究' })).toHaveAttribute(
      'href',
      '/research/new',
    )
    expect(screen.queryByText('ACCOUNT / MY')).not.toBeInTheDocument()
  })

  it('renders the graph workspace from its independent route', async () => {
    renderRoute('/knowledge/graph?knowledge_release_id=release-a')

    expect(await screen.findByRole('heading', { name: '知识图谱' })).toBeVisible()
    expect(screen.getByRole('region', { name: '全屏知识图谱工作台' })).toBeVisible()
  })

  it('opens the knowledge library with the product rail collapsed', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => knowledgeResponse(input)))

    renderRoute('/knowledge?knowledge_release_id=release-a')

    expect(await screen.findByRole('heading', { name: '本体论' })).toBeVisible()
    const expandRail = screen.getByRole('button', { name: '展开侧栏' })
    expect(expandRail).toBeVisible()
    fireEvent.click(expandRail)
    expect(screen.getByRole('button', { name: '收起侧栏' })).toBeVisible()
  })

  it('keeps a knowledge entry in its own scrollable workspace', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json(knowledgeDetail())))

    renderRoute('/knowledge/D1%3AC001?knowledge_release_id=release-a')

    expect(await screen.findByRole('heading', { name: '概念' })).toBeVisible()
    expect(screen.getByRole('button', { name: '展开侧栏' })).toBeVisible()
    expect(screen.getByRole('main')).toHaveClass('page-shell--workspace')
    expect(screen.getByRole('region', { name: '知识条目正文' })).toBeVisible()
  })

  it.each([
    ['/app', '工作台'],
    ['/agent', '你想研究什么？'],
    ['/research/new', '从一个社会学问题开始'],
    ['/research/task-1/phenomenon', '确认现象'],
    ['/research/task-1/match', '理论判断文档'],
    ['/research/task-1/framework', '研究框架文档'],
    ['/my', '我的研究'],
  ])('renders %s from a direct entry for an authenticated visitor', async (path, title) => {
    renderRoute(path, { status: 'authenticated' })

    expect(
      await screen.findByRole('heading', { name: title }),
    ).toBeVisible()
  })

  it('opens New Research as a conversation-led workspace with an honest empty canvas', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ items: [] })))
    renderRoute('/research/new', { status: 'authenticated' })

    const workspace = await screen.findByRole('region', { name: '新建研究工作区' })
    expect(within(workspace).getByRole('heading', { name: '从一个社会学问题开始' })).toBeVisible()
    expect(within(workspace).getByText('研究论证地图')).toBeVisible()
    expect(within(workspace).getByText('等待研究问题')).toBeVisible()
    expect(within(workspace).getByRole('textbox', { name: '和 Agent 讨论你的研究' })).toBeVisible()
    expect(within(workspace).getByText('不是聊天摘要。这里仅保留 Agent 明确建立的问题、理论、主张、证据与缺口。')).toBeVisible()
  })

  it('projects a real Agent turn into research map nodes and traceable evidence', async () => {
    const conversation = {
      ...agentConversationFixture('为什么同一社区里的互助正在减少？'),
      turns: [{
        ...agentConversationFixture().turns[0],
        assistant: {
          ...agentConversationFixture().turns[0].assistant,
          citations: [{
            citation_id: 'knowledge:mutual-aid',
            label: '互惠规范与社区互助',
            kind: 'entry',
            excerpt: '互惠规范会影响持续互助的机会。',
            knowledge_id: 'D1:C009',
          }],
        },
      }],
      research_map: {
        schema_version: 1,
        nodes: [{
          id: 'synthesis-mutual-aid',
          kind: 'synthesis',
          title: '互助关系的结构性变化',
          summary: '把社区互助放回信任与互动机会的变化中理解。',
          status: 'grounded',
          citation_ids: ['knowledge:mutual-aid'],
        }],
        relations: [],
      },
    }
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = requestUrl(input)
      if (request.pathname === '/api/agent/turns') return agentStreamResponse(conversation)
      return json({ items: [] })
    }))
    renderRoute('/research/new', { status: 'authenticated' })

    const workspace = await screen.findByRole('region', { name: '新建研究工作区' })
    const textbox = within(workspace).getByRole('textbox', { name: '和 Agent 讨论你的研究' })
    fireEvent.change(textbox, { target: { value: '为什么同一社区里的互助正在减少？' } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)

    expect(await within(workspace).findByText('互惠规范与社区互助')).toBeVisible()
    expect(within(workspace).getByText('研究论证地图')).toBeVisible()
    await waitFor(() => expect(within(workspace).getByText('互助关系的结构性变化')).toBeInTheDocument())
    expect(within(workspace).getByRole('button', { name: /查看证据/ })).toBeVisible()
  })

  it('opens an independent Agent conversation page from the product rail', async () => {
    const conversation = agentConversationFixture()
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = requestUrl(input)
      if (request.pathname === '/api/agent/turns') return agentStreamResponse(conversation)
      if (request.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    renderRoute('/agent', { status: 'authenticated' })

    const desktopNavigation = await screen.findByRole('navigation', { name: '桌面主导航' })
    expect(within(desktopNavigation).getByRole('link', { name: '研究 Agent' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(screen.getByRole('button', { name: '收起侧栏' })).toBeVisible()

    const agentConversation = screen.getByRole('region', { name: '社会学 Agent 对话' })
    expect(within(agentConversation).queryByText('从知识库出发，和你的学科 Agent 直接聊。')).not.toBeInTheDocument()
    const textbox = within(agentConversation).getByRole('textbox', { name: '问社会学 Agent' })
    const sendButton = within(agentConversation).getByRole('button', {
      name: '发送给社会学 Agent',
    })

    expect(textbox).toBeVisible()
    expect(sendButton).toBeDisabled()
    expect(within(agentConversation).queryByText('交互预览 · 未连接模型')).not.toBeInTheDocument()
    expect(within(agentConversation).queryByText(/^Agent$/)).not.toBeInTheDocument()

    fireEvent.change(textbox, { target: { value: '为什么同一社区里的互助正在减少？' } })
    expect(textbox).toHaveValue('为什么同一社区里的互助正在减少？')
    expect(sendButton).toBeEnabled()

    fireEvent.keyDown(textbox, { key: 'Enter', code: 'Enter' })

    const conversationPreview = within(agentConversation).getByRole('log', { name: '对话内容' })
    expect(within(conversationPreview).getByText('为什么同一社区里的互助正在减少？')).toBeInTheDocument()
    const toolSummary = await within(conversationPreview).findByRole('button', {
      name: /Agent 已完成工具调用/,
    })
    expect(toolSummary).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(toolSummary)
    expect(within(conversationPreview).getByText('检索知识库')).toBeVisible()
    expect(within(conversationPreview).getByText(/社区互助减少/)).toBeVisible()
    expect(within(conversationPreview).getByText(/找到 1 条可引用证据/)).toBeVisible()
    expect(within(conversationPreview).queryByText(/^Agent$/)).not.toBeInTheDocument()
    expect(textbox).toHaveValue('')
    expect(within(agentConversation).getByRole('button', { name: '发送给社会学 Agent' })).toBeVisible()
  })

  it('answers directly without pretending that every turn searches the knowledge library', async () => {
    const conversation = agentConversationFixture('怎么理解年轻人越来越孤独？')
    conversation.turns[0].assistant.content = '可以从关系结构、城市流动和数字媒介三个层面理解。'
    const directStream = pausableDirectAgentStream(conversation)
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = requestUrl(input)
      if (request.pathname === '/api/agent/turns') return directStream.response
      if (request.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    renderRoute('/agent', { status: 'authenticated' })

    const agentConversation = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    const textbox = within(agentConversation).getByRole('textbox', { name: '问社会学 Agent' })
    fireEvent.change(textbox, { target: { value: conversation.title } })
    fireEvent.keyDown(textbox, { key: 'Enter', code: 'Enter' })

    expect(await within(agentConversation).findByText('Agent 正在组织问题与证据…')).toBeVisible()
    expect(within(agentConversation).queryByText('正在检索知识库…')).not.toBeInTheDocument()
    expect(within(agentConversation).queryByRole('region', { name: 'Agent 工作过程' })).not.toBeInTheDocument()

    directStream.finish()
    expect(await within(agentConversation).findByText(conversation.turns[0].assistant.content)).toBeVisible()
  })

  it('keeps a failed tool call visible while the Agent continues with a useful answer', async () => {
    const conversation = agentConversationFixture('怎么理解年轻人越来越孤独？')
    conversation.turns[0].assistant.content = '知识库暂时不可用，我先基于通用社会学知识回答。'
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = requestUrl(input)
      if (request.pathname === '/api/agent/turns') return failedToolStreamResponse(conversation)
      if (request.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    renderRoute('/agent', { status: 'authenticated' })

    const agentConversation = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    const textbox = within(agentConversation).getByRole('textbox', { name: '问社会学 Agent' })
    fireEvent.change(textbox, { target: { value: conversation.title } })
    fireEvent.keyDown(textbox, { key: 'Enter', code: 'Enter' })

    const failedToolSummary = await within(agentConversation).findByRole('button', { name: /工具调用未完成/ })
    expect(failedToolSummary).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(failedToolSummary)
    expect(within(agentConversation).getByText('知识库暂时不可用')).toBeVisible()
    expect(within(agentConversation).getByText(conversation.turns[0].assistant.content)).toBeVisible()
  })

  it('keeps repeated tool calls separate while replayed events with the same call id stay idempotent', async () => {
    const conversation = agentConversationFixture('怎么理解青年孤独？')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = requestUrl(input)
      if (request.pathname === '/api/agent/turns') return repeatedToolStreamResponse(conversation)
      if (request.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    renderRoute('/agent', { status: 'authenticated' })

    const agentConversation = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    const textbox = within(agentConversation).getByRole('textbox', { name: '问社会学 Agent' })
    fireEvent.change(textbox, { target: { value: conversation.title } })
    fireEvent.keyDown(textbox, { key: 'Enter', code: 'Enter' })

    const repeatedToolSummary = await within(agentConversation).findByRole('button', { name: /Agent 已完成工具调用/ })
    expect(repeatedToolSummary).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(repeatedToolSummary)
    expect(within(agentConversation).getAllByText('检索知识库')).toHaveLength(2)
    expect(within(agentConversation).getByText(/query: 青年/)).toBeVisible()
    expect(within(agentConversation).getByText(/query: 孤独/)).toBeVisible()
  })

  it('settles the UI and marks an active tool unfinished when generation is stopped', async () => {
    const conversation = agentConversationFixture('怎么理解青年孤独？')
    const stream = pausableToolAgentStream(conversation)
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = requestUrl(input)
      if (request.pathname === '/api/agent/turns') return stream.response
      if (request.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    renderRoute('/agent', { status: 'authenticated' })

    const agentConversation = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    const textbox = within(agentConversation).getByRole('textbox', { name: '问社会学 Agent' })
    fireEvent.change(textbox, { target: { value: conversation.title } })
    fireEvent.keyDown(textbox, { key: 'Enter', code: 'Enter' })

    fireEvent.click(await within(agentConversation).findByRole('button', { name: '停止生成' }))
    stream.close()

    expect(await within(agentConversation).findByText('本轮已停止，未保存未完成的回答。')).toBeVisible()
    expect(within(agentConversation).queryByText('Agent 正在组织问题与证据…')).not.toBeInTheDocument()
    expect(within(agentConversation).getByText('工具调用已中断')).toBeVisible()
    expect(within(agentConversation).getByRole('textbox', { name: '问社会学 Agent' })).toBeEnabled()
    expect(within(agentConversation).getByRole('button', { name: '发送给社会学 Agent' })).toBeVisible()
  })

  it('reveals citation context through Sources and Basis before opening a knowledge entry', async () => {
    const conversation = agentConversationFixture()
    conversation.turns[0].assistant.citations = [{
      citation_id: 'citation-1',
      label: '互惠规范',
      kind: 'entry',
      excerpt: '互惠规范描述了持续互动中信任与回报的关系。',
      knowledge_id: 'D1:C001',
    }]
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = requestUrl(input)
      if (request.pathname === '/api/agent/conversations') {
        return json({
          items: [{
            conversation_id: conversation.conversation_id,
            title: conversation.title,
            updated_at: conversation.updated_at,
            turn_count: conversation.turn_count,
          }],
        })
      }
      if (request.pathname === `/api/agent/conversations/${conversation.conversation_id}`) {
        return json(conversation)
      }
      return json({}, 404)
    }))
    renderRoute('/agent', { status: 'authenticated' })

    const history = await screen.findByRole('region', { name: 'Agent 对话记录' })
    fireEvent.click(within(history).getByRole('button', { name: /为什么同一社区里的互助正在减少/ }))

    const citation = await screen.findByRole('button', { name: '查看证据：互惠规范' })
    expect(screen.queryByText('互惠规范描述了持续互动中信任与回报的关系。')).not.toBeInTheDocument()
    fireEvent.click(citation)

    const sources = await screen.findByRole('tabpanel', { name: 'Sources' })
    fireEvent.click(within(sources).getByRole('button', { name: /互惠规范/ }))
    const basis = await screen.findByRole('tabpanel', { name: 'Basis' })
    expect(within(basis).getByText('互惠规范描述了持续互动中信任与回报的关系。')).toBeVisible()
  })

  it('hides internal citation ids from rendered Agent prose', async () => {
    const conversation = agentConversationFixture()
    conversation.turns[0].assistant.content = '回答依据 [knowledge:D1:C065]。'
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = requestUrl(input)
      if (request.pathname === '/api/agent/conversations') {
        return json({
          items: [{
            conversation_id: conversation.conversation_id,
            title: conversation.title,
            updated_at: conversation.updated_at,
            turn_count: conversation.turn_count,
          }],
        })
      }
      if (request.pathname === `/api/agent/conversations/${conversation.conversation_id}`) {
        return json(conversation)
      }
      return json({}, 404)
    }))
    renderRoute('/agent', { status: 'authenticated' })

    const history = await screen.findByRole('region', { name: 'Agent 对话记录' })
    fireEvent.click(within(history).getByRole('button', { name: /为什么同一社区里的互助正在减少/ }))

    const transcript = await screen.findByRole('log', { name: '对话内容' })
    expect(transcript).toHaveTextContent('回答依据 。')
    expect(transcript).not.toHaveTextContent('knowledge:D1:C065')
  })

  it('keeps Agent conversation history after the page is reopened', async () => {
    const conversation = agentConversationFixture('县城青年为什么重新组织熟人关系？')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = requestUrl(input)
      if (request.pathname === '/api/agent/turns') {
        return agentStreamResponse(conversation)
      }
      if (request.pathname === '/api/agent/conversations/agent-conversation-1') {
        return json(conversation)
      }
      if (request.pathname === '/api/agent/conversations') {
        return json({
          items: [{
            conversation_id: conversation.conversation_id,
            title: conversation.title,
            updated_at: conversation.updated_at,
            turn_count: conversation.turn_count,
          }],
        })
      }
      return json({}, 404)
    }))
    renderRoute('/agent', { status: 'authenticated' })

    const history = await screen.findByRole('region', { name: 'Agent 对话记录' })
    await within(history).findByRole('button', {
      name: /县城青年为什么重新组织熟人关系？/,
    })
    cleanup()
    renderRoute('/agent', { status: 'authenticated' })

    const reopenedHistory = await screen.findByRole('region', { name: 'Agent 对话记录' })
    fireEvent.click(within(reopenedHistory).getByRole('button', {
      name: /县城青年为什么重新组织熟人关系？/,
    }))

    expect(
      await within(screen.getByRole('log', { name: '对话内容' })).findByText(
        '县城青年为什么重新组织熟人关系？',
      ),
    ).toBeVisible()
  })

  it('restores the real tool trace when a saved Agent conversation is reopened', async () => {
    const conversation = agentConversationFixture('请检索知识库解释社会行动四类型')
    conversation.turns[0].tool_traces = [
      {
        tool: 'search_knowledge',
        phase: 'started',
        call_id: 'tool-search-1',
        input: { query: '社会行动四类型' },
        output: null,
        detail: '正在检索知识库',
        error: null,
      },
      {
        tool: 'search_knowledge',
        phase: 'finished',
        call_id: 'tool-search-1',
        input: { query: '社会行动四类型' },
        output: {
          result_count: 1,
          items: [{
            knowledge_id: 'D1:C029',
            title: '社会行动四类型',
            excerpt: '韦伯将社会行动区分为目的理性、价值理性、情感和传统四类。',
          }],
        },
        detail: '找到 1 条知识库预览内容（未审核）：社会行动四类型：韦伯将社会行动区分为目的理性、价值理性、情感和传统四类。',
        error: null,
      },
    ]
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = requestUrl(input)
      if (request.pathname === '/api/agent/conversations') {
        return json({
          items: [{
            conversation_id: conversation.conversation_id,
            title: conversation.title,
            updated_at: conversation.updated_at,
            turn_count: conversation.turn_count,
          }],
        })
      }
      if (request.pathname === `/api/agent/conversations/${conversation.conversation_id}`) {
        return json(conversation)
      }
      return json({}, 404)
    }))
    renderRoute('/agent', { status: 'authenticated' })

    const history = await screen.findByRole('region', { name: 'Agent 对话记录' })
    fireEvent.click(within(history).getByRole('button', { name: /社会行动四类型/ }))
    const transcript = await screen.findByRole('log', { name: '对话内容' })
    const restoredToolSummary = await within(transcript).findByRole('button', { name: /Agent 已完成工具调用/ })
    expect(restoredToolSummary).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(restoredToolSummary)

    expect(within(transcript).getByText(/韦伯将社会行动区分为目的理性/)).toBeVisible()
  })

  it('keeps Shift+Enter available for a new line on the Agent page', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ items: [] })))
    renderRoute('/agent', { status: 'authenticated' })

    const agentConversation = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    const textbox = within(agentConversation).getByRole('textbox', { name: '问社会学 Agent' })

    fireEvent.change(textbox, { target: { value: '第一行' } })
    expect(fireEvent.keyDown(textbox, {
      key: 'Enter',
      code: 'Enter',
      shiftKey: true,
    })).toBe(true)
    fireEvent.change(textbox, { target: { value: '第一行\n第二行' } })

    expect(textbox).toHaveValue('第一行\n第二行')
    expect(
      within(agentConversation).queryByText('当前只演示对话界面，尚未连接研究模型。'),
    ).not.toBeInTheDocument()
  })

  it('shows the public product home at root for an anonymous visitor', async () => {
    renderRoute('/')

    expect(
      await screen.findByRole('heading', {
        name: /从真实困惑.*找到可研究的问题。/,
      }),
    ).toBeVisible()
    expect(screen.getByTestId('route-location')).toHaveTextContent('/')
  })

  it('sends an authenticated root visit straight to the work home', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ items: [], next_cursor: null })))
    renderRoute('/', { status: 'authenticated' })

    expect(await screen.findByRole('heading', { name: '工作台' })).toBeVisible()
    expect(screen.getByTestId('route-location')).toHaveTextContent('/app')
  })

  it('shows the latest research and its next action on the work home', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({
      items: [{
        adopted_theory_count: 0,
        allowed_actions: ['confirm_phenomenon'],
        created_at: '2026-08-08T08:00:00Z',
        current_framework_id: null,
        current_match_run_id: null,
        current_material_intake_run_id: null,
        current_phenomenon_candidate_id: 'candidate-1',
        current_stage: 'phenomenon_confirmation',
        entry_type: 'direct',
        phenomenon_summary: {
          phenomenon: '同一社区中的互助为何逐渐减少？',
          research_intent: '比较关系持续性与制度规范的解释',
        },
        seed_theory_id: null,
        seed_theory_name: null,
        status: 'active',
        task_id: 'task-1',
        updated_at: '2026-08-09T08:00:00Z',
        version: 1,
      }],
      next_cursor: null,
    })))

    renderRoute('/app', { status: 'authenticated' })

    expect(await screen.findByText('同一社区中的互助为何逐渐减少？')).toBeVisible()
    expect(screen.getByText('下一步：确认现象')).toBeVisible()
    expect(screen.getByRole('link', { name: /现象待确认.*同一社区中的互助为何逐渐减少/ })).toHaveAttribute(
      'href',
      '/research/task-1/phenomenon',
    )
  })

  it('offers a real starting path when the work home has no research', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ items: [], next_cursor: null })))

    renderRoute('/app', { status: 'authenticated' })

    expect(await screen.findByText('还没有研究任务')).toBeVisible()
    expect(screen.getAllByRole('link', { name: '新建研究' })).toHaveLength(2)
    expect(screen.queryByRole('link', { name: /内置案例/ })).not.toBeInTheDocument()
  })

  it('lets the user retry when the work home cannot load research', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ error: { code: 'offline' } }, 503)))

    renderRoute('/app', { status: 'authenticated' })

    expect(await screen.findByRole('alert')).toHaveTextContent('暂时无法读取最近研究')
    expect(screen.getByRole('button', { name: '重新加载研究' })).toBeVisible()
  })

  it.each([
    ['anonymous' as const, '体验研究流程'],
    ['authenticated' as const, '进入工作台'],
  ])('keeps /welcome public for a %s visitor', async (status, action) => {
    renderRoute('/welcome', { status })

    expect(
      await screen.findByRole('heading', {
        name: /从真实困惑.*找到可研究的问题。/,
      }),
    ).toBeVisible()
    expect(screen.getByRole('link', { name: action })).toBeVisible()
    expect(screen.getByTestId('route-location')).toHaveTextContent('/welcome')
  })

  it.each([
    ['/login', '登录'],
    ['/register', '注册'],
  ])('renders the public account route %s for an anonymous visitor', async (path, title) => {
    renderRoute(path)

    expect(await screen.findByRole('heading', { name: title })).toBeVisible()
  })

  it.each([
    '/app',
    '/agent',
    '/research/new?source=home',
    '/research/task-1/phenomenon',
    '/research/task-1/match',
    '/research/task-1/framework',
    '/my',
  ])('sends anonymous visitors to login while preserving %s', async (path) => {
    renderRoute(path)

    expect(await screen.findByRole('heading', { name: '登录' })).toBeVisible()
    expect(screen.getByTestId('route-location')).toHaveTextContent(
      `/login?redirect=${encodeURIComponent(path)}`,
    )
  })

  it('keeps an authenticated visitor on a protected route', async () => {
    renderRoute('/research/task-1/phenomenon', { status: 'authenticated' })

    expect(
      await screen.findByRole('heading', { name: '确认现象' }),
    ).toBeVisible()
    expect(screen.queryByRole('heading', { name: '登录' })).not.toBeInTheDocument()
  })

  it('waits for the session boundary before deciding on a protected route', async () => {
    renderRoute('/my', { status: 'loading' })

    expect(await screen.findByRole('status')).toHaveTextContent('正在确认登录状态')
    expect(screen.queryByRole('heading', { name: '登录' })).not.toBeInTheDocument()
  })

  it('uses a same-origin redirect after login', async () => {
    renderRoute('/login?redirect=%2Fresearch%2Ftask-1%2Fframework')

    expect(await screen.findByRole('button', { name: '登录并继续' })).toBeVisible()
    expect(screen.getByRole('link', { name: '创建账号' })).toHaveAttribute(
      'href',
      `/register?redirect=${encodeURIComponent('/research/task-1/framework')}`,
    )
  })

  it('rejects an external login redirect', async () => {
    renderRoute('/login?redirect=https%3A%2F%2Fevil.example%2Ftakeover')

    expect(await screen.findByRole('link', { name: '创建账号' })).toHaveAttribute(
      'href',
      `/register?redirect=${encodeURIComponent('/app')}`,
    )
  })

  it('rejects a malformed login redirect without crashing the page', async () => {
    renderRoute('/login?redirect=%2F%2F%5B')

    expect(await screen.findByRole('heading', { name: '登录' })).toBeVisible()
    expect(screen.getByRole('link', { name: '创建账号' })).toHaveAttribute(
      'href',
      `/register?redirect=${encodeURIComponent('/app')}`,
    )
  })

  it('preserves a protected route hash through login', async () => {
    const destination = '/research/task-1/phenomenon?source=home#evidence'
    renderRoute(destination)

    expect(await screen.findByRole('heading', { name: '登录' })).toBeVisible()
    expect(screen.getByTestId('route-location')).toHaveTextContent(
      `/login?redirect=${encodeURIComponent(destination)}`,
    )
    expect(screen.getByRole('link', { name: '创建账号' })).toHaveAttribute(
      'href',
      `/register?redirect=${encodeURIComponent(destination)}`,
    )
  })

  it('returns to the protected deep link after a real login response', async () => {
    const destination = '/research/task-1/framework?from=my#methods'
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = input as Request
      if (request.method === 'GET') {
        return new Response(
          JSON.stringify({ error: { code: 'unauthenticated', message: '请先登录。', trace_id: 'trace-1' } }),
          { status: 401, headers: { 'Content-Type': 'application/json' } },
        )
      }
      return new Response(JSON.stringify({
        session_id: '25b191bb-2d85-4a88-8863-2cabf506a7a8',
        status: 'active',
        version: 1,
        allowed_actions: ['logout'],
        user: { user_id: '95306bf9-194d-4677-be2d-eef4f6aa86d1', email: 'researcher@example.com', display_name: null },
        expires_at: '2026-08-14T00:00:00Z',
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <MemoryRouter initialEntries={[`/login?redirect=${encodeURIComponent(destination)}`]}>
        <QueryClientProvider client={queryClient}>
          <AccountProvider>
            <AppRoutes />
            <RouteLocation />
          </AccountProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    )

    fireEvent.change(await screen.findByLabelText('邮箱'), { target: { value: 'researcher@example.com' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'research-passphrase' } })
    fireEvent.click(screen.getByRole('button', { name: '登录并继续' }))

    expect(await screen.findByRole('heading', { name: '研究框架文档' })).toBeVisible()
    expect(screen.getByTestId('route-location')).toHaveTextContent(destination)
  })

  it('returns home after logging out from my research', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = input as Request
      if (request.method === 'GET' && request.url.endsWith('/api/session')) {
        return new Response(JSON.stringify({
          session_id: '25b191bb-2d85-4a88-8863-2cabf506a7a8',
          status: 'active',
          version: 1,
          allowed_actions: ['logout'],
          user: {
            user_id: '95306bf9-194d-4677-be2d-eef4f6aa86d1',
            email: 'researcher@example.com',
            display_name: null,
          },
          expires_at: '2026-08-14T00:00:00Z',
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      if (request.method === 'GET') {
        return new Response(JSON.stringify({ items: [], next_cursor: null }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      return new Response(JSON.stringify({
        status: 'logged_out',
        version: 1,
        allowed_actions: [],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <MemoryRouter initialEntries={['/my']} useTransitions={false}>
        <QueryClientProvider client={queryClient}>
          <AccountProvider>
            <AppRoutes />
            <RouteLocation />
          </AccountProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    )

    const accountRail = await screen.findByRole('complementary', { name: '群学致知功能栏' })
    fireEvent.click(within(accountRail).getByRole('button', { name: '退出' }))

    expect(await screen.findByRole('heading', { name: /从真实困惑.*找到可研究的问题。/ })).toBeVisible()
    expect(screen.getByTestId('route-location')).toHaveTextContent('/')
  })

  it('resolves a first knowledge visit to one fixed release before loading its directory', async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const request = requestUrl(input)
      return request.pathname === '/api/knowledge/releases/current'
        ? json({
            content_hash: 'sha256:release-a',
            knowledge_release_id: 'release-a',
            level: 'preview',
          })
        : knowledgeResponse(input)
    })
    vi.stubGlobal('fetch', fetch)

    renderRoute('/knowledge')

    expect(await screen.findByRole('heading', { name: '本体论' })).toBeVisible()
    await waitFor(() => {
      expect(screen.getByTestId('route-location')).toHaveTextContent(
        '/knowledge?knowledge_release_id=release-a',
      )
    })
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('keeps the selected release and filters while opening an independent detail route', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => knowledgeResponse(input)))
    renderRoute('/knowledge?knowledge_release_id=release-a&query=%E6%A6%82%E5%BF%B5&dimension_id=D1&category_id=C001')

    const results = (await screen.findByRole('heading', { name: '条目' })).closest('section')
    if (!results) throw new Error('知识结果区域缺失')
    fireEvent.click(await within(results).findByRole('button', { name: '打开 概念' }))

    expect(screen.getByTestId('route-location')).toHaveTextContent(
      '/knowledge/D1%3AC001?knowledge_release_id=release-a&query=%E6%A6%82%E5%BF%B5&dimension_id=D1&category_id=C001',
    )
  })

  it('opens a release-pinned detail and returns to the supplied research task', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json(knowledgeDetail())))
    renderRoute(
      '/knowledge/D1%3AC001?knowledge_release_id=release-a&return_to=%2Fresearch%2Ftask-1%2Fmatch',
      { status: 'authenticated' },
    )

    expect(await screen.findByText('一段真实条目正文。')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: '返回研究任务' }))

    expect(await screen.findByRole('heading', { name: '理论判断文档' })).toBeVisible()
    expect(screen.getByTestId('route-location')).toHaveTextContent('/research/task-1/match')
  })

  it('returns from a detail to a safe graph workspace context', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json(knowledgeDetail())))
    const graphContext = '/knowledge/graph?knowledge_release_id=release-a&query=%E7%A4%BE%E4%BC%9A&center=D1%3AC001&pending=1'
    renderRoute(
      `/knowledge/D1%3AC001?knowledge_release_id=release-a&return_to=${encodeURIComponent(graphContext)}`,
    )

    expect(await screen.findByText('一段真实条目正文。')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: '返回知识图谱' }))

    expect(screen.getByTestId('route-location')).toHaveTextContent(graphContext)
  })

  it('exposes the structural graph on the knowledge page without eagerly requesting edges', async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) => knowledgeResponse(input))
    vi.stubGlobal('fetch', fetch)
    renderRoute('/knowledge?knowledge_release_id=release-a')

    expect(await screen.findByRole('button', { name: '打开知识图谱' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: '知识关系图' })).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('keeps reviewed relation details factual without a second graph request', async () => {
    const fetch = vi.fn(async () => json(knowledgeDetailWithRelation()))
    vi.stubGlobal('fetch', fetch)
    renderRoute('/knowledge/D1%3AC001?knowledge_release_id=release-a')

    expect(await screen.findByText('真实已审核关系。')).toBeVisible()
    expect(screen.getByRole('button', { name: '返回知识库' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: '知识关系图' })).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('keeps only the theory ID in the URL when starting research from knowledge', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const request = requestUrl(input)
      if (request.pathname === '/api/knowledge/entries/D1%3AC001') {
        return json(knowledgeDetailWithTheoryProfile())
      }
      if (request.pathname === '/api/phenomenon-examples') return json({ items: [] })
      return json(knowledgeDetailWithTheoryProfile())
    }))
    renderRoute('/knowledge/D1%3AC001?knowledge_release_id=release-a', { status: 'authenticated' })

    fireEvent.click(await screen.findByRole('button', { name: '以此理论开始研究' }))

    expect((await screen.findAllByText('围绕「社会资本理论」展开研究')).length).toBe(2)
    expect(screen.getByTestId('route-location')).toHaveTextContent(
      /^\/research\/new\?seed_theory_id=theory-social-capital$/,
    )
  })

  it('resolves a deep knowledge entry to one fixed release before reading its detail', async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const request = requestUrl(input)
      return request.pathname === '/api/knowledge/releases/current'
        ? json({
            content_hash: 'sha256:release-a',
            knowledge_release_id: 'release-a',
            level: 'preview',
          })
        : json(knowledgeDetail())
    })
    vi.stubGlobal('fetch', fetch)

    renderRoute('/knowledge/D1%3AC001')

    expect(await screen.findByText('一段真实条目正文。')).toBeVisible()
    await waitFor(() => {
      expect(screen.getByTestId('route-location')).toHaveTextContent(
        '/knowledge/D1%3AC001?knowledge_release_id=release-a',
      )
    })
    expect(fetch).toHaveBeenCalledTimes(2)
  })
})
