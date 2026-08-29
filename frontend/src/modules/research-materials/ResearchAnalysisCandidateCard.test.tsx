import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ResearchAnalysisCandidateCard } from './ResearchAnalysisCandidateCard'

afterEach(cleanup)

describe('ResearchAnalysisCandidateCard', () => {
  it('requires the user reason and sends the visible candidate version when confirming', async () => {
    const decide = vi.fn(async () => undefined)
    render(
      <ResearchAnalysisCandidateCard
        kindLabel="候选编码"
        title="照护责任重组"
        detail="迁移后照护责任在家庭成员之间重新分配。"
        rationale="这是可检验的候选，不是结论。"
        version={3}
        onDecide={decide}
      />,
    )

    const card = screen.getByRole('article', { name: '候选编码：照护责任重组' })
    expect(within(card).getByText('Agent 建议 · 待确认')).toBeVisible()
    expect(within(card).getByRole('button', { name: '确认候选编码' })).toBeDisabled()
    fireEvent.change(within(card).getByRole('textbox', { name: '判断依据' }), { target: { value: '  已回到原文核对  ' } })
    fireEvent.click(within(card).getByRole('button', { name: '确认候选编码' }))

    expect(decide).toHaveBeenCalledWith('confirmed', '已回到原文核对', 3)
  })

  it('keeps rejection as an explicit user decision', async () => {
    const decide = vi.fn(async () => undefined)
    render(
      <ResearchAnalysisCandidateCard
        kindLabel="备忘草稿"
        title="性别分工是唯一解释"
        detail="尚未检查资源差异的竞争解释。"
        version={1}
        onDecide={decide}
      />,
    )
    const card = screen.getByRole('article', { name: '备忘草稿：性别分工是唯一解释' })
    fireEvent.change(within(card).getByRole('textbox', { name: '判断依据' }), { target: { value: '过度概括，不保留' } })
    fireEvent.click(within(card).getByRole('button', { name: '拒绝备忘草稿' }))

    expect(decide).toHaveBeenCalledWith('rejected', '过度概括，不保留', 1)
  })
})
