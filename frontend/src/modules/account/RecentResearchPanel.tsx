import { useQuery } from '@tanstack/react-query'
import type { ComponentType, PropsWithChildren, ReactNode } from 'react'
import { ArrowRightIcon, TrayIcon } from '@phosphor-icons/react'

import { listMyResearchViaApi } from './accountApi'
import './recent-research.css'

const researchQueryKey = ['account', 'research-tasks'] as const

type LinkAdapterProps = PropsWithChildren<{
  className?: string
  href: string
}>

function AnchorLink({ children, ...props }: LinkAdapterProps) {
  return <a {...props}>{children}</a>
}

function relativeUpdate(value: string) {
  const updated = new Date(value)
  if (Number.isNaN(updated.getTime())) return '最近更新'
  return `更新于 ${updated.toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })}`
}

export function RecentResearchPanel({
  LinkComponent = AnchorLink,
  emptyIntro,
}: {
  LinkComponent?: ComponentType<LinkAdapterProps>
  emptyIntro?: ReactNode
}) {
  const research = useQuery({
    queryKey: researchQueryKey,
    queryFn: listMyResearchViaApi,
    retry: false,
    refetchOnMount: 'always',
  })

  if (research.isPending) {
    return (
      <section className="recent-research recent-research--loading" role="status">
        <span />
        <span />
        <span />
        <p>正在读取最近研究</p>
      </section>
    )
  }

  if (research.isError) {
    return (
      <section className="recent-research recent-research--error" role="alert">
        <p className="recent-research__label">最近研究</p>
        <h2>暂时无法读取最近研究</h2>
        <p>你的研究内容没有丢失，可以重新请求列表。</p>
        <button
          type="button"
          disabled={research.isFetching}
          onClick={() => research.refetch()}
        >
          {research.isFetching ? '正在重新加载' : '重新加载研究'}
        </button>
      </section>
    )
  }

  const latest = research.data[0]
  if (!latest) {
    return (
      <>
        {emptyIntro}
        <section className={`recent-research recent-research--empty${emptyIntro ? ' recent-research--with-intro' : ''}`}>
          <span className="recent-research__empty-icon" aria-hidden="true">
            <TrayIcon size={21} weight="regular" />
          </span>
          <h2>还没有研究任务</h2>
          <p>从一个具体的社会现象开始。研究阶段、依据和下一步会保存在这里。</p>
          <LinkComponent className="primary-action" href="/research/new">
            新建研究
          </LinkComponent>
        </section>
      </>
    )
  }

  return (
    <section className="recent-research recent-research--ready">
      <LinkComponent
        className="recent-research__task"
        href={latest.retry?.method === 'GET' ? latest.retry.href : latest.entryPath}
      >
        <span className="recent-research__task-main">
          <span className="recent-research__stage">{latest.stageLabel}</span>
          <strong>{latest.phenomenonSummary}</strong>
          <span className="recent-research__next">
            {latest.blocker ? (
              <>
                <span>{latest.blocker.message}</span>{' '}
                <span>{latest.nextActionLabel}</span>
              </>
            ) : <>下一步：{latest.nextActionLabel}</>}
          </span>
        </span>
        <span className="recent-research__task-meta">
          {relativeUpdate(latest.updatedAt)}
          <ArrowRightIcon size={16} weight="regular" aria-hidden="true" />
        </span>
      </LinkComponent>
    </section>
  )
}
