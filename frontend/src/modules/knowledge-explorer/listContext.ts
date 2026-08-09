import type { KnowledgeUrlState } from './urlState'
import { writeKnowledgeUrlState } from './urlState'

interface StorageAdapter {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

export function knowledgeListContextKey(state: KnowledgeUrlState) {
  return `qunxue:knowledge-scroll:${writeKnowledgeUrlState({ ...state, returnTo: undefined }).toString()}`
}

export function saveKnowledgeListScroll(state: KnowledgeUrlState, scrollY: number, storage: StorageAdapter = sessionStorage) {
  if (!Number.isFinite(scrollY) || scrollY < 0) return
  storage.setItem(knowledgeListContextKey(state), String(Math.round(scrollY)))
}

export function readKnowledgeListScroll(state: KnowledgeUrlState, storage: StorageAdapter = sessionStorage) {
  const value = storage.getItem(knowledgeListContextKey(state))
  if (value === null || value.trim() === '') return undefined
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined
}
