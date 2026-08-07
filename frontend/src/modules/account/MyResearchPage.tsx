import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { deleteMyResearchViaApi, listMyResearchViaApi } from './accountApi'
import type { MyResearchItem } from './types'

const researchQueryKey = ['account', 'research-tasks'] as const

export function MyResearchPage() {
  const queryClient = useQueryClient()
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)
  const research = useQuery({
    queryKey: researchQueryKey,
    queryFn: listMyResearchViaApi,
    retry: false,
  })
  const deletion = useMutation({
    mutationFn: deleteMyResearchViaApi,
    onSuccess: (_data, taskId) => {
      queryClient.setQueryData<MyResearchItem[]>(
        researchQueryKey,
        (items = []) => items.filter((item) => item.taskId !== taskId),
      )
      setPendingDeleteId(null)
    },
  })

  if (research.isPending) return <p role="status">正在读取研究列表…</p>
  if (research.isError) return <p role="alert">暂时无法读取研究列表，请稍后重试。</p>
  if (research.data.length === 0) {
    return (
      <div className="my-research-empty">
        <p>还没有研究任务。</p>
        <a className="text-link" href="/research/new">开始一项研究</a>
      </div>
    )
  }

  return (
    <div className="my-research-list">
      {research.data.map((item) => {
        const confirming = pendingDeleteId === item.taskId
        return (
          <article className="my-research-item" key={item.taskId}>
            <div>
              <p className="my-research-stage">{item.stageLabel}</p>
              <p className="my-research-summary" title={item.phenomenonSummary}>
                {item.phenomenonSummary}
              </p>
              <p className="my-research-time">
                已采用 {item.adoptedTheoryCount} 个理论
                {' · '}创建于 {new Date(item.createdAt).toLocaleString('zh-CN')}
                {' · '}更新于 {new Date(item.updatedAt).toLocaleString('zh-CN')}
              </p>
            </div>
            <div className="my-research-actions">
              <a className="text-link" href={item.entryPath}>继续研究</a>
              <button
                type="button"
                className={confirming ? 'danger-action' : 'text-action'}
                disabled={deletion.isPending}
                onClick={() => {
                  if (confirming) deletion.mutate(item.taskId)
                  else setPendingDeleteId(item.taskId)
                }}
              >
                {confirming ? '确认永久删除' : '删除研究'}
              </button>
              {confirming ? (
                <button
                  type="button"
                  className="text-action"
                  onClick={() => setPendingDeleteId(null)}
                >
                  取消
                </button>
              ) : null}
            </div>
            {confirming ? (
              <p className="delete-warning" role="alert">删除后任务及其派生内容不可恢复。</p>
            ) : null}
            {deletion.isError && confirming ? (
              <p className="delete-warning" role="alert">删除失败，研究内容仍然保留。</p>
            ) : null}
          </article>
        )
      })}
    </div>
  )
}
