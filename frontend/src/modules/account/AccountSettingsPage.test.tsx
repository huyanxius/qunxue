import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AccountSettingsPage } from './AccountSettingsPage'
import { AppLocaleProvider } from '../../i18n/AppLocaleProvider'
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
    getCreditSummary: async () => ({
      balance: 1200,
      creditLimit: 3000,
      grantAmount: 3000,
      isUnlimited: false,
      inputTokensPerCredit: 100,
      outputTokensPerCredit: 25,
      entries: [],
      totalEntries: 0,
      nextCursor: null,
    }),
    redeemCredits: async () => ({ redeemedPoints: 3000, balance: 3000 }),
    createCreditRedemptionCodes: async () => ({
      codes: [],
      points: 3000,
      expiresAt: '2026-09-22T23:59:59Z',
    }),
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

function openPartition(name: string) {
  const navigation = screen.getByRole('navigation', { name: '账户设置分区' })
  fireEvent.click(within(navigation).getByRole('button', { name }))
}

describe('AccountSettingsPage', () => {
  it('omits notification controls without a delivery service while preserving the stored preference', async () => {
    const updatePreferences = vi.fn(async () => account.preferences)
    render(<AccountSettingsPage api={createApi({ updatePreferences })} />)
    await screen.findByRole('heading', { name: '个人资料' })
    openPartition('使用偏好')
    expect(screen.queryByRole('checkbox', { name: /研究进度与内测通知/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '保存偏好' }))
    await waitFor(() => expect(updatePreferences).toHaveBeenCalledWith(expect.objectContaining({ researchUpdatesEnabled: true })))
  })

  it('shows the sign-out action below the settings navigation', async () => {
    const onLogout = vi.fn()
    render(<AccountSettingsPage api={createApi()} onLogout={onLogout} />)

    await screen.findByRole('navigation', { name: '账户设置分区' })
    const button = screen.getByRole('button', { name: '退出登录' })
    expect(button).toBeVisible()

    fireEvent.click(button)
    expect(onLogout).toHaveBeenCalledOnce()
  })

  it('shows one settings partition at a time and switches it from the left navigation', async () => {
    render(<AccountSettingsPage api={createApi()} />)

    expect(await screen.findByRole('heading', { name: '个人资料' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: '使用偏好' })).not.toBeInTheDocument()

    const navigation = screen.getByRole('navigation', { name: '账户设置分区' })
    fireEvent.click(within(navigation).getByRole('button', { name: '使用偏好' }))

    expect(screen.getByRole('heading', { name: '使用偏好' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: '个人资料' })).not.toBeInTheDocument()
  })

  it('previews English immediately and persists the locale preference', async () => {
    const updatePreferences = vi.fn(async (input) => ({
      ...account.preferences,
      locale: input.locale,
      timezone: input.timezone,
      researchUpdatesEnabled: input.researchUpdatesEnabled,
      version: 3,
    }))
    render(
      <AppLocaleProvider>
        <AccountSettingsPage api={createApi({ updatePreferences })} />
      </AppLocaleProvider>,
    )

    await screen.findByRole('heading', { name: '账户设置' })
    openPartition('使用偏好')
    fireEvent.change(screen.getByLabelText('界面语言'), { target: { value: 'en-US' } })

    expect(screen.getByRole('heading', { name: 'Preferences' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Credits & usage' })).toBeVisible()
    expect(document.documentElement).toHaveAttribute('lang', 'en')

    fireEvent.click(screen.getByRole('button', { name: 'Save preferences' }))
    await waitFor(() => expect(updatePreferences).toHaveBeenCalledWith(
      expect.objectContaining({ locale: 'en-US' }),
    ))
  })

  it('loads the credit balance and token ledger inside its own settings partition', async () => {
    const getCreditSummary = vi.fn(async () => ({
      balance: 1162,
      creditLimit: 3000,
      grantAmount: 3000,
      isUnlimited: false,
      inputTokensPerCredit: 100,
      outputTokensPerCredit: 25,
      entries: [{
        entryId: 'entry-1',
        kind: 'usage' as const,
        points: -38,
        balanceAfter: 1162,
        inputTokens: 600,
        outputTokens: 800,
        model: 'deepseek-v4-flash',
        createdAt: '2026-08-22T06:00:00Z',
      }],
      totalEntries: 1,
      nextCursor: null,
    }))
    const api = { ...createApi(), getCreditSummary } as AccountManagementApi

    render(<AccountSettingsPage api={api} />)

    const navigation = await screen.findByRole('navigation', { name: '账户设置分区' })
    fireEvent.click(within(navigation).getByRole('button', { name: '积分与用量' }))

    expect(getCreditSummary).toHaveBeenCalledOnce()
    expect(screen.getByLabelText('积分余额数值')).toHaveTextContent('1,162/ 3,000')
    expect(screen.getByRole('progressbar', { name: '积分余额' })).toHaveAttribute('aria-valuenow', '39')
    expect(screen.getByText('剩余 39%')).toBeVisible()
    expect(screen.getByText('600 输入 · 800 输出 token')).toBeVisible()
    expect(screen.getByText('-38')).toBeVisible()
    expect(screen.queryByText(/deepseek-v4-flash/)).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '个人资料' })).not.toBeInTheDocument()
  })

  it('pages the credit consumption ledger without appending one long list', async () => {
    const firstEntry = {
      entryId: 'entry-new',
      kind: 'usage' as const,
      points: -20,
      balanceAfter: 1100,
      inputTokens: 100,
      outputTokens: 25,
      createdAt: '2026-08-23T06:00:00Z',
    }
    const olderEntry = {
      ...firstEntry,
      entryId: 'entry-old',
      points: -12,
      balanceAfter: 1120,
      createdAt: '2026-08-01T06:00:00Z',
    }
    const getCreditSummary = vi.fn(async (input?: { cursor?: string; limit?: number }) => (
      input?.cursor === '10'
        ? {
            balance: 1100,
            creditLimit: 3000,
            grantAmount: 3000,
            isUnlimited: false,
            inputTokensPerCredit: 100,
            outputTokensPerCredit: 25,
            entries: [olderEntry],
            totalEntries: 11,
            nextCursor: null,
          }
        : {
            balance: 1100,
            creditLimit: 3000,
            grantAmount: 3000,
            isUnlimited: false,
            inputTokensPerCredit: 100,
            outputTokensPerCredit: 25,
            entries: [firstEntry],
            totalEntries: 11,
            nextCursor: '10',
          }
    ))
    render(<AccountSettingsPage api={createApi({ getCreditSummary })} />)

    await screen.findByRole('heading', { name: '账户设置' })
    openPartition('积分与用量')
    expect(screen.getByText('-20')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: '下一页积分消耗记录' }))

    await waitFor(() => expect(getCreditSummary).toHaveBeenLastCalledWith({
      cursor: '10',
      limit: 10,
    }))
    expect(await screen.findByText('-12')).toBeVisible()
    expect(screen.queryByText('-20')).not.toBeInTheDocument()
    expect(screen.getByText('第 2 页')).toBeVisible()
  })

  it('redeems one code and refreshes the visible credit balance', async () => {
    const getCreditSummary = vi.fn()
      .mockResolvedValueOnce({
        balance: 1200,
        creditLimit: 3000,
        grantAmount: 3000,
        isUnlimited: false,
        inputTokensPerCredit: 100,
        outputTokensPerCredit: 25,
        entries: [],
        totalEntries: 0,
        nextCursor: null,
      })
      .mockResolvedValueOnce({
        balance: 3000,
        creditLimit: 3000,
        grantAmount: 3000,
        isUnlimited: false,
        inputTokensPerCredit: 100,
        outputTokensPerCredit: 25,
        entries: [],
        totalEntries: 0,
        nextCursor: null,
      })
    const redeemCredits = vi.fn(async () => ({ redeemedPoints: 3000, balance: 3000 }))
    render(<AccountSettingsPage api={createApi({ getCreditSummary, redeemCredits })} />)

    await screen.findByRole('heading', { name: '账户设置' })
    openPartition('积分与用量')
    fireEvent.change(screen.getByLabelText('积分兑换码'), {
      target: { value: 'QX-7KDM-4XJP-9TWR-P6AC' },
    })
    fireEvent.click(screen.getByRole('button', { name: '兑换积分' }))

    await waitFor(() => expect(redeemCredits).toHaveBeenCalledWith({
      code: 'QX-7KDM-4XJP-9TWR-P6AC',
      idempotencyKey: expect.any(String),
    }))
    await waitFor(() => expect(screen.getByLabelText('积分余额数值')).toHaveTextContent('3,000/ 3,000'))
    expect(screen.getByRole('status')).toHaveTextContent('积分已恢复至 3,000')
  })

  it('shows an unlimited balance for the provisioned administrator', async () => {
    const api = createApi({
      getCreditSummary: async () => ({
        balance: 3000,
        creditLimit: 3000,
        grantAmount: 3000,
        isUnlimited: true,
        inputTokensPerCredit: 100,
        outputTokensPerCredit: 25,
        entries: [],
        totalEntries: 0,
        nextCursor: null,
      }),
    })

    render(<AccountSettingsPage api={api} />)

    const navigation = await screen.findByRole('navigation', { name: '账户设置分区' })
    fireEvent.click(within(navigation).getByRole('button', { name: '积分与用量' }))

    expect(screen.getByText('无限')).toBeVisible()
    expect(screen.getByText('管理员账户不扣减积分')).toBeVisible()
  })

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
    expect(within(screen.getByRole('region', { name: '个人资料' })).getByText('lin@example.com')).toBeVisible()
    openPartition('安全')
    expect(screen.getByText('没有其他活跃会话')).toBeVisible()
  })

  it('saves a profile once while the request is pending and keeps versioned input', async () => {
    const update = deferred<AccountProfile>()
    const updateProfile = vi.fn(() => update.promise)
    const onProfileUpdated = vi.fn()
    const api = createApi({ updateProfile })
    render(<AccountSettingsPage api={api} onProfileUpdated={onProfileUpdated} />)

    fireEvent.click(await screen.findByRole('button', { name: '修改显示名称' }))
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
    expect(screen.queryByRole('button', { name: '保存资料' })).not.toBeInTheDocument()
    expect(screen.getAllByText('林研究员').length).toBeGreaterThan(0)
    expect(onProfileUpdated).toHaveBeenCalledWith(expect.objectContaining({
      displayName: '林研究员',
      version: 4,
    }))
  })

  it('reuses one mutation key after a network failure for the same user intent', async () => {
    const updateProfile = vi.fn()
      .mockRejectedValueOnce(new TypeError('network unavailable'))
      .mockResolvedValueOnce({ ...account, displayName: '林研究员', version: 4 })
    render(<AccountSettingsPage api={createApi({ updateProfile })} />)

    fireEvent.click(await screen.findByRole('button', { name: '修改显示名称' }))
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

    await screen.findByRole('heading', { name: '账户设置' })
    openPartition('安全')
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

    await screen.findByRole('heading', { name: '账户设置' })
    openPartition('安全')
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

    await screen.findByRole('heading', { name: '账户设置' })
    openPartition('数据与隐私')
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

    openPartition('账户状态')
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

    await screen.findByRole('heading', { name: '账户设置' })
    openPartition('账户状态')
    expect(await screen.findByRole('heading', { name: '部署管理员保护' })).toBeVisible()
    expect(screen.getByText(/不能被降级、停用或删除/)).toBeVisible()
    expect(screen.queryByRole('button', { name: '停用账户' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '永久删除账户' })).not.toBeInTheDocument()
  })
})
