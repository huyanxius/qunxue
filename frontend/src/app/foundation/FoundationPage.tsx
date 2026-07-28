import { useMutation } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router'

import { createResearchTask } from '../../modules/socio-match-workspace'
import { copy } from './copy'
import './foundation.css'
import { useSystemHealth } from './useSystemHealth'

export function FoundationPage() {
  const navigate = useNavigate()
  const health = useSystemHealth()
  const createTask = useMutation({
    mutationFn: () => createResearchTask(crypto.randomUUID()),
    onSuccess: (task) => navigate(`/research/${task.task_id}`),
  })

  const connectionLabel = health.isPending
    ? '正在与应用层握手'
    : health.isError
      ? '接口暂不可用'
      : '接口已接通'

  return (
    <main className="page-shell">
      <header className="masthead">
        <Link className="wordmark" to="/" aria-label="群学致知首页">
          <span className="wordmark-mark" aria-hidden="true">
            群
          </span>
          <span>群学致知</span>
        </Link>
        <p>FOUNDATION / 01</p>
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
              <dd>{health.data.contract_version}</dd>
            </div>
            <div>
              <dt>运行</dt>
              <dd>{health.data.runtime_mode}</dd>
            </div>
            <div>
              <dt>保存</dt>
              <dd>{health.data.persistence}</dd>
            </div>
          </dl>
        ) : null}
        {health.isError ? (
          <p className="connection-note">请确认 FastAPI 已在 8000 端口启动。</p>
        ) : null}
      </section>

      <section className="action-line">
        <div>
          <p className="section-index">01 / 研究任务</p>
          <h2>先留下一个可以恢复的起点。</h2>
          <p>{copy.actionNote}</p>
        </div>
        <button
          type="button"
          disabled={!health.data || createTask.isPending}
          onClick={() => createTask.mutate()}
        >
          {createTask.isPending ? '正在建立…' : '建立空白研究任务'}
        </button>
        {createTask.isError ? (
          <p className="inline-error">任务没有建立成功，请重试。</p>
        ) : null}
      </section>

      <footer className="architecture-line">
        <span>React</span>
        <i aria-hidden="true">→</i>
        <span>业务 SDK</span>
        <i aria-hidden="true">→</i>
        <span>OpenAPI</span>
        <i aria-hidden="true">→</i>
        <span>Application</span>
        <i aria-hidden="true">→</i>
        <span>SQLite</span>
      </footer>
    </main>
  )
}
