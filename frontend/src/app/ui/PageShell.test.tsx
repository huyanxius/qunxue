import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PageShell } from './PageShell'

vi.mock('../../modules/account', () => ({
  useAccount: () => ({
    sessionState: {
      status: 'authenticated' as const,
      session: { user: { displayName: '研究者' } },
    },
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    retrySession: vi.fn(),
  }),
}))

afterEach(cleanup)

describe('PageShell global chrome', () => {
  it('does not inject the retired help and boundary trigger', () => {
    render(
      <MemoryRouter>
        <PageShell immersive>
          <h1>登录</h1>
        </PageShell>
      </MemoryRouter>,
    )

    expect(screen.queryByRole('button', { name: '帮助与边界' })).not.toBeInTheDocument()
  })

  it('shows the research deep-dive update in the updates tab', () => {
    render(
      <MemoryRouter>
        <PageShell>
          <h1>工作台</h1>
        </PageShell>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: '通知' }))
    fireEvent.click(screen.getByRole('tab', { name: '更新日志' }))

    expect(screen.getByText('深度研究现已上线')).toBeInTheDocument()
    expect(screen.getByText(/自动让 Agent 规划任务/)).toBeInTheDocument()
  })
})
