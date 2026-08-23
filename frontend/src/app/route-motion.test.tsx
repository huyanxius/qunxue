import { StrictMode } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { vi } from 'vitest'
import { Link, MemoryRouter, Route, Routes } from 'react-router'

import { RouteMotionSurface } from './route-motion'

function MotionFixture() {
  return (
    <>
      <Link to="/app">工作台</Link>
      <Link to="/agent">研究 Agent</Link>
      <Link to="/agent?conversation=recent">最近对话</Link>
      <Link to="/agent#composer">输入框</Link>
      <Link to="/research/new">研究画布</Link>
      <Link to="/research/task-1/match">文档节点</Link>
      <RouteMotionSurface>
        <Routes>
          <Route path="/app" element={<main>工作台页面</main>} />
          <Route path="/agent" element={<main>Agent 页面</main>} />
          <Route path="/research/new" element={<main>研究画布</main>} />
          <Route path="/research/task-1/match" element={<main>文档节点</main>} />
        </Routes>
      </RouteMotionSurface>
    </>
  )
}

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('RouteMotionSurface', () => {
  it('keeps vertical navigation direction through StrictMode double renders', () => {
    render(
      <StrictMode>
        <MemoryRouter initialEntries={['/app']}>
          <MotionFixture />
        </MemoryRouter>
      </StrictMode>,
    )

    fireEvent.click(screen.getByRole('link', { name: '研究 Agent' }))
    expect(screen.getByTestId('route-motion-surface').dataset.motionDirection).toBe('forward')

    fireEvent.click(screen.getByRole('link', { name: '工作台' }))
    expect(screen.getByTestId('route-motion-surface').dataset.motionDirection).toBe('backward')
  })

  it.each(['最近对话', '输入框'])('does not activate motion for an isolated %s navigation', (link) => {
    render(
      <StrictMode>
        <MemoryRouter initialEntries={['/agent']}>
          <MotionFixture />
        </MemoryRouter>
      </StrictMode>,
    )

    fireEvent.click(screen.getByRole('link', { name: link }))
    expect(screen.getByTestId('route-motion-surface').dataset.motionActive).toBe('false')
  })

  it('lets an in-flight pathname transition finish when the destination writes query state', () => {
    vi.useFakeTimers()
    render(
      <StrictMode>
        <MemoryRouter initialEntries={['/app']}>
          <MotionFixture />
        </MemoryRouter>
      </StrictMode>,
    )

    fireEvent.click(screen.getByRole('link', { name: '研究 Agent' }))
    fireEvent.click(screen.getByRole('link', { name: '最近对话' }))

    expect(screen.getByTestId('route-motion-surface').dataset.motionActive).toBe('true')
    expect(screen.getByTestId('route-motion-surface').dataset.motionDirection).toBe('forward')

    act(() => vi.advanceTimersByTime(222))
    expect(screen.getByTestId('route-motion-surface').dataset.motionActive).toBe('false')
  })

  it('keeps research stages visually on the same canvas', () => {
    render(
      <MemoryRouter initialEntries={['/research/new']}>
        <MotionFixture />
      </MemoryRouter>,
    )

    const surface = screen.getByTestId('route-motion-surface')
    fireEvent.click(screen.getByRole('link', { name: '文档节点' }))
    expect(screen.getByTestId('route-motion-surface').dataset.motionActive).toBe('false')
    expect(screen.getByTestId('route-motion-surface')).toBe(surface)
  })
})
