import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
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
  it.each([
    ['/agent?conversation_id=conversation-b&task_id=task-1&knowledge_release_id=release-1', '研究画布', '/research/new?conversation_id=conversation-b&task_id=task-1&knowledge_release_id=release-1'],
    ['/research/new?conversation_id=conversation-b&task_id=task-1', '对话视图', '/agent?conversation_id=conversation-b&task_id=task-1'],
  ])('keeps the same conversation when switching views from %s', (path, label, destination) => {
    render(<MemoryRouter initialEntries={[path]}><PageShell><h1>研究</h1></PageShell></MemoryRouter>)
    const views = screen.getByRole('navigation', { name: '对话视图' })
    expect(within(views).getByRole('link', { name: label })).toHaveAttribute('href', destination)
    expect(within(screen.getByRole('navigation', { name: '桌面主导航' })).getByRole('link', { name: '新建研究' })).toHaveAttribute('href', '/research/new')
    const identityQuery = path.slice(path.indexOf('?'))
    expect(within(screen.getByRole('navigation', { name: '桌面主导航' })).getByRole('link', { name: '研究 Agent' })).toHaveAttribute('href', `/agent${identityQuery}`)
  })

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
