import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AccountSettingsPage } from './AccountSettingsPage'
import type {
  AccountManagementApi,
  AccountProfile,
  AccountSession,
} from './accountManagementModels'

afterEach(cleanup)

const account: AccountProfile = {
  userId: 'user-1',
  email: 'lin@example.com',
  displayName: '林同学',
  role: 'member',
  status: 'active',
  version: 3,
  createdAt: '2026-08-01T08:00:00Z',
  isProtectedAdmin: false,
  preferences: {
    locale: 'zh-CN',
    timezone: 'Asia/Shanghai',
    researchUpdatesEnabled: true,
    modelImprovementAllowed: false,
    consentPolicyVersion: '2026-08-secondary-use-v1',
    consentUpdatedAt: null,
    version: 2,
  },
}

const sessions: AccountSession[] = [
  {
    sessionId: 'session-current',
    current: true,
    createdAt: '2026-08-22T02:00:00Z',
    lastSeenAt: '2026-08-22T05:30:00Z',
    expiresAt: '2026-08-29T02:00:00Z',
    deviceLabel: 'Safari · macOS',
    ipAddress: '127.0.0.1',
  },
  {
    sessionId: 'session-other',
    current: false,
    createdAt: '2026-08-21T02:00:00Z',
    lastSeenAt: '2026-08-21T09:30:00Z',
    expiresAt: '2026-08-28T02:00:00Z',
    deviceLabel: 'Chrome · Windows',
    ipAddress: '192.0.2.10',
  },
]

function createApi(overrides: Partial<AccountManagementApi> = {}): AccountManagementApi {
  return {
    getAccount: async () => account,
    updateProfile: async ({ displayName }) => ({ ...account, displayName, version: 4 }),
    updatePreferences: async (input) => ({
      ...account.preferences,
      locale: input.locale,
      timezone: input.timezone,
      researchUpdatesEnabled: input.researchUpdatesEnabled,
      version: 3,
    }),
    updateModelDataAuthorization: async ({ allowed, policyVersion }) => ({
      ...account.preferences,
      modelImprovementAllowed: allowed,
      consentPolicyVersion: policyVersion,
      consentUpdatedAt: '2026-08-22T06:00:00Z',
      version: 3,
    }),
    changePassword: async () => ({ revokedSessionCount: 1 }),
    listSessions: async () => sessions,
    revokeSession: async () => undefined,
    requestDataExport: async () => ({
      exportId: 'export-1',
      status: 'ready',
      createdAt: '2026-08-22T06:00:00Z',
      expiresAt: '2026-08-29T06:00:00Z',
      downloadHref: '/api/account/data-exports/export-1/download',
    }),
    deactivateAccount: async () => ({ recoverable: true }),
    deleteAccount: async () => ({ recoverable: false }),
    listAdminUsers: async () => ({ items: [], total: 0, nextCursor: null }),
    updateUserRole: async () => { throw new Error('not used') },
    disableUser: async () => { throw new Error('not used') },
    enableUser: async () => { throw new Error('not used') },
    createPasswordReset: async () => { throw new Error('not used') },
    listAuditEvents: async () => ({ items: [], nextCursor: null }),
    consumePasswordReset: async () => undefined,
    ...overrides,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

describe('AccountSettingsPage', () => {
  it('recovers from a failed load and explains an empty session list', async () => {
    let attempt = 0
    const api = createApi({
      getAccount: async () => {
        attempt += 1
        if (attempt === 1) throw new Error('network unavailable')
        return account
      },
      listSessions: async () => [],
    })

    render(<AccountSettingsPage api={api} />)

    expect(screen.getByRole('status')).toHaveTextContent('正在读取账户设置')
    const loadError = await screen.findByRole('alert')
    expect(loadError).toHaveTextContent('暂时无法读取账户设置')
    fireEvent.click(within(loadError).getByRole('button', { name: '重试' }))

    expect(await screen.findByRole('heading', { name: '账户设置' })).toBeVisible()
    expect(screen.getByText('lin@example.com')).toBeVisible()
    expect(screen.getByText('没有其他活跃会话')).toBeVisible()
  })

  it('saves a profile once while the request is pending and keeps versioned input', async () => {
    const update = deferred<AccountProfile>()
    const updateProfile = vi.fn(() => update.promise)
    const api = createApi({ updateProfile })
    render(<AccountSettingsPage api={api} />)

    const displayName = await screen.findByLabelText('显示名称')
    fireEvent.change(displayName, { target: { value: '林研究员' } })
    const save = screen.getByRole('button', { name: '保存资料' })
    fireEvent.click(save)
    fireEvent.click(save)

    expect(updateProfile).toHaveBeenCalledOnce()
    expect(updateProfile).toHaveBeenCalledWith(expect.objectContaining({
      displayName: '林研究员',
      expectedVersion: 3,
      idempotencyKey: expect.any(String),
    }))
    expect(save).toBeDisabled()

    update.resolve({ ...account, displayName: '林研究员', version: 4 })
    expect(await screen.findByRole('status')).toHaveTextContent('资料已保存')
    expect(displayName).toHaveValue('林研究员')
  })

  it('reuses one mutation key after a network failure for the same user intent', async () => {
    const updateProfile = vi.fn()
      .mockRejectedValueOnce(new TypeError('network unavailable'))
      .mockResolvedValueOnce({ ...account, displayName: '林研究员', version: 4 })
    render(<AccountSettingsPage api={createApi({ updateProfile })} />)

    const displayName = await screen.findByLabelText('显示名称')
    fireEvent.change(displayName, { target: { value: '林研究员' } })
    const save = screen.getByRole('button', { name: '保存资料' })
    fireEvent.click(save)

    expect(await screen.findByRole('alert')).toHaveTextContent('操作未完成')
    fireEvent.click(save)

    await waitFor(() => expect(updateProfile).toHaveBeenCalledTimes(2))
    expect(updateProfile.mock.calls[1][0].idempotencyKey).toBe(
      updateProfile.mock.calls[0][0].idempotencyKey,
    )
    expect(await screen.findByRole('status')).toHaveTextContent('资料已保存')
  })

  it('traps focus in a session confirmation and restores the trigger after Escape', async () => {
    const revokeSession = vi.fn(async () => undefined)
    render(<AccountSettingsPage api={createApi({ revokeSession })} />)

    const trigger = await screen.findByRole('button', { name: '撤销 Chrome · Windows 会话' })
    fireEvent.click(trigger)
    const dialog = screen.getByRole('dialog', { name: '撤销这个会话？' })
    expect(within(dialog).getByRole('button', { name: '取消' })).toHaveFocus()
    fireEvent.keyDown(dialog, { key: 'Escape' })

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()

    fireEvent.click(trigger)
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '确认撤销' }))
    await waitFor(() => expect(revokeSession).toHaveBeenCalledWith(
      'session-other',
      { idempotencyKey: expect.any(String) },
    ))
    expect(screen.queryByText('Chrome · Windows')).not.toBeInTheDocument()
    expect(await screen.findByRole('status')).toHaveTextContent('会话已撤销')
  })

  it('changes the password and removes revoked sessions from the visible ledger', async () => {
    const changePassword = vi.fn(async () => ({ revokedSessionCount: 1 }))
    render(<AccountSettingsPage api={createApi({ changePassword })} />)

    await screen.findByRole('heading', { name: '安全' })
    fireEvent.change(screen.getByLabelText('当前密码'), {
      target: { value: 'research-passphrase' },
    })
    fireEvent.change(screen.getByLabelText('新密码'), {
      target: { value: 'new-research-passphrase' },
    })
    fireEvent.change(screen.getByLabelText('确认新密码'), {
      target: { value: 'new-research-passphrase' },
    })
    fireEvent.click(screen.getByRole('button', { name: '更新密码' }))

    await waitFor(() => expect(changePassword).toHaveBeenCalledWith({
      currentPassword: 'research-passphrase',
      newPassword: 'new-research-passphrase',
      revokeOtherSessions: true,
      idempotencyKey: expect.any(String),
    }))
    expect(await screen.findByRole('status')).toHaveTextContent('密码已更新，已撤销 1 个其他会话')
    expect(screen.queryByText('Chrome · Windows')).not.toBeInTheDocument()
  })

  it('makes model authorization explicit, exposes a real export, and requires typed deletion proof', async () => {
    const updateAuthorization = vi.fn(async () => ({
      ...account.preferences,
      modelImprovementAllowed: true,
      consentUpdatedAt: '2026-08-22T06:00:00Z',
      version: 3,
    }))
    const deleteAccount = vi.fn(async () => ({ recoverable: false as const }))
    const onAccountDeleted = vi.fn()
    render(
      <AccountSettingsPage
        api={createApi({
          updateModelDataAuthorization: updateAuthorization,
          deleteAccount,
        })}
        onAccountDeleted={onAccountDeleted}
      />,
    )

    const modelSwitch = await screen.findByRole('switch', { name: '允许用于改进模型' })
    expect(modelSwitch).toHaveAttribute('aria-checked', 'false')
    fireEvent.click(modelSwitch)
    const consentDialog = screen.getByRole('dialog', { name: '允许用于改进模型？' })
    expect(consentDialog).toHaveTextContent('当前不使用你的数据训练模型')
    fireEvent.click(within(consentDialog).getByRole('button', { name: '确认允许' }))
    await waitFor(() => expect(updateAuthorization).toHaveBeenCalledWith({
      allowed: true,
      policyVersion: '2026-08-secondary-use-v1',
      expectedVersion: 2,
      idempotencyKey: expect.any(String),
    }))
    expect(modelSwitch).toHaveAttribute('aria-checked', 'true')

    fireEvent.click(screen.getByRole('button', { name: '导出我的数据' }))
    expect(await screen.findByRole('link', { name: '下载数据副本' })).toHaveAttribute(
      'href',
      '/api/account/data-exports/export-1/download',
    )

    const deleteTrigger = screen.getByRole('button', { name: '永久删除账户' })
    fireEvent.click(deleteTrigger)
    const deleteDialog = screen.getByRole('dialog', { name: '永久删除账户？' })
    expect(deleteDialog).toHaveTextContent('删除后无法恢复')
    const confirm = within(deleteDialog).getByRole('button', { name: '确认永久删除' })
    expect(confirm).toBeDisabled()
    fireEvent.change(within(deleteDialog).getByLabelText('账户邮箱'), {
      target: { value: 'lin@example.com' },
    })
    fireEvent.change(within(deleteDialog).getByLabelText('当前密码'), {
      target: { value: 'research-passphrase' },
    })
    fireEvent.click(confirm)

    await waitFor(() => expect(deleteAccount).toHaveBeenCalledWith({
      currentPassword: 'research-passphrase',
      confirmationEmail: 'lin@example.com',
      idempotencyKey: expect.any(String),
    }))
    expect(onAccountDeleted).toHaveBeenCalledOnce()
  })

  it('explains the fixed deployment administrator boundary without offering deletion', async () => {
    render(<AccountSettingsPage api={createApi({
      getAccount: async () => ({ ...account, role: 'admin', isProtectedAdmin: true }),
    })} />)

    expect(await screen.findByRole('heading', { name: '部署管理员保护' })).toBeVisible()
    expect(screen.getByText(/不能被降级、停用或删除/)).toBeVisible()
    expect(screen.queryByRole('button', { name: '停用账户' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '永久删除账户' })).not.toBeInTheDocument()
  })
})
