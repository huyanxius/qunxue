import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router'

import { readResearchTaskNavigationViaApi } from '../../api/researchWorkspace'
import { M4TheoryJudgment, type M4TaskContract } from '../../modules/m4-theory-judgment'
import { ResearchWorkspaceShell } from '../../modules/socio-match-workspace'
import { PageContent, PageShell } from '../ui/PageShell'
import { ErrorState, LoadingState } from '../ui/States'

export function M4TheoryJudgmentRoute() {
  const { task_id: taskId } = useParams<{ task_id: string }>()
  const navigate = useNavigate()
  const navigation = useQuery({
    queryKey: ['m4-theory-judgment-route', taskId],
    queryFn: () => readResearchTaskNavigationViaApi(taskId!),
    enabled: Boolean(taskId),
    retry: false,
  })

  if (!taskId) {
    return <PageShell wide><PageContent><ErrorState detail="研究任务地址无效。" /></PageContent></PageShell>
  }
  if (navigation.isPending) {
    return <PageShell wide><PageContent><LoadingState message="正在恢复理论判断" /></PageContent></PageShell>
  }
  if (navigation.isError) {
    return (
      <PageShell wide>
        <PageContent>
          <ErrorState
            title="理论判断暂时无法恢复"
            detail="研究内容仍然保留。检查网络后重试。"
            onRetry={() => void navigation.refetch()}
          />
        </PageContent>
      </PageShell>
    )
  }

  const task: M4TaskContract = {
    taskId: navigation.data.task_id,
    taskVersion: navigation.data.version,
    matchRunId: navigation.data.current_match_run_id,
    theoryPlanId: navigation.data.current_theory_plan_id,
    phenomenonQueryId: navigation.data.phenomenon_summary?.phenomenon_query_id ?? null,
    phenomenonVersion: navigation.data.phenomenon_summary?.version ?? null,
    canStartMatching: navigation.data.allowed_actions.includes('start_matching'),
  }

  return (
    <PageShell wide>
      <ResearchWorkspaceShell
        currentStage="theory"
        eyebrow="M4 · 理论判断"
        title="理论判断文档"
        lede="逐项核对理论适配、证据边界与风险，再记录你自己的选择理由。"
        taskLabel={`任务 ${taskId.slice(0, 8)}`}
        context={(
          <>
            <p>判断边界</p>
            <h2>候选不是结论</h2>
            <p>系统负责呈现适配条件、冲突证据与误用边界；最终采用理由由你填写并确认。</p>
          </>
        )}
      >
        <M4TheoryJudgment
          task={task}
          onConfirmed={() => navigate(`/research/${taskId}/framework`)}
        />
      </ResearchWorkspaceShell>
    </PageShell>
  )
}
