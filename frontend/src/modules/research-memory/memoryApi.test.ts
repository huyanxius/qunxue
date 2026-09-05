import { afterEach, describe, expect, it, vi } from 'vitest'
import { saveMemory } from './memoryApi'

afterEach(() => vi.unstubAllGlobals())
describe('memory save errors', () => {
  it('exposes the business validation reason instead of a generic shortening suggestion', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ error: { code: 'validation_error', message: '此范围最多保存 100 条记忆，请删除不再需要的条目。', trace_id: 'test-trace' } }), { status: 422, headers: { 'Content-Type': 'application/json' } })))
    await expect(saveMemory(null, '新记忆')).rejects.toThrow('此范围最多保存 100 条记忆，请删除不再需要的条目。')
  })
  it('does not expose arbitrary validation objects', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ error: { code: 'validation_error', message: { input: 'private-value', msg: 'validation failed' }, trace_id: 'test-trace' } }), { status: 422, headers: { 'Content-Type': 'application/json' } })))
    await expect(saveMemory(null, '新记忆')).rejects.toThrow('这条记忆无法保存，请检查内容后重试。')
  })
  it('accepts a plain business detail from compatible API responses', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: '每条记忆最多 2000 字节。' }), { status: 422, headers: { 'Content-Type': 'application/json' } })))
    await expect(saveMemory(null, '新记忆')).rejects.toThrow('每条记忆最多 2000 字节。')
  })
})
