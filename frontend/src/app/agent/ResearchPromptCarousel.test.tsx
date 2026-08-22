import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ResearchPromptCarousel } from './ResearchPromptCarousel'

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('ResearchPromptCarousel', () => {
  it('keeps the central invitation still for five seconds before revealing a preset topic', () => {
    vi.useFakeTimers()
    const { container } = render(<ResearchPromptCarousel onSelect={vi.fn()} />)

    expect(screen.getByRole('heading', { name: '你想研究什么？' })).toBeVisible()
    expect(container.querySelector('[data-copy-phase]')).toHaveAttribute('data-copy-phase', 'entering')

    act(() => vi.advanceTimersByTime(760))
    expect(container.querySelector('[data-copy-phase]')).toHaveAttribute('data-copy-phase', 'resting')

    act(() => vi.advanceTimersByTime(4_239))
    expect(screen.getByRole('heading', { name: '你想研究什么？' })).toBeVisible()

    act(() => vi.advanceTimersByTime(1))
    expect(container.querySelector('[data-copy-phase]')).toHaveAttribute('data-copy-phase', 'exiting')

    act(() => vi.advanceTimersByTime(460))
    expect(screen.getByRole('button', { name: '为什么同一课堂里有人总是沉默？' })).toBeVisible()
  })

  it('lets the user try a rotating preset and moves to the next topic after one cycle', () => {
    vi.useFakeTimers()
    const onSelect = vi.fn()
    render(<ResearchPromptCarousel onSelect={onSelect} />)

    act(() => vi.advanceTimersByTime(5_000))
    act(() => vi.advanceTimersByTime(460))
    const firstTopic = screen.getByRole('button', { name: '为什么同一课堂里有人总是沉默？' })
    fireEvent.click(firstTopic)
    expect(onSelect).toHaveBeenCalledWith('为什么同一课堂里有人总是沉默？')

    act(() => vi.advanceTimersByTime(3_740))
    act(() => vi.advanceTimersByTime(460))

    expect(screen.getByRole('button', { name: '为什么短视频越刷越难停下来？' })).toBeVisible()
  })

  it('shows twenty distinct presets before the carousel repeats', () => {
    vi.useFakeTimers()
    render(<ResearchPromptCarousel onSelect={vi.fn()} />)

    const moveToNextPreset = () => {
      act(() => vi.advanceTimersByTime(3_740))
      act(() => vi.advanceTimersByTime(460))
    }

    act(() => vi.advanceTimersByTime(5_000))
    act(() => vi.advanceTimersByTime(460))

    const seen = [screen.getByRole('button').getAttribute('aria-label')]
    for (let index = 1; index < 20; index += 1) {
      moveToNextPreset()
      seen.push(screen.getByRole('button').getAttribute('aria-label'))
    }

    expect(new Set(seen).size).toBe(20)
    expect(seen.at(-1)).toBe('为什么技术进步没有减少所有人的负担？')

    moveToNextPreset()
    expect(screen.getByRole('button', { name: '为什么同一课堂里有人总是沉默？' })).toBeVisible()
  })
})
