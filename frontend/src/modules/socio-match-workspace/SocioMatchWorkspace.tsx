import type { MouseEvent } from 'react'

import './workspace.css'
import { useResearchTask } from './useResearchTask'

export interface SocioMatchWorkspaceProps {
  readonly taskId: string
  readonly homeHref: string
  readonly onNavigateHome: () => void
}

export function SocioMatchWorkspace({
  taskId,
  homeHref,
  onNavigateHome,
}: SocioMatchWorkspaceProps) {
  const task = useResearchTask(taskId)

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
        <a
          className="wordmark"
          href={homeHref}
          onClick={navigateHome}
        >
          <span className="wordmark-mark" aria-hidden="true">
            群
          </span>
          <span>群学致知</span>
        </a>
        <p>RESEARCH / DRAFT</p>
      </header>

      <section className="task-heading">
        <p className="eyebrow">研究任务已经落盘</p>
        <h1 className="display-title">起点保留下来了。</h1>
        <p>
          当前只确认恢复链路成立。现象输入、候选理论和研究框架将在各自契约冻结后进入。
        </p>
      </section>

      {task.isPending ? <p className="loading-line">正在恢复任务…</p> : null}
      {task.isError ? (
        <section className="recovery-error">
          <h2>没有找到这项研究任务。</h2>
          <p>返回首页重新建立；系统不会根据文本猜测或替换任务 ID。</p>
        </section>
      ) : null}
      {task.data ? (
        <section className="task-record">
          <div className="task-state">
            <span>状态</span>
            <strong>{task.data.status}</strong>
          </div>
          <dl>
            <div>
              <dt>稳定 ID</dt>
              <dd>{task.data.taskId}</dd>
            </div>
            <div>
              <dt>入口</dt>
              <dd>{task.data.entryType}</dd>
            </div>
            <div>
              <dt>版本</dt>
              <dd>{task.data.version}</dd>
            </div>
            <div>
              <dt>下一动作</dt>
              <dd>{task.data.allowedActions.join(', ')}</dd>
            </div>
          </dl>
          <p className="task-note">刷新此页，任务仍由后端按 ID 恢复。</p>
        </section>
      ) : null}

      <a
        className="text-link"
        href={homeHref}
        onClick={navigateHome}
      >
        ← 返回工程起点
      </a>
    </main>
  )
}
