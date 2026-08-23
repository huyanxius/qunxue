import { ArrowClockwiseIcon, CircleNotchIcon, SparkleIcon } from '@phosphor-icons/react'
import { useRef, useState } from 'react'

import './m5-research-delivery.css'

export type M5GenerationAttempt = Readonly<{
  idempotencyKey: string
  prompt: string
}>

type Props = {
  theoryPlanLabel: string
  createIdempotencyKey: () => string
  onGenerate: (attempt: M5GenerationAttempt) => Promise<void>
}

const GENERATION_PROMPT = '基于已确认的理论方案生成一份可审阅的 M5 正式研究框架草稿；必须完整包含且仅包含研究问题、研究对象与田野、研究问题或假设、核心概念、理论视角、作用机制、方法论、样本与资料、分析步骤、研究伦理、研究局限、证据缺口 12 个规范章节。所有 Agent 内容只作为待接受建议，不直接覆盖正式文档。'

export function M5GenerationState({ theoryPlanLabel, createIdempotencyKey, onGenerate }: Props) {
  const [state, setState] = useState<'idle' | 'running' | 'failed' | 'succeeded'>('idle')
  const [error, setError] = useState<string | null>(null)
  const attemptRef = useRef<M5GenerationAttempt | null>(null)
  const lockRef = useRef(false)

  async function run(retry: boolean) {
    if (lockRef.current || state === 'succeeded') return
    const attempt = retry && attemptRef.current
      ? attemptRef.current
      : Object.freeze({ idempotencyKey: createIdempotencyKey(), prompt: GENERATION_PROMPT })
    attemptRef.current = attempt
    lockRef.current = true
    setState('running')
    setError(null)
    try {
      await onGenerate(attempt)
      setState('succeeded')
    } catch (failure: unknown) {
      setState('failed')
      setError(failure instanceof Error ? failure.message : '草稿生成失败，请重试原请求。')
    } finally {
      lockRef.current = false
    }
  }

  return (
    <section className="m5-generation" aria-labelledby="m5-generation-heading" aria-busy={state === 'running'}>
      <SparkleIcon className="m5-generation__mark" aria-hidden="true" weight="fill" />
      <span className="m5-panel-kicker">M5 · 正式研究框架</span>
      <h3 id="m5-generation-heading">从已确认方案开始</h3>
      <p>{theoryPlanLabel}</p>
      <small>Agent 会提出一份完整草稿。每项建议都需由你接受，正式文档才会改变。</small>

      {state === 'failed' ? (
        <button type="button" className="m5-secondary-button" onClick={() => void run(true)}>
          <ArrowClockwiseIcon aria-hidden="true" />
          重试原请求
        </button>
      ) : state !== 'succeeded' ? (
        <button type="button" className="m5-primary-button" disabled={state === 'running'} onClick={() => void run(false)}>
          {state === 'running' ? <CircleNotchIcon className="m5-spin" aria-hidden="true" /> : <SparkleIcon aria-hidden="true" />}
          {state === 'running' ? '正在生成草稿' : '生成研究框架草稿'}
        </button>
      ) : null}

      <p className={`m5-live-message ${error ? 'is-error' : ''}`} role="status" aria-live="polite">
        {error ?? (state === 'succeeded' ? '草稿已生成，等待你逐条审阅建议。' : '')}
      </p>
    </section>
  )
}
