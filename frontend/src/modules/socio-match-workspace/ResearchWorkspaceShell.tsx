import type { ReactNode } from 'react'

import './research-workspace-shell.css'

export type ResearchStageId =
  | 'intake'
  | 'phenomenon'
  | 'theory'
  | 'decision'
  | 'framework'

type ResearchWorkspaceShellProps = {
  readonly currentStage: ResearchStageId
  readonly eyebrow: string
  readonly title: string
  readonly lede: string
  readonly children: ReactNode
  readonly context: ReactNode
  readonly taskLabel?: string
}

const stages: ReadonlyArray<{ id: ResearchStageId; label: string; detail: string }> = [
  { id: 'intake', label: '提出问题', detail: '描述现象与语境' },
  { id: 'phenomenon', label: '确认现象', detail: '核对结构化表述' },
  { id: 'theory', label: '比较理论', detail: '查看前提与依据' },
  { id: 'decision', label: '作出选择', detail: '记录你的判断' },
  { id: 'framework', label: '形成框架', detail: '保留可追溯结果' },
]

export function ResearchWorkspaceShell({
  currentStage,
  eyebrow,
  title,
  lede,
  children,
  context,
  taskLabel,
}: ResearchWorkspaceShellProps) {
  const currentIndex = stages.findIndex((stage) => stage.id === currentStage)

  return (
    <section className="research-shell">
      <header className="research-shell__topbar">
        <div>
          <span>{eyebrow}</span>
          {taskLabel ? <small>{taskLabel}</small> : null}
        </div>
        <a href="/my">全部研究</a>
      </header>

      <div className="research-shell__body">
        <nav className="research-stages" aria-label="研究阶段">
          <p>研究路径</p>
          <ol>
            {stages.map((stage, index) => {
              const status = index < currentIndex
                ? 'completed'
                : index === currentIndex
                  ? 'current'
                  : 'unavailable'
              return (
                <li
                  key={stage.id}
                  data-status={status}
                  aria-current={status === 'current' ? 'step' : undefined}
                >
                  <span aria-hidden="true">{status === 'completed' ? '✓' : index + 1}</span>
                  <div>
                    <strong>{stage.label}</strong>
                    <small>{stage.detail}</small>
                  </div>
                </li>
              )
            })}
          </ol>
        </nav>

        <section className="research-task" aria-label="当前研究任务">
          <header className="research-task__heading">
            <p>{eyebrow}</p>
            <h1>{title}</h1>
            <span>{lede}</span>
          </header>
          <div className="research-task__content">{children}</div>
        </section>

        <aside className="research-context" aria-label="当前步骤说明">
          {context}
        </aside>
      </div>
    </section>
  )
}
