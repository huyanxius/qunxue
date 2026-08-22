// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { FoundationAgentReveal } from './FoundationAgentReveal'

vi.mock('@paper-design/shaders-react', () => ({
  ShaderMount: ({ className }: { className?: string }) => <div className={className} />,
}))

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

function renderReveal() {
  return render(
    <MemoryRouter>
      <FoundationAgentReveal />
    </MemoryRouter>,
  )
}

describe('FoundationAgentReveal', () => {
  it('cycles complete research questions with character-level motion', () => {
    vi.useFakeTimers()
    vi.stubGlobal('matchMedia', () => ({ matches: false }))

    const { container } = renderReveal()
    const question = container.querySelector<HTMLElement>('[data-research-question]')

    expect(screen.queryByText('研究 Agent')).not.toBeInTheDocument()
    expect(question).toHaveTextContent('为什么同一课堂里有人总是沉默？')
    expect(question?.dataset.copyPhase).toBe('entering')
    expect(question?.querySelectorAll('.foundation-agent__glyph')).toHaveLength(15)

    act(() => vi.advanceTimersByTime(959))
    expect(question?.dataset.copyPhase).toBe('entering')

    act(() => vi.advanceTimersByTime(1))
    expect(question?.dataset.copyPhase).toBe('resting')

    act(() => vi.advanceTimersByTime(2_780))
    expect(question?.dataset.copyPhase).toBe('exiting')
    expect(question).toHaveTextContent('为什么同一课堂里有人总是沉默？')

    act(() => vi.advanceTimersByTime(459))
    expect(question?.dataset.copyPhase).toBe('exiting')
    expect(question).toHaveTextContent('为什么同一课堂里有人总是沉默？')

    act(() => vi.advanceTimersByTime(1))

    expect(question).toHaveTextContent('为什么短视频越刷越难停下来？')
    expect(question?.dataset.copyPhase).toBe('entering')
  })

  it('replaces the question cycle with the characters the visitor types', () => {
    vi.useFakeTimers()
    vi.stubGlobal('matchMedia', () => ({ matches: false }))

    const { container } = renderReveal()
    const input = screen.getByRole('textbox', { name: '输入你的研究困惑' })

    fireEvent.change(input, { target: { value: '宿舍里为什么总有人沉默？' } })

    const question = container.querySelector<HTMLElement>('[data-research-question]')
    expect(input).toHaveValue('宿舍里为什么总有人沉默？')
    expect(question?.dataset.copyMode).toBe('input')
    expect(question).toHaveTextContent('宿舍里为什么总有人沉默？')
    expect(question).not.toHaveTextContent('为什么同一课堂里有人总是沉默？')

    fireEvent.scroll(input, { target: { scrollLeft: 96 } })
    expect(question).toHaveStyle({ transform: 'translate3d(-96px, 0, 0)' })

    act(() => vi.advanceTimersByTime(8_400))
    expect(question).toHaveTextContent('宿舍里为什么总有人沉默？')
  })
})
