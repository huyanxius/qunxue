import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DegradedState, EmptyState, ErrorState, LoadingState } from './States'

afterEach(cleanup)

describe('shared page states', () => {
  it('announces loading without presenting successful content', () => {
    render(<LoadingState />)

    expect(screen.getByRole('status')).toHaveTextContent('正在准备页面')
  })

  it('gives an empty result a heading and an optional next action', () => {
    render(<EmptyState title="还没有研究任务" action={<a href="/research/new">新建研究任务</a>} />)

    expect(screen.getByRole('heading', { name: '还没有研究任务' })).toBeVisible()
    expect(screen.getByRole('link', { name: '新建研究任务' })).toHaveAttribute(
      'href',
      '/research/new',
    )
  })

  it('exposes an error to assistive technology and invokes retry', () => {
    const onRetry = vi.fn()
    render(<ErrorState onRetry={onRetry} />)

    fireEvent.click(screen.getByRole('button', { name: '重试' }))

    expect(screen.getByRole('alert')).toHaveTextContent('页面暂时无法加载')
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('labels a degraded result without treating it as successful data', () => {
    render(<DegradedState />)

    expect(screen.getByRole('status')).toHaveTextContent('部分功能暂不可用')
  })
})
