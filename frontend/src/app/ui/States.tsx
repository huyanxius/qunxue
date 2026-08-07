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
