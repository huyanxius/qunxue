import type { MouseEvent } from 'react'

import './workspace.css'
import { useResearchTask } from './useResearchTask'

export interface SocioMatchWorkspaceProps {
  readonly taskId: string
  readonly homeHref: string
  readonly onNavigateHome: () => void
}

interface RequestLikeError {
  readonly message: string
  readonly status?: number
}

function isRequestLikeError(error: unknown): error is RequestLikeError {
  return Boolean(
    error &&
      typeof error === 'object' &&
      'message' in error &&
      typeof error.message === 'string',
  )
}

function optionalField(value: string | null): string {
  return value ?? '未填写'
}

export function SocioMatchWorkspace({
  taskId,
  homeHref,
  onNavigateHome,
}: SocioMatchWorkspaceProps) {
  const task = useResearchTask(taskId)
  const requestError: RequestLikeError | null = isRequestLikeError(task.error)
    ? task.error
    : null
  const isMissingTask = requestError?.status === 404

  function navigateHome(event: MouseEvent<HTMLAnchorElement>) {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return
    }
    event.preventDefault()
    onNavigateHome()
  }

  return (
    <main className="page-shell task-page">
      <header className="masthead">
        <a className="wordmark" href={homeHref} onClick={navigateHome}>
          <span className="wordmark-mark" aria-hidden="true">
            群
          </span>
          <span>群学致知</span>
        </a>
        <p>研究任务</p>
      </header>

      <section className="task-heading">
        <p className="eyebrow">可恢复的现象记录</p>
        <h1 className="display-title">研究现象已录入</h1>
        <p>
          当前任务保留用户提交的原始现象描述，后续正式匹配只能从已确认的现象出发。
        </p>
      </section>

      {task.isPending ? <p className="loading-line">正在恢复任务...</p> : null}
      {requestError ? (
        <section className="recovery-error" role="alert">
          <h2>
            {isMissingTask
              ? '不存在这个 task_id 对应的研究任务。'
              : '暂时无法恢复这个研究任务。'}
          </h2>
          <p>
            {isMissingTask
              ? requestError.message
              : '请稍后重试。已保存的研究任务不会被界面覆盖。'}
          </p>
        </section>
      ) : null}
      {task.data ? (
        <section className="task-record">
          <dl>
            <div className="task-field task-field-wide">
              <dt>研究现象</dt>
              <dd>{task.data.phenomenon}</dd>
            </div>
            <div>
              <dt>研究意图</dt>
              <dd>{optionalField(task.data.researchIntent)}</dd>
            </div>
            <div>
              <dt>补充背景</dt>
              <dd>{optionalField(task.data.context)}</dd>
            </div>
            <div>
              <dt>来源</dt>
              <dd>{task.data.source}</dd>
            </div>
            <div>
              <dt>任务 ID</dt>
              <dd>{task.data.taskId}</dd>
            </div>
            <div>
              <dt>创建时间</dt>
              <dd>{task.data.createdAt}</dd>
            </div>
            <div>
              <dt>更新时间</dt>
              <dd>{task.data.updatedAt}</dd>
            </div>
          </dl>
          <p className="task-note">
            刷新页面后，系统会根据 URL 中的 task_id 恢复同一任务。
          </p>
        </section>
      ) : null}

      <a className="text-link" href={homeHref} onClick={navigateHome}>
        返回录入页
      </a>
    </main>
  )
}
