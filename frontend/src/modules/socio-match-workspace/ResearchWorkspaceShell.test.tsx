import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { ResearchWorkspaceShell } from './ResearchWorkspaceShell'

afterEach(cleanup)

describe('research workspace shell', () => {
  it('keeps the full research path visible and distinguishes completed, current and unavailable stages', () => {
    render(
      <ResearchWorkspaceShell
        currentStage="phenomenon"
        eyebrow="研究任务"
        title="确认研究现象"
        lede="先确认研究对象，再进入理论比较。"
        context={<p>这里说明为什么需要确认。</p>}
      >
        <p>研究表单</p>
      </ResearchWorkspaceShell>,
    )

    const progress = screen.getByRole('navigation', { name: '研究阶段' })
    expect(within(progress).getAllByRole('listitem')).toHaveLength(5)
    expect(within(progress).getByText('提出问题').closest('li')).toHaveAttribute('data-status', 'completed')
    expect(within(progress).getByText('确认现象').closest('li')).toHaveAttribute('aria-current', 'step')
    expect(within(progress).getByText('比较理论').closest('li')).toHaveAttribute('data-status', 'unavailable')
    expect(within(progress).queryByRole('link')).not.toBeInTheDocument()
  })

  it('uses the same task and context regions for the first research stage', () => {
    render(
      <ResearchWorkspaceShell
        currentStage="intake"
        eyebrow="新研究"
        title="从一个具体观察开始"
        lede="保留原始表达，后续每一步都可以回看。"
        context={<p>填写提示</p>}
      >
        <label htmlFor="observation">研究观察</label>
        <textarea id="observation" />
      </ResearchWorkspaceShell>,
    )

    expect(screen.getByRole('region', { name: '当前研究任务' })).toBeVisible()
    expect(screen.getByRole('complementary', { name: '当前步骤说明' })).toHaveTextContent('填写提示')
    expect(screen.getByText('提出问题').closest('li')).toHaveAttribute('aria-current', 'step')
    expect(screen.getByText('确认现象').closest('li')).toHaveAttribute('data-status', 'unavailable')
  })
})
