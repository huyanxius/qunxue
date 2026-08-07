import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'

import {
  confirmEditedPhenomenonViaApi,
  restorePhenomenonViaApi,
  startPhenomenonViaApi,
} from './researchTaskApi'
import type { PhenomenonSnapshot } from './researchTaskModel'
import './workspace.css'

export function NewResearchPage({ onStarted }: { readonly onStarted: (taskId: string) => void }) {
  const [phenomenon, setPhenomenon] = useState('')
  const start = useMutation({
    mutationFn: startPhenomenonViaApi,
    onSuccess: (result) => onStarted(result.taskId),
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    start.mutate(phenomenon.trim())
  }

  return (
    <form className="phenomenon-form" onSubmit={submit}>
      <label htmlFor="direct-phenomenon">你观察到的现象</label>
      <textarea
        id="direct-phenomenon"
        value={phenomenon}
        onChange={(event) => setPhenomenon(event.target.value)}
        placeholder="例如：同一社区中的互助为何逐渐减少？"
        required
        rows={6}
      />
      <p className="page-placeholder">
        系统会调用演示 AI 生成一条可编辑候选；候选不是研究结论。
      </p>
      <button type="submit" disabled={start.isPending || !phenomenon.trim()}>
        {start.isPending ? '正在生成演示候选…' : '生成可编辑候选'}
      </button>
      {start.isError ? <p role="alert">暂时无法生成候选，输入内容仍未丢失。</p> : null}
    </form>
  )
}

export function PhenomenonWorkspace({ taskId }: { readonly taskId: string }) {
  const restored = useQuery({
    queryKey: ['phenomenon', taskId],
    queryFn: () => restorePhenomenonViaApi(taskId),
    retry: false,
  })
  const [phenomenon, setPhenomenon] = useState('')
  const [researchIntent, setResearchIntent] = useState('')
  const [context, setContext] = useState('')
  const [confirmed, setConfirmed] = useState<PhenomenonSnapshot | null>(null)

  useEffect(() => {
    if (!restored.data) return
    setPhenomenon(restored.data.candidate.phenomenon)
    setResearchIntent(restored.data.candidate.researchIntent ?? '')
    setContext(restored.data.candidate.context ?? '')
    setConfirmed(restored.data.snapshot)
  }, [restored.data])

  const confirmation = useMutation({
    mutationFn: () => confirmEditedPhenomenonViaApi(restored.data!.candidate, {
      phenomenon,
      researchIntent,
      context,
    }),
    onSuccess: setConfirmed,
  })

  if (restored.isPending) return <p role="status">正在恢复现象候选…</p>
  if (restored.isError || !restored.data) {
    return <p role="alert">暂时无法恢复这条现象候选。</p>
  }

  const { candidate } = restored.data
  if (confirmed) {
    return (
      <section className="confirmed-phenomenon">
        <p className="eyebrow">现象已经确认并保存</p>
        <h2>{confirmed.phenomenon}</h2>
        <p>刷新页面后仍会从后端快照恢复。</p>
        <p className="model-badge">{candidate.modelLabel}</p>
        {candidate.evidence.map((item) => (
          <p key={item.evidenceRefId}>
            <strong>{item.sourceDescription ?? item.evidenceRefId}</strong>
            {' · '}{item.useBoundary}
          </p>
        ))}
        <a className="text-link" href="/my">返回我的研究</a>
      </section>
    )
  }

  return (
    <form
      className="phenomenon-form"
      onSubmit={(event) => {
        event.preventDefault()
        confirmation.mutate()
      }}
    >
      <p className="model-badge">{candidate.modelLabel}</p>
      <label htmlFor="candidate-phenomenon">现象表述</label>
      <textarea
        id="candidate-phenomenon"
        rows={5}
        value={phenomenon}
        onChange={(event) => setPhenomenon(event.target.value)}
        required
      />
      <label htmlFor="research-intent">研究意图（可选）</label>
      <textarea
        id="research-intent"
        rows={3}
        value={researchIntent}
        onChange={(event) => setResearchIntent(event.target.value)}
      />
      <label htmlFor="phenomenon-context">背景（可选）</label>
      <textarea
        id="phenomenon-context"
        rows={3}
        value={context}
        onChange={(event) => setContext(event.target.value)}
      />
      <section className="evidence-card" aria-label="证据来源">
        <h2>输入证据</h2>
        {candidate.evidence.map((item) => (
          <article key={item.evidenceRefId}>
            <strong>{item.sourceDescription ?? item.evidenceRefId}</strong>
            <p>{item.excerpt}</p>
            <small>{item.useBoundary}</small>
          </article>
        ))}
      </section>
      <button type="submit" disabled={confirmation.isPending || !phenomenon.trim()}>
        {confirmation.isPending ? '正在确认…' : '确认这个现象'}
      </button>
      {confirmation.isError ? <p role="alert">确认失败，修改内容仍保留在页面中。</p> : null}
    </form>
  )
}
