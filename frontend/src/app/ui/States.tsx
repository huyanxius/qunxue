import type { ReactNode } from 'react'

type ActionStateProps = {
  title?: string
  detail?: string
  action?: ReactNode
}

export function LoadingState({ message = '正在准备页面' }: { message?: string }) {
  return (
    <section className="state-panel" role="status" aria-live="polite">
      <p>{message}</p>
    </section>
  )
}

export function EmptyState({
  title,
  detail = '当前没有可展示的内容。',
  action,
}: ActionStateProps & { title: string }) {
  return (
    <section className="state-panel">
      <h2>{title}</h2>
      <p>{detail}</p>
      {action ? <div className="state-panel__action">{action}</div> : null}
    </section>
  )
}

export function ErrorState({
  title = '页面暂时无法加载',
  detail = '请稍后重试；若问题持续存在，请保留当前地址。',
  onRetry,
}: ActionStateProps & { onRetry?: () => void }) {
  return (
    <section className="state-panel" role="alert">
      <h2>{title}</h2>
      <p>{detail}</p>
      {onRetry ? (
        <button className="state-panel__action" type="button" onClick={onRetry}>
          重试
        </button>
      ) : null}
    </section>
  )
}

export function SessionRecoveryState({ onRetry }: { onRetry: () => void }) {
  return (
    <ErrorState
      title="暂时无法确认登录状态"
      detail="请检查网络后重试；你的研究内容不会因这次连接失败而被删除。"
      onRetry={onRetry}
    />
  )
}

export function NotFoundState({ homeHref = '/' }: { homeHref?: string }) {
  return (
    <section className="not-found-state" role="alert">
      <p className="eyebrow">404 / NOT FOUND</p>
      <h1>找不到这个页面</h1>
      <p>地址可能已经失效，或页面还没有开放。</p>
      <a className="primary-action" href={homeHref}>回到首页</a>
    </section>
  )
}

export function DegradedState({
  title = '部分功能暂不可用',
  detail = '页面保留当前可用的信息，暂不以不完整数据替代。',
  action,
}: ActionStateProps) {
  return (
    <section className="state-panel" role="status" aria-live="polite">
      <h2>{title}</h2>
      <p>{detail}</p>
      {action ? <div className="state-panel__action">{action}</div> : null}
    </section>
  )
}
