import { apiClient } from '../../api/client'
import { summarizeMemory, createMemory, deleteMemory, getMemorySettings, listMemories, listMemoryRevisions, updateMemory, updateMemorySettings } from '../../api/generated'

import type { ResearchMemory, ResearchMemorySettings } from './memoryModel'

function failure(status?: number) {
  return new Error(status === 409 ? '这条记录已在别处更新，请刷新后再试。' : status === 422 ? '这条记忆无法保存，请缩短内容或检查是否包含访问凭据。' : '记忆暂时无法保存或读取，请稍后重试。')
}
const headers = () => ({ 'Idempotency-Key': crypto.randomUUID() })
const query = (taskId: string | null) => taskId ? { task_id: taskId } : undefined

export async function loadMemories(taskId: string | null, signal?: AbortSignal): Promise<{ items: ResearchMemory[]; settings: ResearchMemorySettings }> {
  const [list, settings] = await Promise.all([
    listMemories({ client: apiClient, query: query(taskId), signal }),
    getMemorySettings({ client: apiClient, query: query(taskId), signal }),
  ])
  if (!list.data || !settings.data) throw failure(list.response?.status !== 200 ? list.response?.status : settings.response?.status)
  return { items: list.data.items, settings: settings.data }
}
export async function saveMemory(taskId: string | null, content: string, existing?: ResearchMemory): Promise<ResearchMemory> {
  const result = existing
    ? await updateMemory({ client: apiClient, headers: headers(), path: { memory_id: existing.memory_id }, body: { content, expected_version: existing.version } })
    : await createMemory({ client: apiClient, headers: headers(), body: { task_id: taskId, key: `note.${crypto.randomUUID()}`, content } })
  if (!result.data) throw failure(result.response?.status)
  return result.data
}
export async function removeMemory(memory: ResearchMemory) {
  const result = await deleteMemory({ client: apiClient, headers: headers(), path: { memory_id: memory.memory_id }, query: { expected_version: memory.version } })
  if (!result.response?.ok) throw failure(result.response?.status)
}
export async function saveMemorySettings(settings: ResearchMemorySettings, field: 'use_memory' | 'learn_memory', value: boolean): Promise<ResearchMemorySettings> {
  const result = await updateMemorySettings({ client: apiClient, query: query(settings.task_id), headers: headers(), body: { expected_version: settings.version, use_memory: settings.use_memory, learn_memory: settings.learn_memory, [field]: value } })
  if (!result.data) throw failure(result.response?.status)
  return result.data
}
export async function loadMemoryHistory(memoryId: string): Promise<ResearchMemory[]> {
  const result = await listMemoryRevisions({ client: apiClient, path: { memory_id: memoryId } })
  if (!result.data) throw failure(result.response?.status)
  return result.data.items
}

export async function loadMemoryOverview(taskId: string | null, version: number, signal?: AbortSignal): Promise<string> {
  const result = await summarizeMemory({ client: apiClient, body: { task_id: taskId, expected_version: version }, signal })
  if (!result.data) {
    const status = result.response?.status
    throw new Error(status === 409 ? '记忆已更新，请刷新记录后重新整理。' : status === 429 ? '正在整理记忆，请稍后重试。' : '概览暂未生成，你仍可查看和编辑记忆明细。')
  }
  return result.data.summary
}
