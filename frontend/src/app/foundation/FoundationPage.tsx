import { useState, type FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router'

import { submitResearchTask } from '../../modules/socio-match-workspace'
import { copy } from './copy'
import './foundation.css'
import { useSystemHealth } from './useSystemHealth'

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

function describeSubmitError(error: unknown): string {
  if (isRequestLikeError(error)) {
    if (!error.status || error.status >= 500) {
      return '服务暂时无法保存这条研究任务，请稍后重试。'
    }
    return error.message
  }
  return '服务暂时无法保存这条研究任务，请稍后重试。'
}

export function FoundationPage() {
  const navigate = useNavigate()
  const health = useSystemHealth()
  const [phenomenon, setPhenomenon] = useState('')
  const [researchIntent, setResearchIntent] = useState('')
  const [context, setContext] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const createTask = useMutation({
    mutationFn: () =>
      submitResearchTask({
        phenomenon,
        researchIntent,
        context,
      }),
    onSuccess: (task) => navigate(`/research/${task.taskId}`),
    onError: (error) => setFormError(describeSubmitError(error)),
  })

  const connectionLabel = health.isPending
    ? '正在检查接口契约'
    : health.isError
      ? '接口暂时不可用'
      : '接口已连接'

  function clearFormError() {
    if (formError) {
      setFormError(null)
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (phenomenon.trim() === '') {
      setFormError('请先描述你想研究的社会现象。')
      return
    }
    setFormError(null)
    createTask.mutate()
  }

  return (
    <main className="page-shell">
      <header className="masthead">
        <Link className="wordmark" to="/" aria-label="群学致知首页">
          <span className="wordmark-mark" aria-hidden="true">
            群
          </span>
          <span>群学致知</span>
        </Link>
        <p>研究现象录入</p>
      </header>

      <section className="opening">
        <p className="eyebrow">{copy.eyebrow}</p>
        <h1 className="display-title">{copy.title}</h1>
        <p className="opening-lede">{copy.lede}</p>
      </section>

      <section className="connection" aria-live="polite">
        <div>
          <span
            className={`connection-dot ${health.isError ? 'is-error' : ''}`}
            aria-hidden="true"
          />
          <strong>{connectionLabel}</strong>
        </div>
        {health.data ? (
          <dl>
            <div>
              <dt>契约</dt>
              <dd>{health.data.contractVersion}</dd>
            </div>
            <div>
              <dt>运行</dt>
              <dd>{health.data.runtimeMode}</dd>
            </div>
            <div>
              <dt>保存</dt>
              <dd>{health.data.persistence}</dd>
            </div>
          </dl>
        ) : null}
        {health.isError ? (
          <p className="connection-note">
            即使接口请求失败，这个表单里已经填写的内容也不会丢失。
          </p>
        ) : null}
      </section>

      <section className="action-line action-line-form">
        <div>
          <p className="section-index">01 / 研究现象录入</p>
          <h2>先用你自己的话，把观察到的现象留下来。</h2>
          <p>{copy.actionNote}</p>
        </div>
        <form className="intake-form" onSubmit={handleSubmit}>
          <label htmlFor="phenomenon">研究现象 *</label>
          <textarea
            id="phenomenon"
            name="phenomenon"
            rows={7}
            value={phenomenon}
            onChange={(event) => {
              clearFormError()
              setPhenomenon(event.target.value)
            }}
          />

          <label htmlFor="research-intent">研究意图</label>
          <input
            id="research-intent"
            name="researchIntent"
            type="text"
            value={researchIntent}
            onChange={(event) => {
              clearFormError()
              setResearchIntent(event.target.value)
            }}
          />

          <label htmlFor="context">补充背景</label>
          <textarea
            id="context"
            name="context"
            rows={4}
            value={context}
            onChange={(event) => {
              clearFormError()
              setContext(event.target.value)
            }}
          />

          <button type="submit" disabled={createTask.isPending}>
            {createTask.isPending ? '正在保存研究任务...' : '创建研究任务'}
          </button>
          {formError ? (
            <p className="inline-error" role="alert">
              {formError}
            </p>
          ) : null}
        </form>
      </section>

      <footer className="architecture-line">
        <span>React</span>
        <i aria-hidden="true">-&gt;</i>
        <span>生成 SDK</span>
        <i aria-hidden="true">-&gt;</i>
        <span>OpenAPI</span>
        <i aria-hidden="true">-&gt;</i>
        <span>research_intake</span>
        <i aria-hidden="true">-&gt;</i>
        <span>SQLite</span>
      </footer>
    </main>
  )
}
