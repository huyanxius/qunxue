import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
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
    expect(screen.getByRole('switch', { name: '自动整理记忆' })).toHaveAttribute('aria-checked', 'true')
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
      return json({ items: [record] })
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
})
