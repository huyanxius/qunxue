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
  if (input instanceof Request) return new URL(input.url)
  return typeof input === 'string' ? new URL(input, 'http://localhost') : new URL(input.toString())
}

function LocationProbe() {
  const location = useLocation()
  return <output aria-label="当前测试路径">{location.pathname}{location.search}</output>
}

describe('ResearchAgentConversationPage', () => {
  it('opens the composer material menu and returns focus when Escape closes it', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ items: [] })))
    renderPage()

    const agent = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    const addButton = within(agent).getByRole('button', { name: '添加研究材料' })
    fireEvent.click(addButton)

    const menu = within(agent).getByRole('menu', { name: '添加研究材料' })
    expect(within(menu).getByRole('menuitem', { name: '上传文件' })).toBeVisible()
    expect(within(menu).getByRole('menuitem', { name: '从研究材料添加' })).toBeVisible()
    expect(within(menu).getByRole('menuitem', { name: '查看材料库' })).toBeVisible()

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(within(agent).queryByRole('menu', { name: '添加研究材料' })).not.toBeInTheDocument()
    expect(addButton).toHaveFocus()
  })

  it('selects deep research from the composer mode menu and returns focus on Escape', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ items: [] })))
    renderPage()

    const agent = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    const modeButton = within(agent).getByRole('button', { name: '选择 Agent 模式' })
    expect(modeButton).toHaveTextContent('标准')

    fireEvent.click(modeButton)
    const menu = within(agent).getByRole('menu', { name: '选择 Agent 模式' })
    fireEvent.click(within(menu).getByRole('menuitemradio', { name: /深入研究/ }))

    expect(modeButton).toHaveTextContent('深入研究')
    const composer = within(agent).getByRole('textbox', { name: '问社会学 Agent' }).closest('.research-agent-composer')
    expect(composer).toHaveClass('is-awaiting-first-message')
    expect(within(agent).queryByRole('menu', { name: '选择 Agent 模式' })).not.toBeInTheDocument()

    fireEvent.click(modeButton)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(within(agent).queryByRole('menu', { name: '选择 Agent 模式' })).not.toBeInTheDocument()
    expect(modeButton).toHaveFocus()

    const input = within(agent).getByRole('textbox', { name: '问社会学 Agent' })
    fireEvent.change(input, { target: { value: '比较为何持续发生？' } })
    fireEvent.submit(input.closest('form') as HTMLFormElement)
    await waitFor(() => expect(composer).not.toHaveClass('is-awaiting-first-message'))
  })

  it('keeps a completed deep-research answer in the standard conversation flow', async () => {
    const answer = '## 研究结论\n\n这是一段需要正常换行展示的深入研究正文。'
    const completed = conversationFixture({
      id: 'conversation-deep-research-result',
      prompt: '请深入研究社区互助。',
      answer,
    })
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      if (urlFor(input).pathname !== '/api/agent/turns') return json({ items: [] })
      return new Response(eventStream([
        ['turn_started', { conversation_id: completed.conversation_id, run_id: 'run-deep', replayed: false, runtime_mode: 'base' }],
        ['research_result', { summary: answer, knowledge_count: 2, web_count: 1 }],
        ['assistant_delta', { delta: answer }],
        ['turn_completed', { conversation: completed, knowledge_release_id: 'release-agent' }],
      ]), { headers: { 'Content-Type': 'text/event-stream' } })
    }))
    renderPage()

    const agent = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    fireEvent.click(within(agent).getByRole('button', { name: '选择 Agent 模式' }))
    fireEvent.click(within(agent).getByRole('menuitemradio', { name: /深入研究/ }))
    const input = within(agent).getByRole('textbox', { name: '问社会学 Agent' })
    fireEvent.change(input, { target: { value: completed.turns[0].user.content } })
    fireEvent.submit(input.closest('form') as HTMLFormElement)

    const resultCard = await within(agent).findByRole('region', { name: '研究结论' })
    expect(within(resultCard).getByRole('heading', { name: '已经整理好一份带证据的结论' })).toBeVisible()
    expect(within(resultCard).queryByText('这是一段需要正常换行展示的深入研究正文。')).not.toBeInTheDocument()
    expect(within(agent).getByRole('heading', { name: '研究结论' })).toBeVisible()
    expect(within(agent).getByText('这是一段需要正常换行展示的深入研究正文。')).toBeVisible()
  })

  it('shows segmented deep-research progress before the streaming answer', async () => {
    const stream = deferredStream([
      ['turn_started', { conversation_id: 'conversation-progress', run_id: 'run-progress', replayed: false, runtime_mode: 'base' }],
      ['research_step', { step: '检索知识库与个人材料', status: 'running' }],
      ['assistant_delta', { delta: '正在形成最终回答。' }],
    ])
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      if (urlFor(input).pathname === '/api/agent/turns') return stream.response
      return json({ items: [] })
    }))
    renderPage()

    const agent = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    fireEvent.click(within(agent).getByRole('button', { name: '选择 Agent 模式' }))
    fireEvent.click(within(agent).getByRole('menuitemradio', { name: /深入研究/ }))
    const input = within(agent).getByRole('textbox', { name: '问社会学 Agent' })
    fireEvent.change(input, { target: { value: '研究社区互助的变化。' } })
    fireEvent.submit(input.closest('form') as HTMLFormElement)

    const progress = await within(agent).findByRole('region', { name: '研究进度' })
    const answer = await within(agent).findByText('正在形成最终回答。')
    expect(progress.compareDocumentPosition(answer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(within(progress).getByText('拆解研究问题')).toBeVisible()
    expect(within(progress).getByText('检索知识库与个人材料')).toBeVisible()
  })

  it('sends the enabled web-search choice with the next question', async () => {
    const completed = conversationFixture({
      id: 'conversation-web-search',
      prompt: '查找近期青年就业政策。',
      answer: '我会核对最新网页来源。',
    })
    const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = urlFor(input)
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      if (url.pathname === '/api/agent/turns' && init?.method === 'POST') return streamResponse(completed)
      return json({}, 404)
    })
    vi.stubGlobal('fetch', fetch)
    renderPage()

    const agent = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    const webSearchButton = within(agent).getByRole('button', { name: '联网搜索' })
    expect(webSearchButton).toHaveAttribute('aria-pressed', 'true')
    expect(webSearchButton).toHaveTextContent('联网已开启')
    fireEvent.change(within(agent).getByRole('textbox', { name: '问社会学 Agent' }), {
      target: { value: '查找近期青年就业政策。' },
    })
    fireEvent.submit(within(agent).getByRole('textbox', { name: '问社会学 Agent' }).closest('form') as HTMLFormElement)

    await waitFor(() => expect(fetch.mock.calls.some(([input]) => urlFor(input).pathname === '/api/agent/turns')).toBe(true))
    const turnCall = fetch.mock.calls.find(([input]) => urlFor(input).pathname === '/api/agent/turns')
    expect(JSON.parse(String(turnCall?.[1]?.body))).toMatchObject({ web_search: true })
  })

  it('starts a new conversation from the history rail and keeps one panel toggle in the header', async () => {
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
    const historyRail = screen.getByRole('region', { name: 'Agent 对话记录' })
    expect(historyRail).toBeVisible()
    expect(within(historyRail).getByRole('button', { name: '开始新对话' })).toBeVisible()
    expect(screen.queryByRole('button', { name: '打开研究记录' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '研究面板' })).toBeVisible()
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

  it('offers one task-scoped research-material entry only inside a bound research workspace', async () => {
    const conversation = conversationFixture({ id: 'conversation-material-entry' })
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = urlFor(input)
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      if (url.pathname === '/api/research-tasks/task-1/materials') return json({ task_id: 'task-1', items: [] })
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    })
    vi.stubGlobal('fetch', fetchMock)

    const embedded = render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <ResearchAgentConversationPage
          embedded
          userId="user-agent"
          conversationId={conversation.conversation_id}
          workspace="research"
          taskId="task-1"
        />
      </MemoryRouter>,
    )

    const agent = await screen.findByRole('complementary', { name: '研究 Agent 对话栏' })
    const entry = within(agent).getByRole('button', { name: '研究材料' })
    expect(within(agent).getAllByRole('button', { name: '研究材料' })).toHaveLength(1)
    fireEvent.click(entry)
    expect(await screen.findByRole('dialog', { name: '研究材料' })).toBeVisible()
    embedded.unmount()

    renderPage()
    const standalone = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    expect(within(standalone).queryByRole('button', { name: '研究材料' })).not.toBeInTheDocument()
  })

  it('attaches ready task materials to the next Agent turn and clears them after success', async () => {
    const conversation = conversationFixture({ id: 'conversation-material-attachment' })
    const completed = conversationFixture({
      id: conversation.conversation_id,
      prompt: '只根据这份访谈总结。',
      answer: '访谈显示照护安排发生了变化。',
    })
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = urlFor(input)
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      if (url.pathname === '/api/research-tasks/task-1/materials') return json({
        task_id: 'task-1',
        items: [{
          material_id: 'material-1', task_id: 'task-1', filename: '社区访谈.docx',
          media_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          size_bytes: 2048, status: 'ready', version: 1, parse_version: 1,
          segment_count: 3, updated_at: '2026-09-04T00:00:00Z', error_code: null,
        }],
      })
      if (url.pathname === '/api/agent/turns' && init?.method === 'POST') return streamResponse(completed)
      return json({}, 404)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <ResearchAgentConversationPage
          embedded
          userId="user-agent"
          conversationId={conversation.conversation_id}
          workspace="research"
          taskId="task-1"
        />
      </MemoryRouter>,
    )

    const agent = await screen.findByRole('complementary', { name: '研究 Agent 对话栏' })
    fireEvent.click(within(agent).getByRole('button', { name: '添加研究材料' }))
    fireEvent.click(within(agent).getByRole('menuitem', { name: '从研究材料添加' }))
    const picker = await screen.findByRole('dialog', { name: '选择本轮材料' })
    fireEvent.click(within(picker).getByRole('checkbox', { name: /社区访谈\.docx/ }))
    fireEvent.click(within(picker).getByRole('button', { name: '完成' }))

    expect(within(agent).getByText('社区访谈.docx')).toBeVisible()
    const input = within(agent).getByRole('textbox', { name: '问社会学 Agent' })
    fireEvent.change(input, { target: { value: '只根据这份访谈总结。' } })
    fireEvent.submit(input.closest('form') as HTMLFormElement)

    await waitFor(() => expect(fetchMock.mock.calls.some(([request]) => urlFor(request).pathname === '/api/agent/turns')).toBe(true))
    const turnCall = fetchMock.mock.calls.find(([request]) => urlFor(request).pathname === '/api/agent/turns')
    expect(JSON.parse(String(turnCall?.[1]?.body))).toMatchObject({ material_ids: ['material-1'] })
    await within(agent).findByText('访谈显示照护安排发生了变化。')
    expect(within(agent).queryByText('社区访谈.docx')).not.toBeInTheDocument()
  })

  it('uploads from the composer and refreshes the attachment until it is searchable', async () => {
    const conversation = conversationFixture({ id: 'conversation-direct-upload' })
    const processing = {
      material_id: 'material-upload', task_id: 'task-1', filename: '田野笔记.txt',
      media_type: 'text/plain', size_bytes: 12, status: 'processing', version: 1,
      parse_version: null, segment_count: 0, updated_at: '2026-09-04T00:00:00Z',
      error_code: null, ingestion_status: 'queued', ingestion_job_id: 'job-1',
      unavailable_reason: null,
    }
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = urlFor(input)
      const method = input instanceof Request ? input.method : init?.method ?? 'GET'
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      if (url.pathname === '/api/research-tasks/task-1/materials' && method === 'POST') return json(processing, 201)
      if (url.pathname === '/api/research-tasks/task-1/materials') return json({
        task_id: 'task-1', items: [{ ...processing, status: 'ready', ingestion_status: 'ready', parse_version: 1 }],
      })
      return json({}, 404)
    })
    vi.stubGlobal('fetch', fetchMock)

    const rendered = render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <ResearchAgentConversationPage
          embedded
          userId="user-agent"
          conversationId={conversation.conversation_id}
          workspace="research"
          taskId="task-1"
        />
      </MemoryRouter>,
    )
    const agent = await screen.findByRole('complementary', { name: '研究 Agent 对话栏' })
    fireEvent.click(within(agent).getByRole('button', { name: '添加研究材料' }))
    fireEvent.click(within(agent).getByRole('menuitem', { name: '上传文件' }))
    const fileInput = rendered.container.querySelector<HTMLInputElement>('.research-agent-composer__file-input')
    expect(fileInput).not.toBeNull()
    fireEvent.change(fileInput!, {
      target: { files: [new File(['field notes'], '田野笔记.txt', { type: 'text/plain' })] },
    })

    expect(await within(agent).findByText('等待解析')).toBeVisible()
    await waitFor(() => expect(within(agent).queryByText('等待解析')).not.toBeInTheDocument(), { timeout: 2500 })
    const uploadCall = fetchMock.mock.calls.find(([input, init]) => {
      const method = input instanceof Request ? input.method : init?.method
      return urlFor(input).pathname === '/api/research-tasks/task-1/materials' && method === 'POST'
    })
    const uploadRequest = uploadCall?.[0] instanceof Request
      ? uploadCall[0]
      : new Request(String(uploadCall?.[0]), uploadCall?.[1])
    const uploadBody = await uploadRequest.clone().text()
    expect(uploadBody).toContain('name="defer_processing"')
    expect(uploadBody).toMatch(/name="defer_processing"\r?\n\r?\ntrue/)
  })

  it('distinguishes a personal material citation and opens its exact source locator', async () => {
    const citation = {
      citation_id: 'citation-material-1',
      label: '社区访谈.docx',
      kind: 'research_material',
      excerpt: '受访者描述了工作时间的变化。',
      source_id: 'material-segment:segment-1',
      material_id: 'material-1',
      parse_id: 'parse-1',
      segment_id: 'segment-1',
      locator: { page: 4, paragraph: 12 },
    } as AgentCitation & {
      material_id: string
      parse_id: string
      segment_id: string
      locator: { page: number; paragraph: number }
    }
    const conversation = conversationFixture({ id: 'conversation-material-citation', citations: [citation] })
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = urlFor(input)
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      if (url.pathname === '/api/research-tasks/task-1/materials') return json({ task_id: 'task-1', items: [{
        material_id: 'material-1', task_id: 'task-1', filename: '社区访谈.docx',
        media_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        size_bytes: 2048, status: 'ready', version: 1, parse_version: 1,
        segment_count: 1, updated_at: '2026-08-29T00:00:00Z', error_code: null,
      }] })
      if (url.pathname === '/api/research-tasks/task-1/materials/material-1') return json({
        material_id: 'material-1', task_id: 'task-1', filename: '社区访谈.docx',
        media_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        size_bytes: 2048, status: 'ready', version: 1, parse_version: 1,
        segment_count: 1, updated_at: '2026-08-29T00:00:00Z', error_code: null,
        segments: [{ segment_id: 'segment-1', material_id: 'material-1', parse_id: 'parse-1', ordinal: 0, kind: 'paragraph', text: citation.excerpt, locator: citation.locator }],
      })
      return json({}, 404)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <ResearchAgentConversationPage
          embedded
          userId="user-agent"
          conversationId={conversation.conversation_id}
          workspace="research"
          taskId="task-1"
        />
      </MemoryRouter>,
    )

    const agent = await screen.findByRole('complementary', { name: '研究 Agent 对话栏' })
    expect(within(agent).getByText('研究材料')).toBeVisible()
    fireEvent.click(within(agent).getByRole('button', { name: '查看证据：社区访谈.docx' }))
    const sources = await screen.findByRole('region', { name: '来源' })
    fireEvent.click(within(sources).getByRole('button', { name: /社区访谈\.docx/ }))
    const basis = await screen.findByRole('region', { name: '依据' })
    expect(within(basis).getByText('第 4 页 · 第 12 段')).toBeVisible()
    fireEvent.click(within(basis).getByRole('button', { name: '打开原文位置' }))
    const materials = await screen.findByRole('dialog', { name: '研究材料' })
    expect(await within(materials).findByText('受访者描述了工作时间的变化。')).toBeVisible()
    await waitFor(() => {
      const detailRequest = fetchMock.mock.calls.find(([input]) => {
        const url = urlFor(input)
        return url.pathname === '/api/research-tasks/task-1/materials/material-1'
      })
      expect(detailRequest).toBeDefined()
      expect(urlFor(detailRequest?.[0] as RequestInfo | URL).searchParams.get('parse_id')).toBe('parse-1')
    })
  })

  it('opens a selected web citation at its original page', async () => {
    const citation: AgentCitation = {
      citation_id: 'web:https://www.gov.cn/zhengce/example.html',
      label: '高校毕业生就业政策',
      kind: 'source',
      excerpt: '政策正文说明了高校毕业生就业支持措施。',
      source_id: 'https://www.gov.cn/zhengce/example.html',
      source_kind: 'web',
    }
    const conversation = conversationFixture({ id: 'conversation-web-citation', citations: [citation] })
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = urlFor(input)
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      return json({}, 404)
    }))
    renderPage('user-agent', `/agent?conversation_id=${conversation.conversation_id}`)

    const agent = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    expect(within(agent).getByRole('status', { name: '本轮证据来源' })).toHaveTextContent('公开网页')
    fireEvent.click(within(agent).getByRole('button', { name: '查看证据：高校毕业生就业政策' }))
    const sources = await screen.findByRole('region', { name: '研究面板' })
    fireEvent.click(within(sources).getByRole('button', { name: /高校毕业生就业政策/ }))

    expect(await screen.findByRole('link', { name: '打开网页' })).toHaveAttribute(
      'href',
      'https://www.gov.cn/zhengce/example.html',
    )
  })

  it('makes mixed evidence visible when an answer cites both public knowledge and personal material', async () => {
    const citations = [
      { citation_id: 'citation-knowledge-mixed', label: '社区互助研究', kind: 'knowledge', knowledge_id: 'D1:C001', excerpt: '公共知识条目。' },
      { citation_id: 'citation-material-mixed', label: '社区访谈.docx', kind: 'research_material', material_id: 'material-1', parse_id: 'parse-1', segment_id: 'segment-1', locator: { page: 2, paragraph: 3 }, excerpt: '个人材料片段。' },
    ] as AgentCitation[]
    const conversation = conversationFixture({ id: 'conversation-mixed-evidence', citations })
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = urlFor(input)
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      return json({ task_id: 'task-1', items: [] })
    }))

    render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <ResearchAgentConversationPage embedded userId="user-agent" conversationId={conversation.conversation_id} workspace="research" taskId="task-1" />
      </MemoryRouter>,
    )

    const agent = await screen.findByRole('complementary', { name: '研究 Agent 对话栏' })
    expect(within(agent).getByRole('status', { name: '本轮证据来源' })).toHaveTextContent('本轮引用 · 群学知识库 1 · 你的研究材料 1')
  })

  it('keeps a deleted material citation as a tombstone without opening source text', async () => {
    const citation = {
      citation_id: 'citation-deleted-material-1',
      label: '已删除的访谈.docx',
      kind: 'research_material',
      excerpt: null,
      source_kind: 'personal_material',
      material_id: 'material-deleted-1',
      parse_id: 'parse-deleted-1',
      segment_id: 'segment-deleted-1',
      locator: { page: 2, paragraph: 3 },
      deleted: true,
    } as AgentCitation & {
      material_id: string
      parse_id: string
      segment_id: string
      locator: { page: number; paragraph: number }
      deleted: boolean
    }
    const conversation = conversationFixture({ id: 'conversation-deleted-material', citations: [citation] })
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = urlFor(input)
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      if (url.pathname === '/api/research-tasks/task-1/materials') return json({ task_id: 'task-1', items: [] })
      return json({}, 404)
    }))

    render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <ResearchAgentConversationPage
          embedded
          userId="user-agent"
          conversationId={conversation.conversation_id}
          workspace="research"
          taskId="task-1"
        />
      </MemoryRouter>,
    )

    const agent = await screen.findByRole('complementary', { name: '研究 Agent 对话栏' })
    fireEvent.click(within(agent).getByRole('button', { name: '查看证据：已删除的访谈.docx' }))
    const sources = await screen.findByRole('region', { name: '来源' })
    fireEvent.click(within(sources).getByRole('button', { name: /已删除的访谈.docx/ }))
    const basis = await screen.findByRole('region', { name: '依据' })
    expect(within(basis).getByText('这份研究材料已删除，原文不再可访问。')).toBeVisible()
    expect(within(basis).queryByRole('button', { name: '打开原文位置' })).toBeNull()
  })

  it('turns every visible citation for a material into a tombstone as soon as that material is deleted', async () => {
    const excerpt = '这段个人材料正文不能在删除后继续显示。'
    const leakedAnswer = `材料原文写道：${excerpt}`
    const citation: AgentCitation = {
      citation_id: 'citation-material-to-delete',
      label: '待删除访谈.docx',
      kind: 'research_material',
      excerpt,
      source_kind: 'personal_material',
      material_id: 'material-to-delete',
      parse_id: 'parse-to-delete',
      segment_id: 'segment-to-delete',
      locator: { page: 6, paragraph: 2 },
    }
    const conversation = conversationFixture({
      id: 'conversation-delete-material',
      answer: leakedAnswer,
      citations: [citation],
    })
    const material = {
      material_id: 'material-to-delete', task_id: 'task-1', filename: '待删除访谈.docx',
      media_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      size_bytes: 4096, status: 'ready', version: 1, parse_version: 1,
      segment_count: 1, updated_at: '2026-08-29T00:00:00Z', error_code: null,
    }
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = input instanceof Request ? input : new Request(String(input), init)
      const url = new URL(request.url)
      if (url.pathname === `/api/agent/conversations/${conversation.conversation_id}`) return json(conversation)
      if (url.pathname === '/api/research-tasks/task-1/materials' && request.method === 'GET') {
        return json({ task_id: 'task-1', items: [material] })
      }
      if (url.pathname === '/api/research-tasks/task-1/materials/material-to-delete' && request.method === 'DELETE') {
        return new Response(null, { status: 204 })
      }
      return json({}, 404)
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('confirm', vi.fn(() => true))

    render(
      <MemoryRouter initialEntries={['/research/task-1/match']}>
        <ResearchAgentConversationPage
          embedded
          userId="user-agent"
          conversationId={conversation.conversation_id}
          workspace="research"
          taskId="task-1"
        />
      </MemoryRouter>,
    )

    const agent = await screen.findByRole('complementary', { name: '研究 Agent 对话栏' })
    expect(within(agent).getByText(leakedAnswer)).toBeVisible()
    fireEvent.click(within(agent).getByRole('button', { name: '查看证据：待删除访谈.docx' }))
    const sources = await screen.findByRole('region', { name: '来源' })
    fireEvent.click(within(sources).getByRole('button', { name: /待删除访谈\.docx/ }))
    const basis = await screen.findByRole('region', { name: '依据' })
    expect(within(basis).getByText(excerpt)).toBeVisible()

    fireEvent.click(within(agent).getByRole('button', { name: '研究材料' }))
    const materials = await screen.findByRole('dialog', { name: '研究材料' })
    await within(materials).findByRole('button', { name: '查看材料：待删除访谈.docx' })
    fireEvent.click(within(materials).getByRole('button', { name: /^删除材料：/ }))
    expect(await within(materials).findByText('材料已删除，后续检索不会再使用它。')).toBeVisible()
    fireEvent.click(within(materials).getByRole('button', { name: '关闭研究材料' }))

    await waitFor(() => {
      expect(within(basis).getByText('这份研究材料已删除，原文不再可访问。')).toBeVisible()
      expect(within(basis).queryByText(excerpt)).not.toBeInTheDocument()
      expect(within(basis).queryByRole('button', { name: '打开原文位置' })).not.toBeInTheDocument()
      expect(within(agent).getByText('该回答引用的个人研究材料已删除，原回答内容已隐藏。')).toBeVisible()
      expect(within(agent).queryByText(leakedAnswer)).not.toBeInTheDocument()
    })
  })

  it('hides a live streaming answer as soon as one of its personal materials is deleted', async () => {
    const leakedAnswer = '流式回答直接复述了稍后被删除的个人材料。'
    const citation: AgentCitation = {
      citation_id: 'citation-streaming-material',
      label: '流式访谈.txt',
      kind: 'research_material',
      excerpt: '稍后被删除的个人材料',
      source_kind: 'personal_material',
      material_id: 'material-streaming',
      parse_id: 'parse-streaming',
      segment_id: 'segment-streaming',
      locator: { line_start: 12, line_end: 12 },
    }
    const material = {
      material_id: 'material-streaming', task_id: 'task-1', filename: '流式访谈.txt',
      media_type: 'text/plain', size_bytes: 1024, status: 'ready', version: 1,
      parse_version: 1, segment_count: 1, updated_at: '2026-08-29T00:00:00Z', error_code: null,
    }
    const liveStream = deferredStream([
      ['turn_started', { conversation_id: 'conversation-streaming-material', run_id: 'run-streaming-material', replayed: false, runtime_mode: 'base' }],
      ['agent_status', { status: 'answering' }],
      ['assistant_delta', { delta: leakedAnswer }],
      ['citation_added', citation],
    ])
    const completed = conversationFixture({
      id: 'conversation-streaming-material',
      prompt: '请依据我的访谈回答。',
      answer: `${leakedAnswer}后续流式正文也不能重新出现。`,
      citations: [citation],
    })
    let streamFinished = false
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = input instanceof Request ? input : new Request(String(input), init)
      const url = new URL(request.url)
      if (url.pathname === '/api/agent/turns') return liveStream.response
      if (url.pathname === '/api/research-tasks/task-1/materials' && request.method === 'GET') {
        return json({ task_id: 'task-1', items: [material] })
      }
      if (url.pathname === '/api/research-tasks/task-1/materials/material-streaming' && request.method === 'DELETE') {
        return new Response(null, { status: 204 })
      }
      return json({}, 404)
    }))
    vi.stubGlobal('confirm', vi.fn(() => true))

    try {
      render(
        <MemoryRouter initialEntries={['/research/task-1/match']}>
          <ResearchAgentConversationPage embedded userId="user-agent" workspace="research" taskId="task-1" />
        </MemoryRouter>,
      )

      const agent = await screen.findByRole('complementary', { name: '研究 Agent 对话栏' })
      const textbox = within(agent).getByRole('textbox', { name: '问社会学 Agent' })
      fireEvent.change(textbox, { target: { value: '请依据我的访谈回答。' } })
      fireEvent.submit(textbox.closest('form') as HTMLFormElement)
      expect(await within(agent).findByText(leakedAnswer)).toBeVisible()
      expect(await within(agent).findByRole('button', { name: '查看证据：流式访谈.txt' })).toBeVisible()

      fireEvent.click(within(agent).getByRole('button', { name: '研究材料' }))
      const materials = await screen.findByRole('dialog', { name: '研究材料' })
      await within(materials).findByRole('button', { name: '查看材料：流式访谈.txt' })
      fireEvent.click(within(materials).getByRole('button', { name: /^删除材料：/ }))
      expect(await within(materials).findByText('材料已删除，后续检索不会再使用它。')).toBeVisible()

      await waitFor(() => {
        expect(within(agent).getByText('该回答引用的个人研究材料已删除，原回答内容已隐藏。')).toBeVisible()
        expect(within(agent).queryByText(leakedAnswer)).not.toBeInTheDocument()
      })
      liveStream.finish([
        ['assistant_delta', { delta: '后续流式正文也不能重新出现。' }],
        ['turn_completed', { conversation: completed, knowledge_release_id: 'release-agent' }],
      ])
      streamFinished = true
      await waitFor(() => {
        expect(within(agent).getByText('该回答引用的个人研究材料已删除，原回答内容已隐藏。')).toBeVisible()
        expect(within(agent).queryByText(/后续流式正文也不能重新出现/)).not.toBeInTheDocument()
      })
    } finally {
      if (!streamFinished) liveStream.finish([['turn_interrupted', { code: 'interrupted', message: '本轮已停止。' }]])
    }
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

    expect(await within(region).findByRole('button', { name: '继续研究' })).toBeVisible()
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
    let sources = await screen.findByRole('region', { name: '研究面板' })
    fireEvent.click(within(sources).getByRole('button', { name: /社会资本与邻里互助/ }))

    let basis = await screen.findByRole('region', { name: '依据' })
    expect(within(basis).getByRole('link', { name: /打开知识条目/ })).toHaveAttribute(
      'href',
      '/knowledge/D1%3AC001?knowledge_release_id=release-turn-old&return_to=%2Fagent%3Fconversation_id%3Dconversation-citation-links%26knowledge_release_id%3Drelease-turn-old',
    )
    expect(within(basis).getByRole('link', { name: /在知识图谱中查看/ })).toHaveAttribute(
      'href',
      '/knowledge/graph?knowledge_release_id=release-turn-old&center=D1%3AC001&query=%E7%A4%BE%E4%BC%9A%E8%B5%84%E6%9C%AC%E4%B8%8E%E9%82%BB%E9%87%8C%E4%BA%92%E5%8A%A9',
    )

    fireEvent.click(citationButtons[1])
    sources = await screen.findByRole('region', { name: '研究面板' })
    fireEvent.click(within(sources).getByRole('button', { name: /社会资本与邻里互助/ }))
    basis = await screen.findByRole('region', { name: '依据' })
    expect(within(basis).getByRole('link', { name: /打开知识条目/ })).toHaveAttribute(
      'href',
      '/knowledge/D1%3AC001?knowledge_release_id=release-turn-new&return_to=%2Fagent%3Fconversation_id%3Dconversation-citation-links%26knowledge_release_id%3Drelease-turn-new',
    )

    fireEvent.click(citationButtons[2])
    sources = await screen.findByRole('region', { name: '研究面板' })
    fireEvent.click(within(sources).getByRole('button', { name: /社会资本与邻里互助/ }))
    basis = await screen.findByRole('region', { name: '依据' })
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

  it('automatically resumes a disconnected turn with the original idempotency key', async () => {
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

    expect(await within(region).findByText(conversation.turns[0].assistant.content)).toBeVisible()
    expect(within(region).queryByRole('alert')).not.toBeInTheDocument()
    expect(within(region).queryByRole('button', { name: '重试本轮' })).not.toBeInTheDocument()
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

  it('ignores a late stream after switching records from the history rail', async () => {
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

    const historyRail = screen.getByRole('region', { name: 'Agent 对话记录' })
    fireEvent.click(within(historyRail).getByRole('button', { name: new RegExp(saved.title) }))

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

    // 研究面板会同步列出同一次工具调用，所以正文这一段断言限定在对话内容里。
    const transcript = within(region).getByRole('log', { name: '对话内容' })
    const toolSummary = await within(transcript).findByRole('button', { name: /Agent 已完成工具调用/ })
    expect(toolSummary).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(toolSummary)
    expect(within(transcript).getByText('根据当前研究问题寻找相关概念、理论与已有研究参照')).toBeVisible()
    const disclosure = await within(transcript).findByRole('button', { name: '查看完整工具返回' })
    expect(within(transcript).queryByText(completeDetail)).not.toBeVisible()
    fireEvent.click(disclosure)
    expect(within(transcript).getByText(completeDetail)).toBeVisible()

    fireEvent.click(within(region).getAllByRole('button', { name: '查看活动' })[0])
    const panel = await screen.findByRole('region', { name: '研究面板' })
    fireEvent.click(within(panel).getByRole('button', { name: /社会资本条目/ }))

    const basis = await screen.findByRole('region', { name: '依据' })
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
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = urlFor(input).pathname
      if (path === '/api/agent/turns') return liveStream.response
      if (path === '/api/agent/runs/run-stop/stop') return new Response(null, { status: 204 })
      return json({ items: [] })
    })
    vi.stubGlobal('fetch', fetchMock)

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
    expect(await within(region).findByText('已经形成一段可保留的回答。')).toBeVisible()
    fireEvent.click(within(region).getByRole('button', { name: '停止生成' }))

    expect(await within(region).findByText('本轮已停止，已保留生成内容和 1 个已完成步骤。')).toBeVisible()
    expect(within(region).getByText('已经形成一段可保留的回答。')).toBeVisible()
    expect(within(region).getByRole('button', { name: '继续研究' })).toBeVisible()
    expect(fetchMock.mock.calls.some(([input]) => urlFor(input).pathname === '/api/agent/runs/run-stop/stop')).toBe(true)
    first.unmount()

    renderPage('user-stop')
    const restored = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    expect(within(restored).getByText('已经形成一段可保留的回答。')).toBeVisible()
    expect(within(restored).getByText('本轮已停止，已保留生成内容和 1 个已完成步骤。')).toBeVisible()
    const restoredTools = within(restored).getByRole('button', { name: /工具调用已中断/ })
    expect(restoredTools).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(restoredTools)
    // 研究面板此时也在右侧列出同一条检索结果，所以断言限定在对话正文里。
    expect(within(within(restored).getByRole('log', { name: '对话内容' })).getByText('青年孤独研究')).toBeVisible()
    expect(within(restored).getByRole('button', { name: '继续研究' })).toBeVisible()
  })

  it('stops the server run when the user leaves the Agent page', async () => {
    const liveStream = deferredStream([
      ['turn_started', { conversation_id: 'conversation-leave', run_id: 'run-leave', replayed: false, runtime_mode: 'base' }],
      ['assistant_delta', { delta: '尚未完成的研究内容。' }],
    ])
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = urlFor(input).pathname
      if (path === '/api/agent/turns') return liveStream.response
      if (path === '/api/agent/runs/run-leave/stop') return new Response(null, { status: 204 })
      return json({ items: [] })
    })
    vi.stubGlobal('fetch', fetchMock)

    const page = renderPage('user-leave')
    const region = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    fireEvent.change(within(region).getByRole('textbox', { name: '问社会学 Agent' }), { target: { value: '继续调查社区照护。' } })
    fireEvent.submit(within(region).getByRole('textbox', { name: '问社会学 Agent' }).closest('form') as HTMLFormElement)
    expect(await within(region).findByText('尚未完成的研究内容。')).toBeVisible()

    page.unmount()

    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => urlFor(input).pathname === '/api/agent/runs/run-leave/stop')).toBe(true))
  })

  it('dismisses deep research progress when the user stops the run', async () => {
    const runningStream = deferredStream([
      ['turn_started', { conversation_id: 'conversation-deep-stop', run_id: 'run-deep-stop', replayed: false, runtime_mode: 'base' }],
      ['tool_started', { tool: 'search_knowledge', call_id: 'tool-deep-search', input: { query: '青年孤独' }, detail: '正在检索知识库' }],
    ])
    let turnRequestCount = 0
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = urlFor(input)
      if (url.pathname === '/api/agent/conversations') return json({ items: [] })
      if (url.pathname === '/api/agent/turns') {
        turnRequestCount += 1
        if (turnRequestCount === 1) {
          return new Response(eventStream([
            ['turn_started', { conversation_id: 'conversation-deep-stop', run_id: 'run-deep-stop', replayed: false, runtime_mode: 'base' }],
            ['research_plan', { title: '研究青年孤独', steps: ['检索知识库', '核对证据'] }],
            ['research_waiting', {
              run_id: 'run-deep-stop',
              state: 'awaiting_plan_confirmation',
              title: '研究青年孤独',
              steps: ['检索知识库', '核对证据'],
              prompt: '研究青年孤独。',
            }],
          ]), { headers: { 'Content-Type': 'text/event-stream' } })
        }
        return runningStream.response
      }
      if (url.pathname === '/api/agent/runs/run-deep-stop/stop') {
        return new Response(null, { status: 204 })
      }
      return json({}, 404)
    }))
    renderPage('user-deep-stop')

    const region = await screen.findByRole('region', { name: '社会学 Agent 对话' })
    fireEvent.click(within(region).getByRole('button', { name: '选择 Agent 模式' }))
    fireEvent.click(within(region).getByRole('menuitemradio', { name: /深入研究/ }))
    const textbox = within(region).getByRole('textbox', { name: '问社会学 Agent' })
    fireEvent.change(textbox, { target: { value: '研究青年孤独。' } })
    fireEvent.submit(textbox.closest('form') as HTMLFormElement)

    const plan = await within(region).findByRole('region', { name: '研究计划' })
    fireEvent.click(within(plan).getByRole('button', { name: '开始深入研究' }))
    expect(await within(region).findByRole('region', { name: '研究进度' })).toBeVisible()

    fireEvent.click(within(region).getByRole('button', { name: '停止生成' }))

    await waitFor(() => {
      expect(within(region).queryByRole('region', { name: '研究进度' })).not.toBeInTheDocument()
    })
    expect(within(region).queryByText(/已运行/)).not.toBeInTheDocument()
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
