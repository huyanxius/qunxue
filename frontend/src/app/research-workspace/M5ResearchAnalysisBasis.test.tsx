import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { M5ResearchAnalysisBasis } from './M5ResearchAnalysisBasis'

afterEach(cleanup)

describe('M5ResearchAnalysisBasis', () => {
  it('shows the confirmed material analysis pinned to this document version', () => {
    render(
      <M5ResearchAnalysisBasis
        basis={{
          contentHash: 'sha256:9c663f38e254',
          codes: [
            { id: 'code-1', label: '时间压力', definition: '参与者将准备时间视为稀缺资源。' },
            { id: 'code-2', label: '同伴支持', definition: '同伴关系缓解学习不确定性。' },
          ],
          memos: [
            { id: 'memo-1', title: '资源差异不只是个人策略', kindLabel: '分析备忘' },
          ],
          comparisons: [
            {
              id: 'comparison-1',
              title: '两个学习场域的资源差异',
              theoryImplication: '现有解释需要区分制度供给与同伴网络。',
            },
          ],
          unavailableAnnotationCount: 1,
        }}
      />,
    )

    const region = screen.getByRole('region', { name: '本版材料分析依据' })
    expect(within(region).getByText('2 个编码 · 1 则备忘 · 1 项案例比较')).toBeVisible()
    expect(within(region).getByText('时间压力')).toBeVisible()
    expect(within(region).getByText('资源差异不只是个人策略')).toBeVisible()
    expect(within(region).getByText('两个学习场域的资源差异')).toBeVisible()
    expect(within(region).getByText('1 处原文已删除，仅保留来源记录')).toBeVisible()
    expect(within(region).getByText('依据版本 9c663f38e254')).toBeVisible()
  })

  it('states when a document version does not use personal material analysis', () => {
    render(<M5ResearchAnalysisBasis basis={null} />)

    expect(screen.getByRole('region', { name: '本版材料分析依据' })).toHaveTextContent(
      '本版尚未纳入已确认的个人材料分析。',
    )
  })
})
