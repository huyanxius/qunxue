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

describe('PageShell support access', () => {
  it('keeps help reachable on immersive account pages', () => {
    render(
      <MemoryRouter>
        <PageShell immersive>
          <h1>登录</h1>
        </PageShell>
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: '帮助与边界' })).toBeVisible()
  })
})
