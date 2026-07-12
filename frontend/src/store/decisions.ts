// 编码裁决的全局状态:工作台写入,报告页读取。localStorage 持久化,刷新不丢。

import { useSyncExternalStore } from 'react'
import type { Decision } from '../data/demo'

const STORAGE_KEY = 'qunxue.decisions.v1'

type DecisionMap = Record<number, Decision>

let state: DecisionMap = load()
const listeners = new Set<() => void>()

function load(): DecisionMap {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as DecisionMap) : {}
  } catch {
    return {}
  }
}

function emit() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  listeners.forEach((fn) => fn())
}

export function setDecision(segmentId: number, decision: Decision) {
  state = { ...state, [segmentId]: decision }
  emit()
}

export function clearDecisions() {
  state = {}
  localStorage.removeItem(STORAGE_KEY)
  listeners.forEach((fn) => fn())
}

export function useDecisions(): DecisionMap {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    () => state,
  )
}

// 终裁标签:采纳=AI 标签;修改=新标签;驳回=不计入(该段无有效编码对)。
export function finalLabel(aiLabel: string, d: Decision | undefined): string | null {
  if (!d) return null
  if (d.kind === 'accept') return aiLabel
  if (d.kind === 'revise') return d.newLabel
  return null
}
