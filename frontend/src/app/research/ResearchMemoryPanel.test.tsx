import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { Profiler } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ResearchMemoryPanel } from './ResearchMemoryPanel'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
function setup(preview = true, taskId: string | null = null) {
  render(<MemoryRouter initialEntries={['/research/materials?tab=memory&preview=memory']}><ResearchMemoryPanel taskId={taskId} projectName="研究项目" preview={preview} /></MemoryRouter>)
}
describe('ResearchMemoryPanel', () => {
  it('opens with a readable overview and reveals individual records on request', () => {
    setup()
    expect(screen.getByRole('region', { name: '记忆概览' })).toHaveTextContent('知识生产')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /查看记忆明细/ }))
    expect(screen.getByRole('table', { name: '个人记忆列表' })).toBeVisible()
  })
  it('previews creation, editing, history and deletion without network writes', async () => {
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher); setup()
    expect(screen.getByText('5 条记忆')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: '添加记忆' }))
    fireEvent.change(screen.getByLabelText('希望 Agent 记住什么？'), { target: { value: '核验原文。' } })
    fireEvent.click(screen.getByRole('button', { name: '保存记忆' }))
    expect(await screen.findByText('6 条记忆')).toBeVisible()
    let card = screen.getByRole('complementary', { name: '记忆详情' })
    fireEvent.click(within(card).getByRole('button', { name: '编辑' }))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '保留反例。' } })
    fireEvent.click(screen.getByRole('button', { name: '保存记忆' }))
    card = screen.getByRole('complementary', { name: '记忆详情' })
    fireEvent.click(within(card).getByRole('button', { name: /修改历史/ }))
    expect(within(card).getByText('核验原文。')).toBeVisible()
    fireEvent.click(within(card).getByRole('button', { name: '删除' }))
    fireEvent.click(within(card).getByRole('button', { name: '取消' }))
    expect(card).toBeVisible()
    fireEvent.click(within(card).getByRole('button', { name: '删除' }))
    fireEvent.click(within(card).getByRole('button', { name: '确认删除' }))
    expect(await screen.findByText('5 条记忆')).toBeVisible()
    expect(fetcher).not.toHaveBeenCalled()
  })
  it('separates project memory use from learning and exposes source quotes', () => {
    setup(true, 'project-1')
    expect(screen.getByText('4 条记忆')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: '记忆设置' }))
    fireEvent.click(screen.getByRole('switch', { name: '使用项目记忆' }))
    expect(screen.getByRole('switch', { name: '使用项目记忆' })).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByRole('switch', { name: '从对话中学习' })).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(screen.getByRole('button', { name: /查看记忆明细/ }))
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: '沉默' } })
    expect(screen.getAllByRole('button', { name: /^查看记忆/ })).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: /^查看记忆/ }))
    expect(screen.getByText('这里的沉默可能是在想怎么表达，也可能是不同意，先把前后文留下。')).toBeVisible()
  })
  it('sends scope and version to the API and preserves an edit on conflict', async () => {
    const record = { memory_id: 'memory-1', task_id: 'project-1', key: 'method', content: '核验原文。', origin: 'manual', version: 3, created_at: '2026-09-05T00:00:00Z', updated_at: '2026-09-05T00:00:00Z', source_quote: null, source_conversation_id: null, source_message_id: null }
    const requests: Request[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const req = input instanceof Request ? input : new Request(String(input), init); requests.push(req.clone())
      if (new URL(req.url).pathname.endsWith('/overview')) return json({ summary: '你希望核验原文。', memory_count: 1, scope_version: 0 })
      if (req.method === 'PATCH') return json({ detail: 'conflict' }, 409)
      if (new URL(req.url).pathname.endsWith('/settings')) return json({ task_id: 'project-1', version: 0, use_memory: true, learn_memory: true })
      return json({ items: [record], limits: { max_entries: 100, max_content_bytes: 2000 } })
    }))
    setup(false, 'project-1')
    expect(await screen.findByText('你希望核验原文。')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: /查看记忆明细/ }))
    fireEvent.click(await screen.findByRole('button', { name: '查看记忆：核验原文。' }))
    const card = screen.getByRole('complementary', { name: '记忆详情' })
    fireEvent.click(within(card).getByRole('button', { name: '编辑' }))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '保留反例。' } })
    fireEvent.click(screen.getByRole('button', { name: '保存记忆' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('已在别处更新')
    expect(screen.getByRole('textbox')).toHaveValue('保留反例。')
    expect(requests.filter(req => req.method === 'GET').every(req => new URL(req.url).searchParams.get('task_id') === 'project-1')).toBe(true)
    const patch = requests.find(req => req.method === 'PATCH')!
    expect(await patch.json()).toEqual({ content: '保留反例。', expected_version: 3 })
    expect(patch.headers.get('Idempotency-Key')).toBeTruthy()
  })

  it('counts UTF-8 bytes and prevents oversized Chinese memory in preview', async () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: '添加记忆' }))
    const input = screen.getByLabelText('希望 Agent 记住什么？')
    fireEvent.change(input, { target: { value: `${'中'.repeat(666)}ab` } })
    expect(screen.getByText(/2000 \/ 2000 字节/)).toBeVisible()
    expect(screen.getByRole('button', { name: '保存记忆' })).toBeEnabled()
    fireEvent.change(input, { target: { value: '中'.repeat(667) } })
    expect(screen.getByText(/2001 \/ 2000 字节/)).toBeVisible()
    expect(screen.getByRole('button', { name: '保存记忆' })).toBeDisabled()
  })

  it('respects server entry capacity while allowing edits at capacity', async () => {
    installMemoryServer({ entries: [record('原记忆')], maxEntries: 1 })
    setup(false)
    await screen.findByText('概览：原记忆')
    expect(screen.getByRole('button', { name: '添加记忆' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /查看记忆明细/ }))
    fireEvent.click(screen.getByRole('button', { name: '查看记忆：原记忆' }))
    fireEvent.click(screen.getByRole('button', { name: '编辑' }))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '已修改' } })
    expect(screen.getByRole('button', { name: '保存记忆' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: '保存记忆' }))
    expect(await screen.findByText('概览：已修改')).toBeVisible()
    expect(screen.getByRole('button', { name: '添加记忆' })).toBeDisabled()
  })

  it('keeps the overview when either setting changes without another overview request', async () => {
    const server = installMemoryServer({ entries: [record('原记忆')] })
    setup(false)
    await screen.findByText('概览：原记忆')
    fireEvent.click(screen.getByRole('button', { name: '记忆设置' }))
    fireEvent.click(screen.getByRole('switch', { name: '使用个人记忆' }))
    await waitFor(() => expect(screen.getByRole('switch', { name: '使用个人记忆' })).toHaveAttribute('aria-checked', 'false'))
    expect(screen.getByText('概览：原记忆')).toBeVisible()
    fireEvent.click(screen.getByRole('switch', { name: '从对话中学习' }))
    await waitFor(() => expect(screen.getByRole('switch', { name: '从对话中学习' })).toHaveAttribute('aria-checked', 'false'))
    expect(screen.getByText('概览：原记忆')).toBeVisible()
    expect(server.overviewVersions).toEqual([3])
  })

  it('uses a fresh server scope version after saving alongside background changes', async () => {
    const server = installMemoryServer({ entries: [record('原记忆')], nextWriteVersion: 37 })
    setup(false)
    await screen.findByText('概览：原记忆')
    fireEvent.click(screen.getByRole('button', { name: '添加记忆' }))
    fireEvent.change(screen.getByLabelText('希望 Agent 记住什么？'), { target: { value: '新增记忆' } })
    fireEvent.click(screen.getByRole('button', { name: '保存记忆' }))
    expect(await screen.findByText('概览：原记忆、新增记忆')).toBeVisible()
    expect(server.overviewVersions).toEqual([3, 37])
    fireEvent.click(screen.getByRole('button', { name: '删除' }))
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }))
    expect(await screen.findByText('概览：原记忆')).toBeVisible()
    expect(server.overviewVersions).toEqual([3, 37, 38])
  })

  it('does not restore an old overview when its response arrives after a save', async () => {
    let resolveOld!: (response: Response) => void
    const oldResponse = new Promise<Response>(resolve => { resolveOld = resolve })
    const server = installMemoryServer({ entries: [record('原记忆')], overview: version => version === 3 ? oldResponse : undefined })
    setup(false)
    await waitFor(() => expect(server.overviewVersions).toEqual([3]))
    fireEvent.click(screen.getByRole('button', { name: '添加记忆' }))
    fireEvent.change(screen.getByLabelText('希望 Agent 记住什么？'), { target: { value: '新增记忆' } })
    fireEvent.click(screen.getByRole('button', { name: '保存记忆' }))
    await screen.findByText('概览：原记忆、新增记忆')
    await act(async () => { resolveOld(json({ summary: '过期概览', scope_version: 3, memory_count: 1 })); await oldResponse })
    expect(screen.queryByText('过期概览')).not.toBeInTheDocument()
    expect(screen.getByText('概览：原记忆、新增记忆')).toBeVisible()
  })

  it('keeps the successful write visible and clears stale overview when refresh fails', async () => {
    installMemoryServer({ entries: [record('原记忆')], failRefresh: true })
    const staleSummaryAfterSave: boolean[] = []
    render(<Profiler id="memory" onRender={() => {
      if (screen.queryByText('记忆已保存。')) staleSummaryAfterSave.push(Boolean(screen.queryByText('概览：原记忆')))
    }}><MemoryRouter><ResearchMemoryPanel taskId={null} /></MemoryRouter></Profiler>)
    await screen.findByText('概览：原记忆')
    fireEvent.click(screen.getByRole('button', { name: '添加记忆' }))
    fireEvent.change(screen.getByLabelText('希望 Agent 记住什么？'), { target: { value: '新增记忆' } })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '保存记忆' })) })
    await screen.findByRole('alert')
    expect(staleSummaryAfterSave).not.toContain(true)
    expect(screen.queryByText('概览：原记忆')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '查看记忆：新增记忆' })).toBeVisible()
    expect(screen.queryByRole('button', { name: '保存记忆' })).not.toBeInTheDocument()
  })
})

function record(content: string) {
  return { memory_id: 'memory-1', task_id: null, key: 'note.1', content, origin: 'manual' as const, version: 1, created_at: '2026-09-05T00:00:00Z', updated_at: '2026-09-05T00:00:00Z', source_quote: null, source_conversation_id: null, source_message_id: null }
}
function installMemoryServer({ entries, maxEntries = 100, nextWriteVersion = 4, overview, failRefresh = false }: {
  entries: ReturnType<typeof record>[]; maxEntries?: number; nextWriteVersion?: number;
  overview?: (version: number) => Promise<Response> | undefined; failRefresh?: boolean
}) {
  let version = 3
  let settings = { task_id: null, version, use_memory: true, learn_memory: true }
  const overviewVersions: number[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const req = input instanceof Request ? input : new Request(String(input), init)
    const path = new URL(req.url).pathname
    if (path.endsWith('/overview')) {
      const body = await req.json() as { expected_version: number }
      overviewVersions.push(body.expected_version)
      return overview?.(body.expected_version) ?? json({ summary: `概览：${entries.map(item => item.content).join('、')}`, scope_version: version, memory_count: entries.length })
    }
    if (path.endsWith('/settings')) {
      if (req.method === 'PATCH') settings = { ...settings, ...await req.json(), version: ++version }
      return json({ ...settings, version })
    }
    if (req.method === 'POST' || req.method === 'PATCH') {
      const body = await req.json() as { content: string }
      version = nextWriteVersion
      const updated = { ...record(body.content), memory_id: req.method === 'POST' ? 'memory-new' : 'memory-1', version: 2 }
      entries = [...entries.filter(item => item.memory_id !== updated.memory_id), updated]
      return json(updated, req.method === 'POST' ? 201 : 200)
    }
    if (req.method === 'DELETE') {
      entries = entries.filter(item => !path.endsWith(item.memory_id)); version++
      return new Response(null, { status: 204 })
    }
    if (failRefresh && version !== 3) return json({ detail: 'unavailable' }, 503)
    return json({ items: entries, limits: { max_entries: maxEntries, max_content_bytes: 2000 } })
  }))
  return { overviewVersions }
}
