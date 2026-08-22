import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { Navigate, useLocation, useParams } from 'react-router'

import { readResearchTaskNavigationViaApi } from '../api/researchWorkspace'
import { PageContent, PageShell } from './ui/PageShell'
import { ErrorState, LoadingState } from './ui/States'

function RecoveryFailure({ onRetry }: { onRetry: () => void }) {
  return (
    <PageShell wide>
      <PageContent>
        <ErrorState
          title="研究进度暂时无法恢复"
          detail="研究内容仍然保留。检查网络后重试，或先返回研究列表。"
          onRetry={onRetry}
        />
        <a href="/my">返回我的研究</a>
      </PageContent>
    </PageShell>
  )
}

function isTaskResumePath(taskId: string, resumePath: string) {
  return new Set([
    `/research/${taskId}/phenomenon`,
    `/research/${taskId}/match`,
    `/research/${taskId}/framework`,
  ]).has(resumePath)
}

export function ResearchTaskNavigationRoute({ children }: { children: ReactNode }) {
  const { task_id: taskId } = useParams<{ task_id: string }>()
  const location = useLocation()
  const navigation = useQuery({
    queryKey: ['research-task-navigation-route', taskId, location.pathname],
    queryFn: () => readResearchTaskNavigationViaApi(taskId!),
    enabled: Boolean(taskId),
    refetchOnMount: 'always',
    refetchOnReconnect: false,
    refetchOnWindowFocus: false,
    retry: false,
  })

  if (!taskId) return <RecoveryFailure onRetry={() => undefined} />

  if (navigation.isPending || navigation.isFetching) {
    return (
      <PageShell wide>
        <PageContent>
          <LoadingState message="正在恢复研究进度" />
        </PageContent>
      </PageShell>
    )
  }

  if (navigation.isError) {
    return <RecoveryFailure onRetry={() => void navigation.refetch()} />
  }

  if (!isTaskResumePath(taskId, navigation.data.resume_path)) {
    return <RecoveryFailure onRetry={() => void navigation.refetch()} />
  }

  if (navigation.data.resume_path !== location.pathname) {
    return <Navigate replace to={navigation.data.resume_path} />
  }

  return children
}
