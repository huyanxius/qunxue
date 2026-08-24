import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { AgentCitation, AgentConversation } from '../../modules/research-agent'
import { AppLocaleProvider } from '../../i18n/AppLocaleProvider'
import { ResearchAgentConversationPage } from './ResearchAgentConversationPage'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  delete (document as Document & { startViewTransition?: unknown }).startViewTransition
  window.sessionStorage.clear()
  window.localStorage.clear()
})

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function conversationFixture({
  id = 'conversation-agent',
  prompt = '为什么同一社区里的互助正在减少？',
  answer = '可以从信任、资源压力与互动机会三个层面分析。',
  citations = [],
}: {
  id?: string
  prompt?: string
  answer?: string
  citations?: AgentCitation[]
} = {}): AgentConversation {
  return {
    conversation_id: id,
    title: prompt,
    created_at: '2026-08-22T00:00:00Z',
    updated_at: '2026-08-22T00:00:01Z',
    turn_count: 1,
    turns: [{
      turn_id: `turn-${id}`,
      user: {
        message_id: `message-user-${id}`,
        role: 'user',
        content: prompt,
        citations: [],
        sequence: 1,
        created_at: '2026-08-22T00:00:00Z',
      },
      assistant: {
        message_id: `message-assistant-${id}`,
        role: 'assistant',
        content: answer,
        citations,
        sequence: 2,
        created_at: '2026-08-22T00:00:01Z',
      },
      tool_traces: [],
      knowledge_release_id: 'release-agent',
    }],
  }
}

function eventStream(events: Array<[string, unknown]>) {
  return `${events.map(([name, payload]) => `event: ${name}\ndata: ${JSON.stringify(payload)}`).join('\n\n')}\n\n`
}

function streamResponse(conversation: AgentConversation, runtimeMode: 'mock' | 'base' | 'sft' = 'base') {
  return new Response(eventStream([
    ['turn_started', {
      conversation_id: conversation.conversation_id,
      run_id: `run-${conversation.conversation_id}`,
      replayed: false,
      runtime_mode: runtimeMode,
    }],
    ['agent_status', { status: 'answering' }],
    ['assistant_delta', { delta: conversation.turns[0].assistant.content }],
    ['turn_completed', { conversation, knowledge_release_id: 'release-agent' }],
  ]), { headers: { 'Content-Type': 'text/event-stream' } })
}

function deferredStream(events: Array<[string, unknown]>) {
  const encoder = new TextEncoder()
  let controller: ReadableStreamDefaultController<Uint8Array> | null = null
  const response = new Response(new ReadableStream<Uint8Array>({
    start(streamController) {
      controller = streamController
      streamController.enqueue(encoder.encode(eventStream(events)))
    },
  }), { headers: { 'Content-Type': 'text/event-stream' } })
  return {
    response,
    finish(finalEvents: Array<[string, unknown]>) {
      controller?.enqueue(encoder.encode(eventStream(finalEvents)))
      controller?.close()
    },
  }
}

function renderPage(userId = 'user-agent', path = '/agent') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ResearchAgentConversationPage userId={userId} />
    </MemoryRouter>,
  )
}

function renderEnglishPage(userId = 'user-agent', path = '/agent') {
  window.localStorage.setItem('qunxue.interface-locale', 'en-US')
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppLocaleProvider>
        <ResearchAgentConversationPage userId={userId} />
      </AppLocaleProvider>
    </MemoryRouter>,
  )
}

function urlFor(input: RequestInfo | URL) {
  return typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
}

function LocationProbe() {
  const location = useLocation()
  return <output aria-label="当前测试路径">{location.pathname}{location.search}</output>
}

describe('ResearchAgentConversationPage', () => {
  it('keeps the conversation rail visible while the research history dialog is open', async () => {
    const conversation = conversationFixture({ id: 'conversation-history-rail' })
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = urlFor(input)
      if (url.pathname === '/api/agent/conversations') {
        return json({ items: [{
          conversation_id: conversation.conversation_id,
          title: conversation.title,
          updated_at: conversation.updated_at,
          turn_count: conversation.turn_count,
        }] })
      }
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      return json({}, 404)
    }))
    renderPage('user-agent', `/agent?conversation_id=${conversation.conversation_id}`)

    await screen.findByText(conversation.turns[0].assistant.content)
    expect(screen.getByRole('region', { name: 'Agent 对话记录' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: '打开研究记录' }))

    expect(screen.getByRole('dialog', { name: '研究记录' })).toBeVisible()
    expect(screen.getByRole('region', { name: 'Agent 对话记录' })).toBeVisible()
  })

  it('renames and deletes a saved conversation from its overflow menu', async () => {
    const conversation = conversationFixture({ id: 'conversation-manage' })
    const renamedTitle = '青年婚姻研究'
    const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = urlFor(input)
      if (url.pathname === '/api/agent/conversations' && !init?.method) {
        return json({ items: [{
          conversation_id: conversation.conversation_id,
          title: conversation.title,
          updated_at: conversation.updated_at,
          turn_count: conversation.turn_count,
        }] })
      }
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}` && init?.method === 'PATCH') {
        return json({
          conversation_id: conversation.conversation_id,
          title: renamedTitle,
          updated_at: conversation.updated_at,
          turn_count: conversation.turn_count,
        })
      }
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}` && init?.method === 'DELETE') {
        return new Response(null, { status: 204 })
      }
      return json({}, 404)
    })
    vi.stubGlobal('fetch', fetch)
    renderPage()

    const history = await screen.findByRole('region', { name: 'Agent 对话记录' })
    fireEvent.click(within(history).getByRole('button', { name: '打开对话操作' }))
    fireEvent.click(screen.getByRole('menuitem', { name: '修改名称' }))
    const titleInput = screen.getByRole('textbox', { name: '修改对话名称' })
    fireEvent.change(titleInput, { target: { value: renamedTitle } })
    fireEvent.click(screen.getByRole('button', { name: '保存对话名称' }))

    await waitFor(() => expect(within(history).getByText(renamedTitle)).toBeVisible())
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining(`/api/agent/conversations/${conversation.conversation_id}`),
      expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ title: renamedTitle }) }),
    )

    fireEvent.click(within(history).getByRole('button', { name: '打开对话操作' }))
    fireEvent.click(screen.getByRole('menuitem', { name: '删除对话' }))
    fireEvent.click(screen.getByRole('button', { name: '确认删除对话' }))

    await waitFor(() => expect(within(history).queryByText(renamedTitle)).not.toBeInTheDocument())
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining(`/api/agent/conversations/${conversation.conversation_id}`),
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('embeds the same Agent surface in a research document without rewriting its route', async () => {
    const initial = conversationFixture({ id: 'conversation-research-document' })
    const completed = conversationFixture({
      id: initial.conversation_id,
      prompt: '请补充这一节的反例。',
      answer: '可以加入一个边界条件更强的反例。',
    })
    const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = urlFor(input)
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      if (url.pathname === `/api/agent/conversations/${initial.conversation_id}`) return json(initial)
      if (url.pathname === '/api/agent/turns' && init?.method === 'POST') return streamResponse(completed)
      return json({}, 404)
    })
    vi.stubGlobal('fetch', fetch)

    render(
      <MemoryRouter initialEntries={['/research/task-1/match?view=document']}>
        <ResearchAgentConversationPage
          embedded
          userId="user-agent"
          conversationId={initial.conversation_id}
          knowledgeReleaseId="release-research"
          workspace="research"
          taskId="task-1"
          documentId="document-1"
          sectionId="research_question"
          documentVersion={3}
          theoryPlanId="theory-plan-1"
        />
        <LocationProbe />
      </MemoryRouter>,
    )

    const agent = await screen.findByRole('complementary', { name: '研究 Agent 对话栏' })
    expect(within(agent).getByText(initial.turns[0].assistant.content)).toBeVisible()
    expect(screen.getByLabelText('当前测试路径')).toHaveTextContent('/research/task-1/match?view=document')

    const textbox = within(agent).getByRole('textbox', { name: '问社会学 Agent' })
    fireEvent.change(textbox, { target: { value: '请补充这一节的反例。' } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)

    await waitFor(() => expect(fetch.mock.calls.some(([input]) => urlFor(input).pathname === '/api/agent/turns')).toBe(true))
    const turnCall = fetch.mock.calls.find(([input]) => urlFor(input).pathname === '/api/agent/turns')
    expect(JSON.parse(String(turnCall?.[1]?.body))).toMatchObject({
      conversation_id: initial.conversation_id,
      workspace: 'research',
      task_id: 'task-1',
      document_id: 'document-1',
      section_id: 'research_question',
      document_version: 3,
      theory_plan_id: 'theory-plan-1',
    })
    expect(screen.getByLabelText('当前测试路径')).toHaveTextContent('/research/task-1/match?view=document')
  })

  it('applies the global English locale to an existing conversation', async () => {
    const conversation = conversationFixture({ id: 'conversation-english' })
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = urlFor(input)
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      return json({}, 404)
    }))

    renderEnglishPage('user-agent', `/agent?conversation_id=${conversation.conversation_id}`)

    const region = await screen.findByRole('region', { name: 'Sociology Agent conversation' })
    expect(within(region).getByRole('button', { name: 'Copy answer' })).toBeVisible()
    expect(within(region).getByRole('button', { name: 'Regenerate' })).toBeVisible()
    expect(within(region).getByText(/Knowledge base not searched/)).toBeVisible()
    expect(within(region).getByRole('textbox', { name: 'Ask the Sociology Agent' })).toBeVisible()
  })

  it('keeps the empty Agent focused on starting a conversation', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => (
      urlFor(input).pathname === '/api/agent/conversations' ? json({ items: [] }) : json({}, 404)
    )))
    renderPage()

    const region = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    expect(within(region).queryByRole('navigation', { name: '研究入口' })).not.toBeInTheDocument()
    expect(within(region).getByRole('textbox', { name: '问社会学 Agent' })).toBeVisible()
  })

  it('renders a persisted model proposal as a pinned handoff to New Research', async () => {
    const conversation = conversationFixture({
      id: 'conversation-handoff',
      prompt: '我想继续研究社区流动如何改变邻里互助。',
      answer: '这个问题已经具备一个可继续推进的研究现象。',
    })
    conversation.turns[0].tool_traces = [{
      tool: 'propose_start_research',
      phase: 'finished',
      call_id: 'call-research-handoff',
      input: {
        phenomenon: '社区成员流动正在改变邻里互助',
        research_intent: '解释互助关系变化的机制',
      },
      output: {
        proposal_id: 'proposal-handoff',
        conversation_id: conversation.conversation_id,
        source_run_id: 'run-handoff',
        source_turn_id: conversation.turns[0].turn_id,
        knowledge_release_id: 'release-pinned-handoff',
        phenomenon: '社区成员流动正在改变邻里互助',
        research_intent: '解释互助关系变化的机制',
        context: '城市社区',
        version: 1,
        status: 'pending_confirmation',
        requires_user_confirmation: true,
      },
      detail: '研究起点等待用户确认',
    }]
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = urlFor(input)
      if (url.pathname === '/api/agent/conversations') {
        return json({ items: [{
          conversation_id: conversation.conversation_id,
          title: conversation.title,
          updated_at: conversation.updated_at,
          turn_count: conversation.turn_count,
        }] })
      }
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      return json({}, 404)
    }))
    renderPage('user-agent', `/agent?conversation_id=${conversation.conversation_id}`)

    const region = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    const handoff = await within(region).findByRole('region', { name: '研究建议' })
    expect(within(handoff).getByText('社区成员流动正在改变邻里互助')).toBeVisible()
    expect(within(handoff).getByRole('link', { name: '去新建研究' })).toHaveAttribute(
      'href',
      '/research/new?conversation_id=conversation-handoff&knowledge_release_id=release-pinned-handoff',
    )
    expect(within(handoff).queryByRole('button', { name: /确认|创建/ })).not.toBeInTheDocument()
  })

  it('renders pinned knowledge and graph cards after a real knowledge search', async () => {
    const citation: AgentCitation = {
      citation_id: 'citation-community-knowledge',
      label: '集体知识与群体认知',
      kind: 'preview',
      excerpt: '个体经验与群体认知之间存在还原与涌现的张力。',
      knowledge_id: 'D5:E087',
    }
    const conversation = conversationFixture({
      id: 'conversation-knowledge-handoffs',
      prompt: '请在知识库查一下个体经验与群体经验。',
      answer: '我找到了一个可以继续阅读和探索的知识条目。',
      citations: [citation],
    })
    conversation.turns[0].knowledge_release_id = 'release-pinned-knowledge'
    conversation.turns[0].tool_traces = [{
      tool: 'search_knowledge',
      phase: 'finished',
      call_id: 'call-search-knowledge',
      input: { query: '个体经验 群体经验' },
      output: { results: [{ knowledge_id: citation.knowledge_id, title: citation.label }] },
      detail: '找到 1 条知识库预览内容（未审核）：集体知识与群体认知',
    }]
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = urlFor(input)
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      return json({}, 404)
    }))
    renderPage('user-agent', `/agent?conversation_id=${conversation.conversation_id}`)

    const region = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    expect(region).not.toHaveTextContent('未审核')
    const knowledgeCard = await within(region).findByRole('region', { name: '知识库建议' })
    const graphCard = within(region).getByRole('region', { name: '知识图谱建议' })
    expect(within(knowledgeCard).getByText(citation.label)).toBeVisible()
    expect(within(knowledgeCard).getByRole('link', { name: '打开知识条目' })).toHaveAttribute(
      'href',
      '/knowledge/D5%3AE087?knowledge_release_id=release-pinned-knowledge&return_to=%2Fagent%3Fconversation_id%3Dconversation-knowledge-handoffs%26knowledge_release_id%3Drelease-pinned-knowledge',
    )
    expect(within(graphCard).getByRole('link', { name: '查看知识节点' })).toHaveAttribute(
      'href',
      '/knowledge/graph?knowledge_release_id=release-pinned-knowledge&center=D5%3AE087&query=%E9%9B%86%E4%BD%93%E7%9F%A5%E8%AF%86%E4%B8%8E%E7%BE%A4%E4%BD%93%E8%AE%A4%E7%9F%A5',
    )
  })

  it.each([
    ['turn_interrupted', { code: 'interrupted', message: '本轮已停止。' }],
    ['turn_failed', { code: 'agent_unavailable', message: '本轮生成失败。' }],
  ])('does not render an unpersisted handoff after %s', async (terminalEvent, payload) => {
    const proposalOutput = {
      proposal_id: 'proposal-unpersisted',
      conversation_id: 'conversation-unpersisted',
      source_run_id: 'run-unpersisted',
      source_turn_id: 'turn-unpersisted',
      knowledge_release_id: 'release-unpersisted',
      phenomenon: '社区成员流动正在改变邻里互助',
      research_intent: '解释互助关系变化的机制',
      context: '城市社区',
      version: 1,
      status: 'pending_confirmation',
      requires_user_confirmation: true,
    }
    const response = new Response(eventStream([
      ['turn_started', {
        conversation_id: 'conversation-unpersisted',
        run_id: 'run-unpersisted',
        replayed: false,
        runtime_mode: 'base',
      }],
      ['tool_started', {
        tool: 'propose_start_research',
        call_id: 'call-unpersisted',
        input: { phenomenon: proposalOutput.phenomenon },
      }],
      ['tool_finished', {
        tool: 'propose_start_research',
        call_id: 'call-unpersisted',
        output: proposalOutput,
      }],
      [terminalEvent, payload],
    ]), { headers: { 'Content-Type': 'text/event-stream' } })
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => (
      urlFor(input).pathname === '/api/agent/turns' ? response : json({ items: [] })
    )))
    renderPage()

    const region = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    const textbox = within(region).getByRole('textbox', { name: '问社会学 Agent' })
    fireEvent.change(textbox, { target: { value: '把这个现象继续形成研究。' } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)

    expect(await within(region).findByRole('button', { name: '重试本轮' })).toBeVisible()
    expect(within(region).queryByRole('region', { name: '研究建议' })).not.toBeInTheDocument()
  })

  it('keeps knowledge entry and graph links pinned to the citation turn', async () => {
    const citation: AgentCitation = {
      citation_id: 'citation-social-capital',
      label: '社会资本与邻里互助',
      kind: 'entry',
      excerpt: '互惠规范会影响社区中的持续互助。',
      knowledge_id: 'D1:C001',
    }
    const conversation = conversationFixture({
      id: 'conversation-citation-links',
      answer: '这条解释可以继续回到知识条目和知识图谱核对。',
      citations: [citation],
    })
    const firstTurn = conversation.turns[0]
    conversation.turns = [
      { ...firstTurn, knowledge_release_id: 'release-turn-old' },
      {
        ...firstTurn,
        turn_id: 'turn-citation-new',
        user: { ...firstTurn.user, message_id: 'message-user-new', content: '再从新发布版本核对一次。' },
        assistant: { ...firstTurn.assistant, message_id: 'message-assistant-new' },
        knowledge_release_id: 'release-turn-new',
      },
      {
        ...firstTurn,
        turn_id: 'turn-citation-without-release',
        user: { ...firstTurn.user, message_id: 'message-user-without-release', content: '这一轮没有保存发布版本。' },
        assistant: { ...firstTurn.assistant, message_id: 'message-assistant-without-release' },
        knowledge_release_id: null,
      },
    ]
    conversation.turn_count = conversation.turns.length
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = urlFor(input)
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      return json({}, 404)
    }))
    renderPage(
      'user-agent',
      `/agent?conversation_id=${conversation.conversation_id}&knowledge_release_id=release-query-newer`,
    )

    const region = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    const citationButtons = await within(region).findAllByRole('button', { name: `查看证据：${citation.label}` })
    fireEvent.click(citationButtons[0])
    fireEvent.click(await screen.findByRole('tab', { name: 'Basis' }))

    let basis = await screen.findByRole('tabpanel', { name: 'Basis' })
    expect(within(basis).getByRole('link', { name: /打开知识条目/ })).toHaveAttribute(
      'href',
      '/knowledge/D1%3AC001?knowledge_release_id=release-turn-old&return_to=%2Fagent%3Fconversation_id%3Dconversation-citation-links%26knowledge_release_id%3Drelease-turn-old',
    )
    expect(within(basis).getByRole('link', { name: /在知识图谱中查看/ })).toHaveAttribute(
      'href',
      '/knowledge/graph?knowledge_release_id=release-turn-old&center=D1%3AC001&query=%E7%A4%BE%E4%BC%9A%E8%B5%84%E6%9C%AC%E4%B8%8E%E9%82%BB%E9%87%8C%E4%BA%92%E5%8A%A9',
    )

    fireEvent.click(citationButtons[1])
    fireEvent.click(await screen.findByRole('tab', { name: 'Basis' }))
    basis = await screen.findByRole('tabpanel', { name: 'Basis' })
    expect(within(basis).getByRole('link', { name: /打开知识条目/ })).toHaveAttribute(
      'href',
      '/knowledge/D1%3AC001?knowledge_release_id=release-turn-new&return_to=%2Fagent%3Fconversation_id%3Dconversation-citation-links%26knowledge_release_id%3Drelease-turn-new',
    )

    fireEvent.click(citationButtons[2])
    fireEvent.click(await screen.findByRole('tab', { name: 'Basis' }))
    basis = await screen.findByRole('tabpanel', { name: 'Basis' })
    expect(within(basis).queryByRole('link', { name: /打开知识条目|在知识图谱中查看/ })).not.toBeInTheDocument()
    expect(within(basis).getByText('当前回合的知识版本尚未确认，暂不提供跳转。')).toBeVisible()
  })

  it('moves the homepage bot into the first assistant turn with a shared-element transition', async () => {
    const conversation = conversationFixture()
    const startViewTransition = vi.fn((update: () => void) => {
      update()
      return {
        updateCallbackDone: Promise.resolve(),
        ready: Promise.resolve(),
        finished: Promise.resolve(),
        skipTransition: vi.fn(),
      }
    })
    Object.defineProperty(document, 'startViewTransition', {
      configurable: true,
      value: startViewTransition,
    })
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => (
      urlFor(input).pathname === '/api/agent/turns'
        ? streamResponse(conversation)
        : json({ items: [] })
    )))
    renderPage()

    const region = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    expect(region.querySelector('[data-research-agent-bot]')).toBeInTheDocument()
    const textbox = within(region).getByRole('textbox', { name: '问社会学 Agent' })
    fireEvent.change(textbox, { target: { value: conversation.title } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)

    await waitFor(() => expect(startViewTransition).toHaveBeenCalledTimes(1))
    const assistantMark = await within(region).findByLabelText('群学 Agent')
    expect(assistantMark.querySelector('[data-research-agent-bot]')).toBeInTheDocument()
  })

  it('sends independent Agent turns with the agent workspace contract', async () => {
    const conversation = conversationFixture()
    const turnRequests: RequestInit[] = []
    const requestedPaths: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = urlFor(input)
      requestedPaths.push(url.pathname)
      if (url.pathname === '/api/agent/turns') {
        turnRequests.push(init ?? {})
        return streamResponse(conversation)
      }
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    renderPage()

    const region = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    const textbox = within(region).getByRole('textbox', { name: '问社会学 Agent' })
    fireEvent.change(textbox, { target: { value: conversation.title } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)

    expect(await within(region).findByText(conversation.turns[0].assistant.content)).toBeVisible()
    expect(turnRequests).toHaveLength(1)
    expect(JSON.parse(String(turnRequests[0].body))).toMatchObject({
      conversation_id: null,
      message: conversation.title,
      workspace: 'agent',
    })
    expect(requestedPaths.some((path) => path.endsWith('/journey'))).toBe(false)
  })

  it('keeps the 12,000-character contract and restores drafts only for the same account', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => (
      urlFor(input).pathname === '/api/agent/conversations' ? json({ items: [] }) : json({}, 404)
    )))
    const draft = '这是账号 A 还没有发送的田野笔记'
    const firstPage = renderPage('user-a')
    const firstTextbox = await screen.findByRole('textbox', { name: '问社会学 Agent' })
    expect(firstTextbox).toHaveAttribute('maxlength', '12000')
    fireEvent.change(firstTextbox, { target: { value: draft } })
    firstPage.unmount()

    const restoredPage = renderPage('user-a')
    expect(await screen.findByRole('textbox', { name: '问社会学 Agent' })).toHaveValue(draft)
    restoredPage.unmount()

    renderPage('user-b')
    expect(await screen.findByRole('textbox', { name: '问社会学 Agent' })).toHaveValue('')
  })

  it('retries a disconnected turn with the original question and idempotency key', async () => {
    const question = '为什么青年在熟人社区里也会感到孤独？'
    const conversation = conversationFixture({ prompt: question, answer: '可以从关系稳定性与情感劳动继续分析。' })
    const turnRequests: RequestInit[] = []
    const randomUUID = vi.fn(() => 'stable-agent-turn-key')
    vi.stubGlobal('crypto', { randomUUID })
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = urlFor(input)
      if (url.pathname === '/api/agent/turns') {
        turnRequests.push(init ?? {})
        return turnRequests.length === 1
          ? new Response(eventStream([
              ['turn_started', { conversation_id: conversation.conversation_id, run_id: 'run-disconnected', replayed: false }],
              ['assistant_delta', { delta: '只有半段回答' }],
            ]), { headers: { 'Content-Type': 'text/event-stream' } })
          : streamResponse(conversation)
      }
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    renderPage()

    const region = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    const textbox = within(region).getByRole('textbox', { name: '问社会学 Agent' })
    fireEvent.change(textbox, { target: { value: question } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)

    expect(await within(region).findByRole('alert')).toHaveTextContent('回答完成前中断')
    fireEvent.click(within(region).getByRole('button', { name: '重试本轮' }))

    expect(await within(region).findByText(conversation.turns[0].assistant.content)).toBeVisible()
    expect(turnRequests.map((request) => new Headers(request.headers).get('Idempotency-Key'))).toEqual([
      'stable-agent-turn-key',
      'stable-agent-turn-key',
    ])
    expect(turnRequests.map((request) => JSON.parse(String(request.body)))).toEqual([
      expect.objectContaining({ message: question, workspace: 'agent' }),
      expect.objectContaining({ message: question, workspace: 'agent' }),
    ])
    expect(randomUUID).toHaveBeenCalledTimes(1)
  })

  it('keeps copy and regenerate controls live without leaking internal citation tokens', async () => {
    const first = conversationFixture({ answer: '核心解释。[knowledge:D1:C001]' })
    const regenerated = conversationFixture({ answer: '重新生成后的解释。' })
    const turnRequests: RequestInit[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = urlFor(input)
      if (url.pathname === '/api/agent/turns') {
        turnRequests.push(init ?? {})
        return streamResponse(turnRequests.length === 1 ? first : regenerated)
      }
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    const writeText = vi.fn()
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error('denied'))
    const originalClipboard = Object.getOwnPropertyDescriptor(navigator, 'clipboard')
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })

    try {
      renderPage()
      const region = await screen.findByRole('region', { name: '社会学 Agent 对话' })
      const textbox = within(region).getByRole('textbox', { name: '问社会学 Agent' })
      fireEvent.change(textbox, { target: { value: first.title } })
      fireEvent.submit(textbox.closest('form') as HTMLFormElement)

      const copy = await within(region).findByRole('button', { name: '复制回答' })
      fireEvent.click(copy)
      await waitFor(() => expect(copy).toHaveAccessibleName('已复制'))
      expect(writeText).toHaveBeenLastCalledWith('核心解释。')

      fireEvent.click(copy)
      await waitFor(() => expect(copy).toHaveAccessibleName('复制失败'))

      fireEvent.click(within(region).getByRole('button', { name: '重新生成' }))
      expect(await within(region).findByText('重新生成后的解释。')).toBeVisible()
      expect(turnRequests).toHaveLength(2)
      expect(JSON.parse(String(turnRequests[1].body))).toMatchObject({
        conversation_id: first.conversation_id,
        message: first.title,
        workspace: 'agent',
      })
    } finally {
      if (originalClipboard) Object.defineProperty(navigator, 'clipboard', originalClipboard)
      else Reflect.deleteProperty(navigator, 'clipboard')
    }
  })

  it('closes history with Escape and ignores a late stream after switching records', async () => {
    const saved = conversationFixture({
      id: 'conversation-saved',
      prompt: '已保存的社区互助研究',
      answer: '这是已保存的研究回答。',
    })
    const late = conversationFixture({
      id: 'conversation-live',
      prompt: '正在运行的旧问题',
      answer: '这段迟到回答不能覆盖已切换的记录。',
    })
    const liveStream = deferredStream([
      ['turn_started', { conversation_id: late.conversation_id, run_id: 'run-live', replayed: false, runtime_mode: 'base' }],
      ['agent_status', { status: 'answering' }],
      ['assistant_delta', { delta: '旧回答片段' }],
    ])
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = urlFor(input)
      if (url.pathname === '/api/agent/turns') return liveStream.response
      if (url.pathname === '/api/agent/conversations') {
        return json({ items: [{
          conversation_id: saved.conversation_id,
          title: saved.title,
          updated_at: saved.updated_at,
          turn_count: saved.turn_count,
        }] })
      }
      if (url.pathname === `/api/agent/conversations/${saved.conversation_id}`) return json(saved)
      return json({}, 404)
    }))
    renderPage()

    const region = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    const textbox = within(region).getByRole('textbox', { name: '问社会学 Agent' })
    fireEvent.change(textbox, { target: { value: late.title } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)
    expect(await within(region).findByRole('button', { name: '停止生成' })).toBeVisible()

    fireEvent.click(within(region).getByRole('button', { name: '打开研究记录' }))
    const dialog = await within(region).findByRole('dialog', { name: '研究记录' })
    fireEvent.keyDown(dialog, { key: 'Escape' })
    expect(within(region).queryByRole('dialog', { name: '研究记录' })).not.toBeInTheDocument()

    fireEvent.click(within(region).getByRole('button', { name: '打开研究记录' }))
    const reopenedDialog = await within(region).findByRole('dialog', { name: '研究记录' })
    fireEvent.click(within(reopenedDialog).getByRole('button', { name: new RegExp(saved.title) }))

    expect(await within(region).findByText(saved.turns[0].assistant.content)).toBeVisible()
    liveStream.finish([
      ['assistant_delta', { delta: late.turns[0].assistant.content }],
      ['turn_completed', { conversation: late, knowledge_release_id: 'release-late' }],
    ])
    await waitFor(() => {
      expect(within(region).queryByText(late.turns[0].assistant.content)).not.toBeInTheDocument()
      expect(within(region).getByText(saved.turns[0].assistant.content)).toBeVisible()
    })
  })

  it('expands complete tool output and opens an Activity result in Basis', async () => {
    const conversation = conversationFixture({
      prompt: '请检索知识库解释社区互助。',
      answer: '检索结果显示，互惠规范是重要机制。',
    })
    const completeDetail = `完整工具返回：${'社会资本与社区互助的检索证据。'.repeat(40)}`
    const toolStream = new Response(eventStream([
      ['turn_started', { conversation_id: conversation.conversation_id, run_id: 'run-tool', replayed: false, runtime_mode: 'base' }],
      ['tool_started', { tool: 'search_knowledge', call_id: 'tool-search', input: { query: '社区互助' } }],
      ['tool_finished', {
        tool: 'search_knowledge',
        call_id: 'tool-search',
        output: { results: [{ knowledge_id: 'D1:C001', title: '社会资本条目', excerpt: '互惠规范会影响社区互助。' }] },
        detail: completeDetail,
      }],
      ['assistant_delta', { delta: conversation.turns[0].assistant.content }],
      ['turn_completed', { conversation, knowledge_release_id: 'release-agent' }],
    ]), { headers: { 'Content-Type': 'text/event-stream' } })
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = urlFor(input)
      if (url.pathname === '/api/agent/turns') return toolStream
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    renderPage()

    const region = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    const textbox = within(region).getByRole('textbox', { name: '问社会学 Agent' })
    fireEvent.change(textbox, { target: { value: conversation.title } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)

    const toolSummary = await within(region).findByRole('button', { name: /Agent 已完成工具调用/ })
    expect(toolSummary).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(toolSummary)
    expect(within(region).getByText('根据当前研究问题寻找相关概念、理论与已有研究参照')).toBeVisible()
    const disclosure = await within(region).findByRole('button', { name: '查看完整工具返回' })
    expect(within(region).queryByText(completeDetail)).not.toBeVisible()
    fireEvent.click(disclosure)
    expect(within(region).getByText(completeDetail)).toBeVisible()

    fireEvent.click(within(region).getAllByRole('button', { name: '查看活动' })[0])
    const activity = await screen.findByRole('tabpanel', { name: 'Activity' })
    fireEvent.click(within(activity).getByRole('button', { name: /社会资本条目/ }))

    const basis = await screen.findByRole('tabpanel', { name: 'Basis' })
    expect(within(basis).getByText('检索知识库')).toBeVisible()
    expect(within(basis).getByText(/社会资本条目/)).toBeVisible()
    expect(within(basis).getByText(/互惠规范会影响社区互助/)).toBeVisible()
  })

  it('shows a live research phase and restores completed work after the user stops', async () => {
    const liveStream = deferredStream([
      ['turn_started', { conversation_id: 'conversation-stop', run_id: 'run-stop', replayed: false, runtime_mode: 'base' }],
      ['tool_started', { tool: 'search_knowledge', call_id: 'tool-search', input: { query: '青年孤独' }, detail: '正在检索知识库' }],
      ['tool_finished', { tool: 'search_knowledge', call_id: 'tool-search', output: { results: [{ knowledge_id: 'D1:C001', title: '青年孤独研究' }] }, detail: '找到 1 条材料' }],
      ['assistant_delta', { delta: '已经形成一段可保留的回答。' }],
      ['tool_started', { tool: 'read_knowledge_entry', call_id: 'tool-read', input: { knowledge_id: 'D1:C001' }, detail: '正在核对知识条目' }],
    ])
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => (
      urlFor(input).pathname === '/api/agent/turns' ? liveStream.response : json({ items: [] })
    )))

    const first = renderPage('user-stop')
    const region = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    const textbox = within(region).getByRole('textbox', { name: '问社会学 Agent' })
    fireEvent.change(textbox, { target: { value: '研究青年孤独。' } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)

    expect(await within(region).findByText('正在阅读研究材料')).toBeVisible()
    expect(within(region).queryByText(/已运行/)).not.toBeInTheDocument()
    expect(within(region).queryByText('Agent 正在组织问题与证据…')).not.toBeInTheDocument()
    const runningTool = within(region).getByRole('button', { name: /Agent 正在调用工具/ })
    expect(runningTool).toHaveAttribute('aria-expanded', 'false')
    expect(within(region).getByText('根据当前问题核对知识条目的主张、适用前提与证据边界')).not.toBeVisible()
    fireEvent.click(runningTool)
    expect(within(region).getByText('根据当前问题核对知识条目的主张、适用前提与证据边界')).toBeVisible()
    fireEvent.click(within(region).getByRole('button', { name: '停止生成' }))

    expect(await within(region).findByText('本轮已停止，已保留生成内容和 1 个已完成步骤。')).toBeVisible()
    expect(within(region).getByText('已经形成一段可保留的回答。')).toBeVisible()
    first.unmount()

    renderPage('user-stop')
    const restored = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    expect(within(restored).getByText('已经形成一段可保留的回答。')).toBeVisible()
    expect(within(restored).getByText('本轮已停止，已保留生成内容和 1 个已完成步骤。')).toBeVisible()
    const restoredTools = within(restored).getByRole('button', { name: /工具调用已中断/ })
    expect(restoredTools).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(restoredTools)
    expect(within(restored).getByText('青年孤独研究')).toBeVisible()
  })

  it('shows the runtime mode reported by the real Agent stream', async () => {
    const conversation = conversationFixture({ answer: 'SFT 模型已经返回回答。' })
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = urlFor(input)
      if (url.pathname === '/api/agent/turns') return streamResponse(conversation, 'sft')
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    renderPage()

    const region = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    const textbox = within(region).getByRole('textbox', { name: '问社会学 Agent' })
    fireEvent.change(textbox, { target: { value: conversation.title } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)

    expect(await within(region).findByText('SFT 模型已经返回回答。')).toBeVisible()
    expect(within(region).queryByText('SFT 模型运行')).not.toBeInTheDocument()
    expect(within(region).queryByText('预览 Agent')).not.toBeInTheDocument()
  })
})
