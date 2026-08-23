import {
  ClockCounterClockwiseIcon,
  MagnifyingGlassIcon,
  UsersThreeIcon,
  WarningIcon,
} from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'

import { accountManagementApi } from './accountManagementApi'
import {
  AccountManagementRequestError,
  type AccountAuditEvent,
  type AccountManagementApi,
  type AccountRole,
  type AccountStatus,
  type AdminUser,
  type CreditRedemptionCodeBatch,
  type PasswordResetLink,
} from './accountManagementModels'
import { AccountConfirmationDialog } from './AccountSettingsPage'
import { MutationIntentLedger } from './mutationIntent'
import './account-management.css'

type AdminUsersPageProps = {
  api?: AccountManagementApi
  settingsHref?: string
  onForbidden?(): void
  onSessionExpired?(): void
}

type DirectoryState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; users: AdminUser[]; total: number; nextCursor: string | null }

type StatusDialog = {
  user: AdminUser
  nextStatus: Extract<AccountStatus, 'active' | 'disabled'>
}

type RoleDialog = {
  user: AdminUser
  nextRole: AccountRole
}

function formatDate(value: string | null) {
  if (!value) return '尚未登录'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const auditLabels: Record<string, string> = {
  'admin.access': '管理员权限校验',
  'admin.provisioned': '部署管理员初始化',
  'profile.updated': '更新个人资料',
  'preferences.updated': '更新使用偏好',
  'model_secondary_use.granted': '开启模型改进授权',
  'model_secondary_use.withdrawn': '撤回模型改进授权',
  'session.revoked': '撤销登录会话',
  'password.changed': '更新账户密码',
  'user.disabled': '禁用用户',
  'user.enabled': '启用用户',
  'user.role_changed': '变更角色',
  'password_reset.issued': '创建密码重置',
  'password_reset.consumed': '完成密码重置',
  'data_export.created': '生成个人数据副本',
  'account.deactivated': '停用账户',
  'account.deleted': '永久删除账户',
}

export function AdminUsersPage({
  api = accountManagementApi,
  settingsHref = '/settings',
  onForbidden,
  onSessionExpired,
}: AdminUsersPageProps) {
  const [query, setQuery] = useState('')
  const [submittedQuery, setSubmittedQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<AccountStatus | ''>('')
  const [reloadToken, setReloadToken] = useState(0)
  const [auditReloadToken, setAuditReloadToken] = useState(0)
  const [directory, setDirectory] = useState<DirectoryState>({ status: 'loading' })
  const [auditEvents, setAuditEvents] = useState<AccountAuditEvent[]>([])
  const [roleSelections, setRoleSelections] = useState<Record<string, AccountRole>>({})
  const [roleDialog, setRoleDialog] = useState<RoleDialog | null>(null)
  const [roleReason, setRoleReason] = useState('')
  const [statusDialog, setStatusDialog] = useState<StatusDialog | null>(null)
  const [statusReason, setStatusReason] = useState('')
  const [resetUser, setResetUser] = useState<AdminUser | null>(null)
  const [resetLinks, setResetLinks] = useState<Record<string, PasswordResetLink>>({})
  const [creditCodeCount, setCreditCodeCount] = useState(20)
  const [creditCodeExpiresInDays, setCreditCodeExpiresInDays] = useState(30)
  const [generatedCreditCodes, setGeneratedCreditCodes] = useState<CreditRedemptionCodeBatch | null>(null)
  const [pendingAction, setPendingAction] = useState<string | null>(null)
  const pendingRef = useRef<string | null>(null)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const mutationIntents = useRef(new MutationIntentLedger())
  const rowTriggerRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    let active = true
    setDirectory({ status: 'loading' })
    const input = {
      ...(submittedQuery ? { query: submittedQuery } : {}),
      ...(statusFilter ? { status: statusFilter } : {}),
    }
    api.listAdminUsers(input)
      .then((page) => {
        if (!active) return
        setDirectory({
          status: 'ready',
          users: page.items,
          total: page.total,
          nextCursor: page.nextCursor,
        })
        setRoleSelections(Object.fromEntries(
          page.items.map((user) => [user.userId, user.role]),
        ))
      })
      .catch((failure: unknown) => {
        if (!active) return
        handleBoundaryFailure(failure)
        setDirectory({ status: 'error' })
      })
    return () => {
      active = false
    }
  }, [api, submittedQuery, statusFilter, reloadToken])

  useEffect(() => {
    let active = true
    api.listAuditEvents({ limit: 8 })
      .then((page) => {
        if (active) setAuditEvents(page.items)
      })
      .catch(() => {
        if (active) setAuditEvents([])
      })
    return () => {
      active = false
    }
  }, [api, auditReloadToken])

  function handleBoundaryFailure(failure: unknown) {
    if (!(failure instanceof AccountManagementRequestError)) return
    if (failure.status === 401) onSessionExpired?.()
    if (failure.status === 403) onForbidden?.()
  }

  function actionFailureMessage(failure: unknown) {
    handleBoundaryFailure(failure)
    if (failure instanceof AccountManagementRequestError) {
      if (failure.status === 409) {
        return failure.message
      }
      if (failure.status === 401) return '登录已过期，请重新登录。'
      if (failure.status === 403) return '当前账户没有管理员权限。'
    }
    return '操作未完成。当前目录没有改变，请检查网络后重试。'
  }

  function replaceUser(updated: AdminUser) {
    setDirectory((state) => state.status === 'ready'
      ? {
          ...state,
          users: state.users.map((user) => user.userId === updated.userId ? updated : user),
        }
      : state)
    setRoleSelections((values) => ({ ...values, [updated.userId]: updated.role }))
  }

  async function perform<T>(
    action: string,
    operation: () => Promise<T>,
    onSuccess: (result: T) => void,
    message: string,
  ) {
    if (pendingRef.current) return
    pendingRef.current = action
    setPendingAction(action)
    setFeedback(null)
    setActionError(null)
    try {
      const result = await operation()
      mutationIntents.current.complete(action)
      onSuccess(result)
      setAuditReloadToken((token) => token + 1)
      setFeedback(message)
    } catch (failure) {
      setActionError(actionFailureMessage(failure))
    } finally {
      pendingRef.current = null
      setPendingAction(null)
    }
  }

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmittedQuery(query.trim())
  }

  function submitCreditCodeBatch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const intent = {
      count: creditCodeCount,
      expiresInDays: creditCodeExpiresInDays,
    }
    void perform(
      'credit-code-batch',
      () => api.createCreditRedemptionCodes({
        ...intent,
        idempotencyKey: mutationIntents.current.keyFor('credit-code-batch', intent),
      }),
      setGeneratedCreditCodes,
      `已生成 ${creditCodeCount} 个积分兑换码。`,
    )
  }

  if (directory.status === 'loading') {
    return (
      <section className="account-management-state account-management-state--loading" role="status" aria-live="polite">
        <span className="account-management-state__line" />
        <span className="account-management-state__line" />
        <span className="account-management-state__line" />
        <p>正在读取用户目录</p>
      </section>
    )
  }

  if (directory.status === 'error') {
    return (
      <section className="account-management-state" role="alert">
        <span className="account-management-state__icon" aria-hidden="true">
          <WarningIcon size={20} />
        </span>
        <h2>暂时无法读取用户目录</h2>
        <p>没有任何角色或账户状态被改变。</p>
        <button
          className="account-management-button"
          type="button"
          onClick={() => setReloadToken((value) => value + 1)}
        >
          重试
        </button>
      </section>
    )
  }

  const pending = pendingAction !== null

  return (
    <article className="account-management-page account-admin-page">
      <header className="account-management-hero account-admin-hero">
        <div>
          <p className="account-management-eyebrow">PRIVATE BETA ROSTER</p>
          <h1>用户管理</h1>
          <p>管理内测用户的资格、权限与账户恢复。</p>
        </div>
        <div className="account-admin-summary" aria-label="目录摘要">
          <span aria-hidden="true"><UsersThreeIcon size={21} /></span>
          <strong>{directory.total}</strong>
          <small>位内测用户</small>
        </div>
        <a className="account-management-admin-link" href={settingsHref}>返回账户设置</a>
      </header>

      {feedback ? <p className="account-management-feedback" role="status">{feedback}</p> : null}
      {actionError ? <p className="account-management-alert" role="alert">{actionError}</p> : null}

      <section className="account-admin-credit-codes" aria-labelledby="credit-code-generator-title">
        <header>
          <div>
            <p className="account-management-eyebrow">PRIVATE BETA CREDITS</p>
            <h2 id="credit-code-generator-title">积分兑换码</h2>
            <p>批量生成一次性兑换码，兑换后积分恢复至 3,000。</p>
          </div>
        </header>
        <form className="account-admin-credit-code-form" onSubmit={submitCreditCodeBatch}>
          <label>
            <span>生成数量</span>
            <input
              type="number"
              min={1}
              max={100}
              value={creditCodeCount}
              onChange={(event) => setCreditCodeCount(Number(event.target.value))}
            />
          </label>
          <label>
            <span>有效天数</span>
            <input
              type="number"
              min={1}
              max={365}
              value={creditCodeExpiresInDays}
              onChange={(event) => setCreditCodeExpiresInDays(Number(event.target.value))}
            />
          </label>
          <button
            className="account-management-button account-management-button--primary"
            type="submit"
            disabled={pending
              || creditCodeCount < 1
              || creditCodeExpiresInDays < 1}
          >
            {pendingAction === 'credit-code-batch' ? '正在生成…' : '生成兑换码'}
          </button>
        </form>
        {generatedCreditCodes ? (
          <div className="account-admin-credit-code-result">
            <p>完整兑换码只显示在这里，请立即复制保存。</p>
            <small>
              兑换后恢复至 {generatedCreditCodes.points.toLocaleString('zh-CN')} 积分 ·
              有效至 {formatDate(generatedCreditCodes.expiresAt)}
            </small>
            <ol>
              {generatedCreditCodes.codes.map((code) => <li key={code}><code>{code}</code></li>)}
            </ol>
          </div>
        ) : null}
      </section>

      <section className="account-admin-toolbar" aria-label="用户目录工具">
        <form className="account-admin-search" role="search" onSubmit={submitSearch}>
          <label>
            <span className="sr-only">搜索用户</span>
            <MagnifyingGlassIcon size={17} aria-hidden="true" />
            <input
              type="search"
              aria-label="搜索用户"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索姓名或邮箱"
            />
          </label>
          <select
            aria-label="筛选账户状态"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as AccountStatus | '')}
          >
            <option value="">全部状态</option>
            <option value="active">活跃</option>
            <option value="disabled">已禁用</option>
            <option value="deactivated">已停用</option>
          </select>
          <button className="account-management-button" type="submit">搜索</button>
        </form>
      </section>

      <section className="account-admin-directory" aria-labelledby="account-directory-title">
        <header>
          <div>
            <p className="account-management-eyebrow">ACCESS DIRECTORY</p>
            <h2 id="account-directory-title">内测名册</h2>
          </div>
          <span>{directory.total} 位用户</span>
        </header>

        {directory.users.length === 0 ? (
          <div className="account-admin-empty">
            <UsersThreeIcon size={24} aria-hidden="true" />
            <h3>还没有匹配的用户</h3>
            <p>调整搜索条件，或等待新的内测用户完成注册。</p>
          </div>
        ) : (
          <div className="account-admin-table-wrap">
            <table className="account-admin-table">
              <thead>
                <tr>
                  <th scope="col">用户</th>
                  <th scope="col">角色</th>
                  <th scope="col">状态</th>
                  <th scope="col">最近活动</th>
                  <th scope="col"><span className="sr-only">操作</span></th>
                </tr>
              </thead>
              <tbody>
                {directory.users.map((user) => {
                  const selectedRole = roleSelections[user.userId] ?? user.role
                  const resetLink = resetLinks[user.userId]
                  return (
                    <tr key={user.userId}>
                      <td>
                        <strong>{user.displayName ?? '未设置名称'}</strong>
                        <span>{user.email}</span>
                        {user.isCurrentUser ? <small>当前账户</small> : null}
                        {user.isProtectedAdmin ? (
                          <small className="account-admin-protected">部署管理员</small>
                        ) : null}
                      </td>
                      <td>
                        <div className="account-admin-role-control">
                          <select
                            aria-label={`${user.email} 的角色`}
                            value={selectedRole}
                            disabled={pending || user.isProtectedAdmin}
                            onChange={(event) => setRoleSelections((values) => ({
                              ...values,
                              [user.userId]: event.target.value as AccountRole,
                            }))}
                          >
                            <option value="member">内测用户</option>
                            <option value="admin">管理员</option>
                          </select>
                          <button
                            className="account-management-button account-management-button--quiet"
                            type="button"
                            aria-label={`保存 ${user.email} 的角色`}
                            disabled={pending || user.isProtectedAdmin || selectedRole === user.role}
                            onClick={(event) => {
                              rowTriggerRef.current = event.currentTarget
                              setRoleReason('')
                              setRoleDialog({ user, nextRole: selectedRole })
                            }}
                          >
                            保存
                          </button>
                        </div>
                      </td>
                      <td>
                        <span className={`account-status account-status--${user.status}`}>
                          {user.status === 'active' ? '活跃' : user.status === 'disabled' ? '已禁用' : '已停用'}
                        </span>
                      </td>
                      <td>{formatDate(user.lastActiveAt)}</td>
                      <td>
                        <div className="account-admin-actions">
                          {!user.isProtectedAdmin && user.status === 'active' ? (
                            <button
                              className="account-management-button account-management-button--quiet"
                              type="button"
                              aria-label={`禁用 ${user.email}`}
                              disabled={pending || user.isCurrentUser}
                              onClick={(event) => {
                                rowTriggerRef.current = event.currentTarget
                                setStatusReason('')
                                setStatusDialog({ user, nextStatus: 'disabled' })
                              }}
                            >禁用</button>
                          ) : !user.isProtectedAdmin ? (
                            <button
                              className="account-management-button account-management-button--quiet"
                              type="button"
                              aria-label={`启用 ${user.email}`}
                              disabled={pending}
                              onClick={(event) => {
                                rowTriggerRef.current = event.currentTarget
                                setStatusReason('恢复内测资格')
                                setStatusDialog({ user, nextStatus: 'active' })
                              }}
                            >启用</button>
                          ) : null}
                          <button
                            className="account-management-button account-management-button--quiet"
                            type="button"
                            aria-label={`为 ${user.email} 创建密码重置链接`}
                            disabled={pending || user.status !== 'active'}
                            onClick={(event) => {
                              rowTriggerRef.current = event.currentTarget
                              setResetUser(user)
                            }}
                          >重置密码</button>
                        </div>
                        {resetLink?.resetUrl ? (
                          <a className="account-admin-reset-link" href={resetLink.resetUrl}>
                            {user.email} 的密码重置链接
                          </a>
                        ) : null}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="account-admin-audit" aria-labelledby="account-audit-title">
        <header>
          <span aria-hidden="true"><ClockCounterClockwiseIcon size={19} /></span>
          <div>
            <h2 id="account-audit-title">最近审计记录</h2>
            <p>角色、资格与账户恢复操作都会在服务端留痕。</p>
          </div>
        </header>
        {auditEvents.length ? (
          <ol>
            {auditEvents.map((event) => (
              <li key={event.eventId}>
                <span className={`account-audit-outcome account-audit-outcome--${event.outcome ?? 'succeeded'}`} />
                <div>
                  <strong>{auditLabels[event.action] ?? event.action}</strong>
                  <p>{event.actorEmail ?? '系统'} → {event.targetEmail ?? '账户域'}</p>
                </div>
                <span>{event.reason ?? '未填写原因'} · {formatDate(event.occurredAt)}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="account-settings-empty">还没有可显示的审计记录。</p>
        )}
      </section>

      {roleDialog ? (
        <AccountConfirmationDialog
          title={`将角色更改为${roleDialog.nextRole === 'admin' ? '管理员' : '内测用户'}？`}
          description={roleDialog.nextRole === 'admin'
            ? '管理员可以禁用和更改其他用户。请只授予可信的内测负责人。'
            : '移除管理员权限后，该用户将只能管理自己的账户与研究数据。'}
          confirmLabel="确认更改角色"
          pending={pendingAction === 'role'}
          confirmDisabled={roleReason.trim().length < 3}
          error={actionError}
          triggerRef={rowTriggerRef}
          onCancel={() => setRoleDialog(null)}
          onConfirm={() => {
            const intent = {
              role: roleDialog.nextRole,
              expectedVersion: roleDialog.user.version,
              reason: roleReason.trim(),
            }
            void perform(
              'role',
              () => api.updateUserRole(roleDialog.user.userId, {
                ...intent,
                idempotencyKey: mutationIntents.current.keyFor(
                  `role:${roleDialog.user.userId}`,
                  intent,
                ),
              }),
              (updated) => {
                mutationIntents.current.complete(`role:${roleDialog.user.userId}`)
                replaceUser(updated)
                setRoleDialog(null)
              },
              '角色已更新。',
            )
          }}
        >
          <label className="account-dialog-field">
            <span>变更原因</span>
            <textarea value={roleReason} onChange={(event) => setRoleReason(event.target.value)} maxLength={240} rows={3} />
          </label>
        </AccountConfirmationDialog>
      ) : null}

      {statusDialog ? (
        <AccountConfirmationDialog
          title={statusDialog.nextStatus === 'active' ? '启用这位用户？' : '禁用这位用户？'}
          description={statusDialog.nextStatus === 'active'
            ? '用户可以重新登录；已撤销的旧会话不会恢复。'
            : '禁用会立即终止其所有活跃会话，但保留研究数据以便恢复。'}
          confirmLabel={statusDialog.nextStatus === 'active' ? '确认启用' : '确认禁用'}
          pending={pendingAction === 'status'}
          confirmDisabled={statusReason.trim().length < 3}
          error={actionError}
          tone={statusDialog.nextStatus === 'disabled' ? 'danger' : 'default'}
          triggerRef={rowTriggerRef}
          onCancel={() => setStatusDialog(null)}
          onConfirm={() => {
            const intent = {
              expectedVersion: statusDialog.user.version,
              reason: statusReason.trim(),
            }
            const method = statusDialog.nextStatus === 'active'
              ? api.enableUser
              : api.disableUser
            const keyName = `${statusDialog.nextStatus}:${statusDialog.user.userId}`
            void perform(
              'status',
              () => method(statusDialog.user.userId, {
                ...intent,
                idempotencyKey: mutationIntents.current.keyFor(keyName, intent),
              }),
              (updated) => {
                mutationIntents.current.complete(keyName)
                replaceUser(updated)
                setStatusDialog(null)
              },
              statusDialog.nextStatus === 'active' ? '用户已启用。' : '用户已禁用。',
            )
          }}
        >
          <label className="account-dialog-field">
            <span>原因</span>
            <textarea value={statusReason} onChange={(event) => setStatusReason(event.target.value)} maxLength={240} rows={3} />
          </label>
        </AccountConfirmationDialog>
      ) : null}

      {resetUser ? (
        <AccountConfirmationDialog
          title="创建密码重置链接？"
          description="新链接一小时内有效且只能使用一次。创建新链接会使此前未使用的链接失效。"
          confirmLabel="确认创建"
          pending={pendingAction === 'reset'}
          error={actionError}
          triggerRef={rowTriggerRef}
          onCancel={() => setResetUser(null)}
          onConfirm={() => {
            const keyName = `reset:${resetUser.userId}`
            void perform(
              'reset',
              () => api.createPasswordReset(resetUser.userId, {
                idempotencyKey: mutationIntents.current.keyFor(keyName, { userId: resetUser.userId }),
              }),
              (link) => {
                mutationIntents.current.complete(keyName)
                setResetLinks((links) => ({ ...links, [resetUser.userId]: link }))
                setResetUser(null)
              },
              '密码重置链接已创建，只显示这一次。',
            )
          }}
        />
      ) : null}
    </article>
  )
}
