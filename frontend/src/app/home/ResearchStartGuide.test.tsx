import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { ResearchStartGuide } from './ResearchStartGuide'

afterEach(cleanup)

describe('ResearchStartGuide', () => {
  it('explains the real first-use path and keeps unfinished stages honest', () => {
    render(<ResearchStartGuide />)

    const guide = screen.getByRole('region', { name: '开始研究' })
    expect(guide).toHaveTextContent('从一个具体现象开始')
    expect(guide).toHaveTextContent('Agent 界面预览，尚未连接研究模型')
    expect(guide).toHaveTextContent('理论匹配与研究框架尚未开放')
    expect(guide).not.toHaveTextContent('审核')
    expect(guide).toHaveTextContent('由你确认')
  })
})
