import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PasswordResetPage } from './PasswordResetPage'
import {
  AccountManagementRequestError,
  type AccountManagementApi,
} from './accountManagementModels'

afterEach(cleanup)

function createApi(consumePasswordReset: AccountManagementApi['consumePasswordReset']): AccountManagementApi {
  return {
    getAccount: async () => { throw new Error('not used') },
    updateProfile: async () => { throw new Error('not used') },
    updatePreferences: async () => { throw new Error('not used') },
    updateModelDataAuthorization: async () => { throw new Error('not used') },
    changePassword: async () => { throw new Error('not used') },
    listSessions: async () => [],
    revokeSession: async () => undefined,
    requestDataExport: async () => { throw new Error('not used') },
    deactivateAccount: async () => ({ recoverable: true }),
    deleteAccount: async () => ({ recoverable: false }),
    listAdminUsers: async () => ({ items: [], total: 0, nextCursor: null }),
    updateUserRole: async () => { throw new Error('not used') },
    disableUser: async () => { throw new Error('not used') },
    enableUser: async () => { throw new Error('not used') },
    createPasswordReset: async () => { throw new Error('not used') },
    listAuditEvents: async () => ({ items: [], nextCursor: null }),
    consumePasswordReset,
  }
}

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

describe('PasswordResetPage', () => {
  it('keeps mismatched or short passwords away from the API', async () => {
    const consumePasswordReset = vi.fn(async () => undefined)
    render(
      <PasswordResetPage
        api={createApi(consumePasswordReset)}
        token="reset-token"
        loginHref="/login"
      />,
    )

    fireEvent.change(screen.getByLabelText('新密码'), { target: { value: 'short' } })
    fireEvent.change(screen.getByLabelText('确认新密码'), { target: { value: 'different' } })
    fireEvent.click(screen.getByRole('button', { name: '重设密码' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('密码需要 12-128 个字符')
    expect(consumePasswordReset).not.toHaveBeenCalled()
  })

  it('submits only once while pending and returns the user to login on success', async () => {
    const reset = deferred()
    const consumePasswordReset = vi.fn(() => reset.promise)
    const onReset = vi.fn()
    render(
      <PasswordResetPage
        api={createApi(consumePasswordReset)}
        token="reset-token"
        loginHref="/login"
        onReset={onReset}
      />,
    )

    fireEvent.change(screen.getByLabelText('新密码'), { target: { value: 'reset-research-passphrase' } })
    fireEvent.change(screen.getByLabelText('确认新密码'), { target: { value: 'reset-research-passphrase' } })
    const submit = screen.getByRole('button', { name: '重设密码' })
    fireEvent.click(submit)
    fireEvent.click(submit)

    expect(consumePasswordReset).toHaveBeenCalledOnce()
    expect(consumePasswordReset).toHaveBeenCalledWith(expect.objectContaining({
      token: 'reset-token',
      newPassword: 'reset-research-passphrase',
      idempotencyKey: expect.any(String),
    }))
    expect(submit).toBeDisabled()

    reset.resolve()
    expect(await screen.findByRole('heading', { name: '密码已重设' })).toBeVisible()
    expect(screen.getByText('所有旧会话都已撤销')).toBeVisible()
    expect(screen.getByRole('link', { name: '使用新密码登录' })).toHaveAttribute('href', '/login')
    await waitFor(() => expect(onReset).toHaveBeenCalledOnce())
  })

  it('explains an expired or consumed link without leaking server detail', async () => {
    const consumePasswordReset = vi.fn(async () => {
      throw new AccountManagementRequestError('token digest mismatch', 410, 'password_reset_expired')
    })
    render(
      <PasswordResetPage
        api={createApi(consumePasswordReset)}
        token="reset-token"
        loginHref="/login"
      />,
    )

    fireEvent.change(screen.getByLabelText('新密码'), { target: { value: 'reset-research-passphrase' } })
    fireEvent.change(screen.getByLabelText('确认新密码'), { target: { value: 'reset-research-passphrase' } })
    fireEvent.click(screen.getByRole('button', { name: '重设密码' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('重置链接已过期或已使用')
    expect(screen.queryByText('token digest mismatch')).not.toBeInTheDocument()
  })
})
