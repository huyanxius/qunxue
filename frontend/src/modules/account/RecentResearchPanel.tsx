import { useQuery } from '@tanstack/react-query'
import type { ComponentType, PropsWithChildren, ReactNode } from 'react'
import { ArrowRightIcon, TrayIcon } from '@phosphor-icons/react'

import { listMyResearchViaApi } from './accountApi'
import { useAppLocale } from '../../i18n/AppLocaleProvider'
import { researchActionLabel, researchBlockerLabel, researchStageLabel } from './researchLabels'
import './recent-research.css'

const researchQueryKey = ['account', 'research-tasks'] as const

type LinkAdapterProps = PropsWithChildren<{
  className?: string
  href: string
}>

function AnchorLink({ children, ...props }: LinkAdapterProps) {
  return <a {...props}>{children}</a>
}

export function ResearchEmptyState({
  LinkComponent = AnchorLink,
  intro,
}: {
  LinkComponent?: ComponentType<LinkAdapterProps>
  intro?: ReactNode
}) {
  const { text } = useAppLocale()
  return (
    <>
      {intro}
      <section className={`recent-research recent-research--empty${intro ? ' recent-research--with-intro' : ''}`}>
        <span className="recent-research__empty-icon" aria-hidden="true">
          <TrayIcon size={21} weight="regular" />
        </span>
        <h2>{text('还没有研究任务', 'No research tasks yet')}</h2>
        <p>{text('从一个具体的社会现象开始。研究阶段、依据和下一步会保存在这里。', 'Start with a concrete social phenomenon. Stages, evidence, and next steps will be saved here.')}</p>
        <LinkComponent className="primary-action" href="/research/new">
          {text('开始第一项研究', 'Start your first study')}
        </LinkComponent>
      </section>
    </>
  )
}

function relativeUpdate(value: string, locale: string, text: (zh: string, en: string) => string) {
  const updated = new Date(value)
  if (Number.isNaN(updated.getTime())) return text('最近更新', 'Recently updated')
  return `${text('更新于', 'Updated')} ${updated.toLocaleString(locale, {
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
  const { locale, text } = useAppLocale()
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
        <p>{text('正在读取最近研究', 'Loading recent research')}</p>
      </section>
    )
  }

  if (research.isError) {
    return (
      <section className="recent-research recent-research--error" role="alert">
        <p className="recent-research__label">{text('最近研究', 'Recent research')}</p>
        <h2>{text('暂时无法读取最近研究', 'Recent research is unavailable')}</h2>
        <p>{text('你的研究内容没有丢失，可以重新请求列表。', 'Your research is safe. You can request the list again.')}</p>
        <button
          type="button"
          disabled={research.isFetching}
          onClick={() => research.refetch()}
        >
          {research.isFetching ? text('正在重新加载', 'Reloading…') : text('重新加载研究', 'Reload research')}
        </button>
      </section>
    )
  }

  const recentItems = research.data.slice(0, 4)
  if (recentItems.length === 0) {
    return <ResearchEmptyState LinkComponent={LinkComponent} intro={emptyIntro} />
  }

  return (
    <section className="recent-research recent-research--ready">
      <ul className="recent-research__list">
        {recentItems.map((item) => (
          <li key={item.taskId}>
            <LinkComponent
              className="recent-research__task"
              href={item.retry?.method === 'GET' ? item.retry.href : item.entryPath}
            >
              <span className="recent-research__stage">{researchStageLabel(item.stageLabel, locale)}</span>
              <strong>{item.phenomenonSummary}</strong>
              <span className="recent-research__next">
                {item.blocker ? (
                  <>
                    <span>{researchBlockerLabel(item.blocker.code, item.blocker.message, locale)}</span>{' '}
                    <span>{researchActionLabel(item.nextActionLabel, locale)}</span>
                  </>
                ) : <>{text('下一步：', 'Next: ')}{researchActionLabel(item.nextActionLabel, locale)}</>}
              </span>
              <span className="recent-research__task-meta">
                {relativeUpdate(item.updatedAt, locale, text)}
                <ArrowRightIcon size={16} weight="regular" aria-hidden="true" />
              </span>
            </LinkComponent>
          </li>
        ))}
      </ul>
    </section>
  )
}
