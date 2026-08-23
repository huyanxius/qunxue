import { useCallback, useEffect, useState } from 'react'

import {
  acceptM5Proposal,
  confirmM5ResearchDocument,
  exportM5ResearchDocument,
  loadM5ResearchDelivery,
  rejectM5Proposal,
  restoreM5ResearchDocument,
  serializeM5ResearchExport,
  type M5ExportFormat,
  type M5ResearchDeliveryState,
} from '../../api/m5ResearchDelivery'
import { streamAgentTurn, type AgentEvent } from '../../modules/research-agent'
import { M5ResearchDeliveryPanel } from './M5ResearchDeliveryPanel'
import type { M5GenerationAttempt } from './M5GenerationState'

type Props = {
  taskId: string
  theoryPlanId: string
  conversationId: string | null
  saveState: 'saved' | 'saving' | 'unsaved'
  onChanged(): void
}

function requestKey() {
  return globalThis.crypto?.randomUUID?.() ?? `m5-${Date.now()}`
}

function download(filename: string, mediaType: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: mediaType }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export function M5ResearchDeliveryController({
  taskId,
  theoryPlanId,
  conversationId,
  saveState,
  onChanged,
}: Props) {
  const [state, setState] = useState<M5ResearchDeliveryState | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    const next = await loadM5ResearchDelivery({
      taskId,
      confirmedTheoryPlanId: theoryPlanId,
    })
    setState(next)
    setLoadError(null)
    return next
  }, [taskId, theoryPlanId])

  useEffect(() => {
    let active = true
    void refresh().catch((failure: unknown) => {
      if (active) setLoadError(failure instanceof Error ? failure.message : '研究交付状态暂时无法加载。')
    })
    return () => { active = false }
  }, [refresh])

  async function generate(attempt: M5GenerationAttempt) {
    let failed: string | null = null
    await streamAgentTurn({
      conversation_id: conversationId,
      message: attempt.prompt,
      workspace: 'research',
      task_id: taskId,
      theory_plan_id: theoryPlanId,
      idempotencyKey: attempt.idempotencyKey,
    }, (event: AgentEvent) => {
      if (event.type === 'turn_failed' || event.type === 'turn_interrupted') failed = event.message
    })
    if (failed) throw new Error(failed)
    const next = await refresh()
    if (!next.proposals.some((proposal) => proposal.status === 'pending') && !next.document) {
      throw new Error('Agent 本轮没有生成可审批草稿，请重试原请求。')
    }
    onChanged()
  }

  async function acceptProposal(proposalId: string) {
    await acceptM5Proposal({
      proposalId,
      expectedDocumentVersion: state?.document?.version ?? null,
      idempotencyKey: requestKey(),
    })
    await refresh()
    onChanged()
  }

  async function rejectProposal(proposalId: string, reason: string) {
    await rejectM5Proposal({ proposalId, reason, idempotencyKey: requestKey() })
    await refresh()
    onChanged()
  }

  async function restoreVersion(version: number) {
    if (!state?.document) throw new Error('当前没有可恢复的正式文档。')
    await restoreM5ResearchDocument({
      documentId: state.document.documentId,
      expectedVersion: state.document.version,
      sourceVersion: version,
      reason: `用户从交付面板恢复第 ${version} 版`,
      idempotencyKey: requestKey(),
    })
    await refresh()
    onChanged()
  }

  async function confirm() {
    if (!state?.document) throw new Error('当前没有可确认的正式文档。')
    await confirmM5ResearchDocument({
      documentId: state.document.documentId,
      expectedVersion: state.document.version,
      idempotencyKey: requestKey(),
    })
    await refresh()
    onChanged()
  }

  async function exportPackage(format: M5ExportFormat) {
    if (!state?.document) throw new Error('当前没有可导出的正式文档。')
    const result = await exportM5ResearchDocument({ documentId: state.document.documentId })
    const serialized = serializeM5ResearchExport(result, format)
    download(serialized.filename, serialized.mediaType, serialized.content)
  }

  if (loadError) {
    return (
      <section className="m5-delivery-stack" role="alert">
        <strong>研究交付状态暂时无法加载</strong>
        <p>{loadError}</p>
        <button type="button" className="m5-secondary-button" onClick={() => void refresh()}>重新加载</button>
      </section>
    )
  }
  if (!state) return <section className="m5-delivery-stack" role="status">正在恢复 M5 研究交付…</section>

  return (
    <M5ResearchDeliveryPanel
      state={state}
      theoryPlanLabel={`已确认方案 · ${theoryPlanId}`}
      saveState={saveState}
      createIdempotencyKey={requestKey}
      onGenerate={generate}
      onAcceptProposal={acceptProposal}
      onRejectProposal={rejectProposal}
      onRestoreVersion={restoreVersion}
      onConfirm={confirm}
      onExport={exportPackage}
    />
  )
}
