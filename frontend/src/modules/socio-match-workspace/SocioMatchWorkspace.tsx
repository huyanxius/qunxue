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
  return value ?? 'Not provided'
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
            SQ
          </span>
          <span>SocioMatch</span>
        </a>
        <p>RESEARCH TASK</p>
      </header>

      <section className="task-heading">
        <p className="eyebrow">Restorable intake record</p>
        <h1 className="display-title">Research phenomenon saved</h1>
        <p>
          This task keeps the original user-submitted observation intact so the
          next matching step can only begin from a confirmed phenomenon.
        </p>
      </section>

      {task.isPending ? <p className="loading-line">Restoring task...</p> : null}
      {requestError ? (
        <section className="recovery-error" role="alert">
          <h2>
            {isMissingTask
              ? 'No research task exists for this task_id.'
              : 'This research task could not be restored right now.'}
          </h2>
          <p>
            {isMissingTask
              ? requestError.message
              : 'Please retry in a moment. Your saved task is not replaced by the interface.'}
          </p>
        </section>
      ) : null}
      {task.data ? (
        <section className="task-record">
          <dl>
            <div className="task-field task-field-wide">
              <dt>Phenomenon</dt>
              <dd>{task.data.phenomenon}</dd>
            </div>
            <div>
              <dt>Research intent</dt>
              <dd>{optionalField(task.data.researchIntent)}</dd>
            </div>
            <div>
              <dt>Context</dt>
              <dd>{optionalField(task.data.context)}</dd>
            </div>
            <div>
              <dt>Source</dt>
              <dd>{task.data.source}</dd>
            </div>
            <div>
              <dt>Task ID</dt>
              <dd>{task.data.taskId}</dd>
            </div>
            <div>
              <dt>Created at</dt>
              <dd>{task.data.createdAt}</dd>
            </div>
            <div>
              <dt>Updated at</dt>
              <dd>{task.data.updatedAt}</dd>
            </div>
          </dl>
          <p className="task-note">
            Refreshing this page restores the same task by its task_id in the URL.
          </p>
        </section>
      ) : null}

      <a className="text-link" href={homeHref} onClick={navigateHome}>
        Back to intake
      </a>
    </main>
  )
}
