import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PageShell } from './PageShell'

vi.mock('../../modules/account', () => ({
  useAccount: () => ({
    sessionState: { status: 'anonymous' as const },
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

  it('keeps the SVG mark and bilingual product lockup visible in the app shell', () => {
    const { container } = render(
      <MemoryRouter>
        <PageShell>
          <h1>工作台</h1>
        </PageShell>
      </MemoryRouter>,
    )

    expect(screen.getAllByText('COLLECTIVE INQUIRY')).toHaveLength(2)
    expect(container.querySelectorAll('.product-mark img')).toHaveLength(2)
  })
})
