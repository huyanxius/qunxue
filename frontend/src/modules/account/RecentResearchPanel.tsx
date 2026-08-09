import { useQuery } from '@tanstack/react-query'
import type { ComponentType, PropsWithChildren } from 'react'

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
}: {
  LinkComponent?: ComponentType<LinkAdapterProps>
}) {
  const research = useQuery({
    queryKey: researchQueryKey,
    queryFn: listMyResearchViaApi,
    retry: false,
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
      <section className="recent-research recent-research--empty">
        <p className="recent-research__label">最近研究</p>
        <h2>还没有研究任务</h2>
        <p>从自己的现象开始，或先用内置案例熟悉确认与比较方式。</p>
        <div className="recent-research__actions">
          <LinkComponent className="primary-action" href="/research/new">开始新研究</LinkComponent>
          <LinkComponent className="secondary-action" href="/research/new">从内置案例开始</LinkComponent>
        </div>
      </section>
    )
  }

  return (
    <section className="recent-research recent-research--ready">
      <div className="recent-research__meta">
        <p className="recent-research__label">最近研究</p>
        <span>{relativeUpdate(latest.updatedAt)}</span>
      </div>
      <p className="recent-research__stage">{latest.stageLabel}</p>
      <h2>{latest.phenomenonSummary}</h2>
      <p className="recent-research__next">下一步：{latest.nextActionLabel}</p>
      <div className="recent-research__actions">
        <LinkComponent className="primary-action" href={latest.entryPath}>继续研究</LinkComponent>
        <LinkComponent className="secondary-action" href="/my">查看全部研究</LinkComponent>
      </div>
    </section>
  )
}
