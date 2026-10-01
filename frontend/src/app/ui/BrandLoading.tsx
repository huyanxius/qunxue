import type { CSSProperties } from 'react'

/** Progress is a measured percentage (0–100); omit it when completion is unknown. */
export function BrandLoading({
  message = '正在准备页面',
  progress,
  compact = false,
  fullscreen = false,
}: {
  message?: string
  progress?: number
  compact?: boolean
  fullscreen?: boolean
}) {
  const value = progress !== undefined && Number.isFinite(progress)
    ? Math.min(100, Math.max(0, progress))
    : undefined

  return (
    <section className={`brand-loading${compact ? ' brand-loading--compact' : ''}${fullscreen ? ' brand-loading--fullscreen' : ''}`}>
      <span
        className={`brand-loading__mark${value === undefined ? ' brand-loading__mark--waiting' : ''}`}
        style={value === undefined ? undefined : { '--brand-loading-fill': `${100 - value}%` } as CSSProperties}
        role={value === undefined ? undefined : 'progressbar'}
        aria-hidden={value === undefined ? true : undefined}
        aria-label={value === undefined ? undefined : message}
        aria-valuemin={value === undefined ? undefined : 0}
        aria-valuemax={value === undefined ? undefined : 100}
        aria-valuenow={value}
        aria-live={value === undefined ? undefined : 'off'}
      >
        <span className="brand-loading__fill" />
      </span>
      <p className="brand-loading__message" role="status" aria-live="polite" aria-atomic="true">{message}</p>
    </section>
  )
}
