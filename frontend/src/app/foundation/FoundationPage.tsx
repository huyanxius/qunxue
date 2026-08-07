import { useMutation } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router'

import { startResearchTask } from '../../modules/socio-match-workspace'
import { copy } from './copy'
import './foundation.css'
import { useSystemHealth } from './useSystemHealth'
import { PageContent, PageShell, PageTitle } from '../ui/PageShell'

export function FoundationPage() {
  const navigate = useNavigate()
  const health = useSystemHealth()
  const createTask = useMutation({
    mutationFn: () => startResearchTask(crypto.randomUUID()),
    onSuccess: (task) => navigate(`/research/${task.taskId}/phenomenon`),
  })

  const connectionLabel = health.isPending
    ? '正在与应用层握手'
    : health.isError
      ? '接口暂不可用'
      : '接口已接通'

  return (
    <PageShell>
      <PageTitle eyebrow={copy.eyebrow} title={copy.title} lede={copy.lede} />

      <PageContent>
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
            className="action-line__control"
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

        <section className="action-line action-line--knowledge">
          <div>
            <p className="section-index">02 / 知识浏览</p>
            <h2>查看知识条目如何连接来源、审核与关系。</h2>
            <p>
              当前入口使用明确标识的演示数据，用于验证知识浏览的信息结构和交互状态。
            </p>
          </div>
          <Link className="action-line__control" to="/knowledge">
            进入可视化知识库
          </Link>
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
      </PageContent>
    </PageShell>
  )
}
