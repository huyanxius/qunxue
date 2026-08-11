import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  confirmFrameworkViaApi,
  createFrameworkViaApi,
  resolveFrameworkAuditViaApi,
  restoreFrameworkViaApi,
  reviewFrameworkViaApi,
  saveFrameworkViaApi,
} from './frameworkApi'
import {
  ResearchFrameworkWorkspace,
  type FrameworkResolution,
  type ResearchFrameworkView,
} from './ResearchFrameworkWorkspace'


type CreationContext = {
  taskVersion: number
  theoryPlanId: string
  theoryPlanVersion: number
  phenomenon: string
  context: string
}

function FrameworkCreationForm({
  taskId,
  context,
  onCreated,
}: {
  taskId: string
  context: CreationContext
  onCreated: () => Promise<unknown>
}) {
  const [question, setQuestion] = useState(context.phenomenon)
  const [researchObject, setResearchObject] = useState('')
  const [analysisUnit, setAnalysisUnit] = useState('')
  const creation = useMutation({
    mutationFn: () => createFrameworkViaApi({
      taskId,
      taskVersion: context.taskVersion,
      theoryPlanId: context.theoryPlanId,
      theoryPlanVersion: context.theoryPlanVersion,
      originalResearchQuestion: context.phenomenon,
      confirmedResearchQuestion: question,
      researchObject,
      analysisUnit,
      context: context.context,
    }),
    onSuccess: onCreated,
  })

  return (
    <form className="framework-creation" onSubmit={(event) => { event.preventDefault(); creation.mutate() }}>
      <p className="framework-kicker">FRAMEWORK / START</p>
      <h1>生成研究框架</h1>
      <p>已确认的理论方案将作为不可变快照进入框架；你可以在生成前收窄研究问题。</p>
      <label><span>研究问题</span><textarea required value={question} onChange={(event) => setQuestion(event.target.value)} /></label>
      <label><span>研究对象</span><input required value={researchObject} onChange={(event) => setResearchObject(event.target.value)} /></label>
      <label><span>分析单位</span><input value={analysisUnit} onChange={(event) => setAnalysisUnit(event.target.value)} /></label>
      <button type="submit" disabled={creation.isPending}>{creation.isPending ? '正在生成…' : '生成系统草稿'}</button>
      {creation.isError ? <p role="alert">框架生成失败，已确认的理论方案不会丢失。</p> : null}
    </form>
  )
}

export function ResearchFrameworkPage({
  taskId,
  creationContext,
}: {
  taskId: string
  creationContext: CreationContext | null
}) {
  const queryClient = useQueryClient()
  const [actionError, setActionError] = useState('')
  const queryKey = ['research-framework', taskId]
  const framework = useQuery({
    queryKey,
    queryFn: () => restoreFrameworkViaApi(taskId),
  })
  const refresh = () => queryClient.invalidateQueries({ queryKey })
  const action = useMutation({
    mutationFn: async (operation: () => Promise<unknown>) => operation(),
    onMutate: () => setActionError(''),
    onSuccess: refresh,
    onError: () => setActionError('操作未保存，已有版本仍保留。请刷新后重试。'),
  })

  if (framework.isPending) return <p role="status">正在恢复研究框架…</p>
  if (framework.isError) return <p role="alert">研究框架恢复失败。</p>
  if (!framework.data) {
    if (!creationContext) {
      return <p role="alert">这项研究还没有可用的已确认理论方案。</p>
    }
    return <FrameworkCreationForm taskId={taskId} context={creationContext} onCreated={refresh} />
  }

  const { raw, current, versions } = framework.data
  const run = (operation: () => Promise<unknown>) => action.mutate(operation)
  return (
    <>
      {actionError ? <p className="framework-action-error" role="alert">{actionError}</p> : null}
      <ResearchFrameworkWorkspace
        framework={current}
        versions={versions}
        busy={action.isPending}
        onSave={(next: ResearchFrameworkView, reason: string) => run(() => saveFrameworkViaApi(raw, next, reason))}
        onReview={() => run(() => reviewFrameworkViaApi(raw))}
        onResolve={(resolutions: FrameworkResolution[]) => run(() => resolveFrameworkAuditViaApi(raw, resolutions))}
        onConfirm={(resolutions: FrameworkResolution[]) => run(() => confirmFrameworkViaApi(raw, resolutions))}
      />
    </>
  )
}
