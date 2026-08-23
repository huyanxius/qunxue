import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AdminUsersPage } from './AdminUsersPage'
import type {
  AccountManagementApi,
  AdminUser,
} from './accountManagementModels'

afterEach(cleanup)

const admin: AdminUser = {
  userId: 'admin-1',
  email: 'owner@example.com',
  displayName: '创建者',
  role: 'admin',
  status: 'active',
  version: 4,
  createdAt: '2026-08-01T08:00:00Z',
  lastActiveAt: '2026-08-22T05:00:00Z',
  isCurrentUser: true,
  isProtectedAdmin: true,
}

const member: AdminUser = {
  userId: 'user-2',
  email: 'member@example.com',
  displayName: '林同学',
  role: 'member',
  status: 'active',
  version: 2,
  createdAt: '2026-08-10T08:00:00Z',
  lastActiveAt: '2026-08-21T05:00:00Z',
  isCurrentUser: false,
  isProtectedAdmin: false,
}

function createApi(overrides: Partial<AccountManagementApi> = {}): AccountManagementApi {
  return {
    getAccount: async () => { throw new Error('not used') },
    getCreditSummary: async () => { throw new Error('not used') },
    redeemCredits: async () => { throw new Error('not used') },
    createCreditRedemptionCodes: async () => ({
      codes: [],
      points: 3000,
      expiresAt: '2026-09-22T23:59:59Z',
    }),
    updateProfile: async () => { throw new Error('not used') },
    updatePreferences: async () => { throw new Error('not used') },
    updateModelDataAuthorization: async () => { throw new Error('not used') },
    changePassword: async () => { throw new Error('not used') },
    listSessions: async () => [],
    revokeSession: async () => undefined,
    requestDataExport: async () => { throw new Error('not used') },
    deactivateAccount: async () => ({ recoverable: true }),
    deleteAccount: async () => ({ recoverable: false }),
    listAdminUsers: async () => ({ items: [admin, member], total: 2, nextCursor: null }),
    updateUserRole: async (_userId, input) => ({
      ...member,
      role: input.role,
      version: 3,
    }),
    disableUser: async () => ({ ...member, status: 'disabled', version: 3 }),
    enableUser: async () => ({ ...member, status: 'active', version: 4 }),
    createPasswordReset: async () => ({
      resetId: 'reset-1',
      resetUrl: '/reset-password?token=reset-token',
      expiresAt: '2026-08-22T08:00:00Z',
    }),
    listAuditEvents: async () => ({
      items: [{
        eventId: 'audit-1',
        action: 'user.disabled',
        actorEmail: 'owner@example.com',
        targetEmail: 'member@example.com',
        reason: '内测资格暂停',
        occurredAt: '2026-08-21T04:00:00Z',
      }],
      nextCursor: null,
    }),
    consumePasswordReset: async () => undefined,
    ...overrides,
  }
}

describe('AdminUsersPage', () => {
  it('generates a configurable batch of credit redemption codes', async () => {
    const createCreditRedemptionCodes = vi.fn(async () => ({
      codes: [
        'QX-7KDM-4XJP-9TWR-P6AC',
        'QX-J4NR-W8CY-T2PH-6VKA',
      ],
      points: 3000,
      expiresAt: '2026-09-22T23:59:59Z',
    }))
    render(<AdminUsersPage api={createApi({ createCreditRedemptionCodes })} />)

    await screen.findByRole('heading', { name: '用户管理' })
    expect(screen.getByText('批量生成一次性兑换码，兑换后积分恢复至 10,000。')).toBeVisible()
    fireEvent.change(screen.getByLabelText('生成数量'), { target: { value: '20' } })
    fireEvent.change(screen.getByLabelText('有效天数'), { target: { value: '30' } })
    fireEvent.click(screen.getByRole('button', { name: '生成兑换码' }))

    await waitFor(() => expect(createCreditRedemptionCodes).toHaveBeenCalledWith({
      count: 20,
      expiresInDays: 30,
      idempotencyKey: expect.any(String),
    }))
    expect(await screen.findByText('QX-7KDM-4XJP-9TWR-P6AC')).toBeVisible()
    expect(screen.getByText('完整兑换码只显示在这里，请立即复制保存。')).toBeVisible()
  })

  it('marks the fixed administrator and does not expose lifecycle controls for it', async () => {
    render(<AdminUsersPage api={createApi()} />)

    const row = await screen.findByRole('row', { name: /owner@example.com/ })
    expect(within(row).getByText('部署管理员')).toBeVisible()
    expect(within(row).getByLabelText('owner@example.com 的角色')).toBeDisabled()
    expect(within(row).queryByRole('button', { name: '禁用 owner@example.com' })).not.toBeInTheDocument()
  })

  it('recovers from a failed directory load and gives an empty result a next action', async () => {
    let attempt = 0
    const api = createApi({
      listAdminUsers: async () => {
        attempt += 1
        if (attempt === 1) throw new Error('network unavailable')
        return { items: [], total: 0, nextCursor: null }
      },
    })
    render(<AdminUsersPage api={api} />)

    expect(screen.getByRole('status')).toHaveTextContent('正在读取用户目录')
    const error = await screen.findByRole('alert')
    expect(error).toHaveTextContent('暂时无法读取用户目录')
    fireEvent.click(within(error).getByRole('button', { name: '重试' }))

    expect(await screen.findByRole('heading', { name: '还没有匹配的用户' })).toBeVisible()
    expect(screen.getByText(/等待新的内测用户完成注册/)).toBeVisible()
  })

  it('searches through the server boundary and renders only the returned member', async () => {
    const listAdminUsers = vi.fn(async ({ query }: { query?: string }) => ({
      items: query ? [member] : [admin, member],
      total: query ? 1 : 2,
      nextCursor: null,
    }))
    render(<AdminUsersPage api={createApi({ listAdminUsers })} />)

    await screen.findByRole('row', { name: /member@example.com/ })
    fireEvent.change(screen.getByRole('searchbox', { name: '搜索用户' }), {
      target: { value: 'member' },
    })
    fireEvent.click(screen.getByRole('button', { name: '搜索' }))

    await waitFor(() => expect(listAdminUsers).toHaveBeenLastCalledWith({ query: 'member' }))
    expect(screen.getByRole('row', { name: /member@example.com/ })).toBeVisible()
    expect(screen.queryByRole('row', { name: /owner@example.com/ })).not.toBeInTheDocument()
    expect(screen.getByText('1 位用户')).toBeVisible()
  })

  it('requires a focused, escapable confirmation before disabling a user', async () => {
    const disableUser = vi.fn(async () => ({ ...member, status: 'disabled' as const, version: 3 }))
    const listAuditEvents = vi.fn(async () => ({
      items: [],
      nextCursor: null,
    }))
    render(<AdminUsersPage api={createApi({ disableUser, listAuditEvents })} />)

    const trigger = await screen.findByRole('button', { name: '禁用 member@example.com' })
    fireEvent.click(trigger)
    const dialog = screen.getByRole('dialog', { name: '禁用这位用户？' })
    expect(dialog).toHaveTextContent('立即终止其所有活跃会话')
    expect(within(dialog).getByRole('button', { name: '取消' })).toHaveFocus()
    fireEvent.keyDown(dialog, { key: 'Escape' })
    expect(trigger).toHaveFocus()

    fireEvent.click(trigger)
    const reopened = screen.getByRole('dialog', { name: '禁用这位用户？' })
    fireEvent.change(within(reopened).getByLabelText('原因'), {
      target: { value: '内测资格暂停' },
    })
    fireEvent.click(within(reopened).getByRole('button', { name: '确认禁用' }))

    await waitFor(() => expect(disableUser).toHaveBeenCalledWith('user-2', {
      expectedVersion: 2,
      reason: '内测资格暂停',
      idempotencyKey: expect.any(String),
    }))
    expect(within(screen.getByRole('row', { name: /member@example.com/ })).getByText('已禁用')).toBeVisible()
    expect(screen.getByRole('button', { name: '启用 member@example.com' })).toBeVisible()
    await waitFor(() => expect(listAuditEvents).toHaveBeenCalledTimes(2))
  })

  it('confirms role changes and creates a bounded password reset link', async () => {
    const updateUserRole = vi.fn(async () => ({ ...member, role: 'admin' as const, version: 3 }))
    const createPasswordReset = vi.fn(async () => ({
      resetId: 'reset-1',
      resetUrl: '/reset-password?token=reset-token',
      expiresAt: '2026-08-22T08:00:00Z',
    }))
    render(<AdminUsersPage api={createApi({ updateUserRole, createPasswordReset })} />)

    const row = await screen.findByRole('row', { name: /member@example.com/ })
    fireEvent.change(within(row).getByLabelText('member@example.com 的角色'), {
      target: { value: 'admin' },
    })
    fireEvent.click(within(row).getByRole('button', { name: '保存 member@example.com 的角色' }))
    const roleDialog = screen.getByRole('dialog', { name: '将角色更改为管理员？' })
    fireEvent.change(within(roleDialog).getByLabelText('变更原因'), {
      target: { value: '负责内测用户' },
    })
    fireEvent.click(within(roleDialog).getByRole('button', { name: '确认更改角色' }))
    await waitFor(() => expect(updateUserRole).toHaveBeenCalledWith('user-2', {
      role: 'admin',
      expectedVersion: 2,
      reason: '负责内测用户',
      idempotencyKey: expect.any(String),
    }))

    const updatedRow = screen.getByRole('row', { name: /member@example.com/ })
    fireEvent.click(within(updatedRow).getByRole('button', { name: '为 member@example.com 创建密码重置链接' }))
    const resetDialog = screen.getByRole('dialog', { name: '创建密码重置链接？' })
    fireEvent.click(within(resetDialog).getByRole('button', { name: '确认创建' }))

    await waitFor(() => expect(createPasswordReset).toHaveBeenCalledWith(
      'user-2',
      { idempotencyKey: expect.any(String) },
    ))
    expect(await screen.findByRole('link', { name: 'member@example.com 的密码重置链接' })).toHaveAttribute(
      'href',
      '/reset-password?token=reset-token',
    )
  })
})
