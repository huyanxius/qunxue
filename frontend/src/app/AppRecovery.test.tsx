import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ErrorBoundary, FatalErrorState } from './ErrorBoundary'
import { NotFoundState, SessionRecoveryState } from './ui/States'

const retrySession = vi.hoisted(() => vi.fn())

afterEach(() => {
  cleanup()
  retrySession.mockReset()
})

describe('global recovery', () => {
  it('offers a navigable not-found state for unknown routes', () => {
    render(<NotFoundState />)

    expect(screen.getByRole('heading', { name: '找不到这个页面' })).toBeVisible()
    expect(screen.getByRole('link', { name: '回到首页' })).toHaveAttribute('href', '/')
  })

  it('lets a protected route retry a failed session check', () => {
    render(<SessionRecoveryState onRetry={retrySession} />)

    fireEvent.click(screen.getByRole('button', { name: '重试' }))

    expect(retrySession).toHaveBeenCalledTimes(1)
  })

  it('gives a crashed page a reload and home recovery path', () => {
    const reload = vi.fn()
    render(<FatalErrorState onReload={reload} />)

    fireEvent.click(screen.getByRole('button', { name: '重新加载' }))

    expect(reload).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('link', { name: '回到首页' })).toHaveAttribute('href', '/welcome')
  })

  it('turns a render crash into the same recoverable state', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    function BrokenChild(): never {
      throw new Error('render failed')
    }

    render(
      <ErrorBoundary>
        <BrokenChild />
      </ErrorBoundary>,
    )

    expect(screen.getByRole('heading', { name: '页面没有安全地完成渲染。' })).toBeVisible()
    expect(screen.getByRole('button', { name: '重新加载' })).toBeVisible()
    expect(consoleError).toHaveBeenCalled()
    consoleError.mockRestore()
  })
})
