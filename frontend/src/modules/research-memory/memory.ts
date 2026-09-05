import * as api from './memoryApi'
import type { ResearchMemory, ResearchMemorySettings } from './memoryModel'

export const loadMemories = (taskId: string | null, signal?: AbortSignal) => api.loadMemories(taskId, signal)
export const saveMemory = (taskId: string | null, content: string, existing?: ResearchMemory) => api.saveMemory(taskId, content, existing)
export const removeMemory = (memory: ResearchMemory) => api.removeMemory(memory)
export const saveMemorySettings = (settings: ResearchMemorySettings, field: 'use_memory' | 'learn_memory', value: boolean) => api.saveMemorySettings(settings, field, value)
export const loadMemoryHistory = (memoryId: string) => api.loadMemoryHistory(memoryId)

export const loadMemoryOverview = (taskId: string | null, version: number, signal?: AbortSignal) => api.loadMemoryOverview(taskId, version, signal)
