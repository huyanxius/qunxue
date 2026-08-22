import {
  BellIcon,
  DatabaseIcon,
  DownloadSimpleIcon,
  LockKeyIcon,
  MonitorIcon,
  PowerIcon,
  ShieldCheckIcon,
  TrashIcon,
  UserCircleIcon,
  WarningIcon,
} from '@phosphor-icons/react'
import { useEffect, useId, useRef, useState } from 'react'
import type {
  FormEvent,
  MutableRefObject,
  ReactNode,
} from 'react'

import {
  isAccountManagementRequestError,
  type AccountManagementApi,
  type AccountProfile,
  type AccountSession,
  type PersonalDataExport,
} from './accountManagementModels'
import { accountManagementApi } from './accountManagementApi'
import { MutationIntentLedger } from './mutationIntent'
import './account-management.css'

const dialogFocusableSelector = [
  'button:not([disabled])',
  'a[href]',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

type ConfirmationDialogProps = {
  title: string
  description: string
  confirmLabel: string
  pendingLabel?: string
  pending: boolean
  confirmDisabled?: boolean
  tone?: 'default' | 'danger'
  error?: string | null
  triggerRef: MutableRefObject<HTMLElement | null>
  children?: ReactNode
  onCancel(): void
  onConfirm(): void
}

export function AccountConfirmationDialog({
  title,
  description,
  confirmLabel,
  pendingLabel = '正在处理…',
  pending,
  confirmDisabled = false,
  tone = 'default',
  error,
  triggerRef,
  children,
  onCancel,
  onConfirm,
}: ConfirmationDialogProps) {
  const titleId = useId()
  const descriptionId = useId()
  const dialogRef = useRef<HTMLElement | null>(null)
  const cancelRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    cancelRef.current?.focus()

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && !pending) {
        event.preventDefault()
        onCancel()
        return
      }
      if (event.key !== 'Tab') return

      const dialog = dialogRef.current
      if (!dialog) return
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(dialogFocusableSelector),
      )
      if (focusable.length === 0) {
        event.preventDefault()
        dialog.focus()
        return
      }
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      const trigger = triggerRef.current
      if (trigger && document.contains(trigger)) trigger.focus()
    }
  }, [onCancel, pending, triggerRef])

  return (
    <div className="account-dialog-backdrop">
      <section
        className={`account-dialog account-dialog--${tone}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        ref={dialogRef}
        tabIndex={-1}
      >
        <span className="account-dialog__mark" aria-hidden="true">
          {tone === 'danger'
            ? <WarningIcon size={20} weight="regular" />
            : <ShieldCheckIcon size={20} weight="regular" />}
        </span>
        <h2 id={titleId}>{title}</h2>
        <p id={descriptionId}>{description}</p>
        {children ? <div className="account-dialog__body">{children}</div> : null}
        {error ? <p className="account-management-alert" role="alert">{error}</p> : null}
        <div className="account-dialog__actions">
          <button
            className="account-management-button"
            type="button"
            disabled={pending}
            ref={cancelRef}
            onClick={onCancel}
          >
            取消
          </button>
          <button
            className={`account-management-button ${tone === 'danger' ? 'account-management-button--danger' : 'account-management-button--primary'}`}
            type="button"
            disabled={pending || confirmDisabled}
            onClick={onConfirm}
          >
            {pending ? pendingLabel : confirmLabel}
          </button>
        </div>
      </section>
    </div>
  )
}

type AccountSettingsPageProps = {
  api?: AccountManagementApi
  adminHref?: string
  onSessionExpired?(): void
  onAccountDeactivated?(): void
  onAccountDeleted?(): void
}

type LoadState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; account: AccountProfile; sessions: AccountSession[] }

function formattedDate(value: string | null) {
  if (!value) return '暂无记录'
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

export function AccountSettingsPage({
  api = accountManagementApi,
  adminHref = '/admin/users',
  onSessionExpired,
  onAccountDeactivated,
  onAccountDeleted,
}: AccountSettingsPageProps) {
  const [reloadToken, setReloadToken] = useState(0)
  const mutationIntents = useRef(new MutationIntentLedger())
  const [loadState, setLoadState] = useState<LoadState>({ status: 'loading' })
  const [displayName, setDisplayName] = useState('')
  const [locale, setLocale] = useState('zh-CN')
  const [timezone, setTimezone] = useState('Asia/Shanghai')
  const [researchUpdatesEnabled, setResearchUpdatesEnabled] = useState(true)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [passwordConfirmation, setPasswordConfirmation] = useState('')
  const [revokeOtherSessions, setRevokeOtherSessions] = useState(true)
  const [pendingAction, setPendingAction] = useState<string | null>(null)
  const pendingActionRef = useRef<string | null>(null)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [dataExport, setDataExport] = useState<PersonalDataExport | null>(null)
  const [sessionToRevoke, setSessionToRevoke] = useState<AccountSession | null>(null)
  const [modelAuthorizationTarget, setModelAuthorizationTarget] = useState<boolean | null>(null)
  const [deactivationOpen, setDeactivationOpen] = useState(false)
  const [deactivationPassword, setDeactivationPassword] = useState('')
  const [deactivationReason, setDeactivationReason] = useState('')
  const [deletionOpen, setDeletionOpen] = useState(false)
  const [deletionPassword, setDeletionPassword] = useState('')
  const [deletionEmail, setDeletionEmail] = useState('')
  const sessionTriggerRef = useRef<HTMLElement | null>(null)
  const modelTriggerRef = useRef<HTMLElement | null>(null)
  const deactivateTriggerRef = useRef<HTMLElement | null>(null)
  const deleteTriggerRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    let active = true
    setLoadState({ status: 'loading' })
    Promise.all([api.getAccount(), api.listSessions()])
      .then(([account, sessions]) => {
        if (!active) return
        setLoadState({ status: 'ready', account, sessions })
        setDisplayName(account.displayName ?? '')
        setLocale(account.preferences.locale)
        setTimezone(account.preferences.timezone)
        setResearchUpdatesEnabled(account.preferences.researchUpdatesEnabled)
      })
      .catch((failure: unknown) => {
        if (!active) return
        if (isAccountManagementRequestError(failure) && failure.status === 401) {
          onSessionExpired?.()
        }
        setLoadState({ status: 'error' })
      })
    return () => {
      active = false
    }
  }, [api, onSessionExpired, reloadToken])

  function replaceAccount(account: AccountProfile) {
    setLoadState((state) => state.status === 'ready'
      ? { ...state, account }
      : state)
  }

  function replaceSessions(update: (sessions: AccountSession[]) => AccountSession[]) {
    setLoadState((state) => state.status === 'ready'
      ? { ...state, sessions: update(state.sessions) }
      : state)
  }

  function failureMessage(failure: unknown) {
    if (isAccountManagementRequestError(failure)) {
      if (failure.status === 401) {
        onSessionExpired?.()
        return '登录已过期，请重新登录后继续。'
      }
      if (failure.status === 409) {
        return failure.message
      }
    }
    return '操作未完成，已保留当前数据。请检查网络后重试。'
  }

  async function perform<T>(
    action: string,
    operation: () => Promise<T>,
    onSuccess: (result: T) => void,
    successMessage: string | ((result: T) => string),
  ) {
    if (pendingActionRef.current) return
    pendingActionRef.current = action
    setPendingAction(action)
    setActionError(null)
    setFeedback(null)
    try {
      const result = await operation()
      mutationIntents.current.complete(action)
      onSuccess(result)
      setFeedback(typeof successMessage === 'function' ? successMessage(result) : successMessage)
    } catch (failure) {
      setActionError(failureMessage(failure))
    } finally {
      pendingActionRef.current = null
      setPendingAction(null)
    }
  }

  if (loadState.status === 'loading') {
    return (
      <section className="account-management-state account-management-state--loading" role="status" aria-live="polite">
        <span className="account-management-state__line" />
        <span className="account-management-state__line" />
        <span className="account-management-state__line" />
        <p>正在读取账户设置</p>
      </section>
    )
  }

  if (loadState.status === 'error') {
    return (
      <section className="account-management-state" role="alert">
        <span className="account-management-state__icon" aria-hidden="true">
          <WarningIcon size={20} weight="regular" />
        </span>
        <h2>暂时无法读取账户设置</h2>
        <p>你的账户与研究数据没有改变。请检查网络后重试。</p>
        <button className="account-management-button" type="button" onClick={() => setReloadToken((value) => value + 1)}>
          重试
        </button>
      </section>
    )
  }

  const { account, sessions } = loadState
  const otherSessions = sessions.filter((session) => !session.current)
  const pending = pendingAction !== null

  function submitProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalizedName = displayName.trim()
    if (!normalizedName || normalizedName.length > 80) {
      setActionError('显示名称需要 1-80 个字符。')
      return
    }
    void perform(
      'profile',
      () => {
        const intent = { displayName: normalizedName, expectedVersion: account.version }
        return api.updateProfile({
          ...intent,
          idempotencyKey: mutationIntents.current.keyFor('profile', intent),
        })
      },
      (updated) => {
        replaceAccount(updated)
        setDisplayName(updated.displayName ?? '')
      },
      '资料已保存。',
    )
  }

  function submitPreferences(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void perform(
      'preferences',
      () => {
        const intent = {
          locale,
          timezone,
          researchUpdatesEnabled,
          expectedVersion: account.preferences.version,
        }
        return api.updatePreferences({
          ...intent,
          idempotencyKey: mutationIntents.current.keyFor('preferences', intent),
        })
      },
      (preferences) => replaceAccount({ ...account, preferences }),
      '偏好已保存。',
    )
  }

  function submitPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (newPassword.length < 12 || newPassword.length > 128) {
      setActionError('新密码需要 12-128 个字符。')
      return
    }
    if (newPassword !== passwordConfirmation) {
      setActionError('两次输入的新密码不一致。')
      return
    }
    void perform(
      'password',
      () => {
        const intent = { currentPassword, newPassword, revokeOtherSessions }
        return api.changePassword({
          ...intent,
          idempotencyKey: mutationIntents.current.keyFor('password', intent),
        })
      },
      () => {
        setCurrentPassword('')
        setNewPassword('')
        setPasswordConfirmation('')
        if (revokeOtherSessions) replaceSessions((items) => items.filter((item) => item.current))
      },
      ({ revokedSessionCount }) => `密码已更新，已撤销 ${revokedSessionCount} 个其他会话。`,
    )
  }

  return (
    <article className="account-management-page">
      <header className="account-management-hero">
        <div>
          <p className="account-management-eyebrow">ACCOUNT LEDGER</p>
          <h1>账户设置</h1>
          <p>管理你的身份、安全与研究数据使用边界。</p>
        </div>
        <div className="account-management-identity">
          <span aria-hidden="true"><UserCircleIcon size={21} weight="regular" /></span>
          <div>
            <strong>{account.displayName ?? '研究者'}</strong>
            <small>{account.email}</small>
          </div>
          <span className="account-management-badge">
            {account.role === 'admin' ? '管理员' : '内测用户'}
          </span>
        </div>
        {account.role === 'admin' ? (
          <a className="account-management-admin-link" href={adminHref}>
            打开用户管理
          </a>
        ) : null}
      </header>

      <div className="account-management-layout">
        <nav className="account-settings-nav" aria-label="账户设置分区">
          <a href="#account-profile">个人资料</a>
          <a href="#account-preferences">使用偏好</a>
          <a href="#account-security">安全</a>
          <a href="#account-privacy">数据与隐私</a>
          <a href="#account-danger">账户状态</a>
        </nav>

        <div className="account-settings-sections">
          {feedback ? <p className="account-management-feedback" role="status" aria-live="polite">{feedback}</p> : null}
          {actionError ? <p className="account-management-alert" role="alert">{actionError}</p> : null}

          <section className="account-settings-section" id="account-profile" aria-labelledby="account-profile-title">
            <div className="account-settings-section__heading">
              <span aria-hidden="true"><UserCircleIcon size={18} weight="regular" /></span>
              <div>
                <h2 id="account-profile-title">个人资料</h2>
                <p>这些信息会出现在你的研究档案中。</p>
              </div>
            </div>
            <form className="account-management-form account-management-form--inline" onSubmit={submitProfile} noValidate>
              <label>
                <span>显示名称</span>
                <input
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  maxLength={80}
                  autoComplete="name"
                  required
                />
              </label>
              <label>
                <span>邮箱</span>
                <input value={account.email} readOnly aria-describedby="account-email-help" />
                <small id="account-email-help">邮箱用于登录，内测期间如需变更请联系管理员。</small>
              </label>
              <div className="account-management-form__actions">
                <button className="account-management-button account-management-button--primary" type="submit" disabled={pending}>
                  {pendingAction === 'profile' ? '正在保存…' : '保存资料'}
                </button>
              </div>
            </form>
          </section>

          <section className="account-settings-section" id="account-preferences" aria-labelledby="account-preferences-title">
            <div className="account-settings-section__heading">
              <span aria-hidden="true"><BellIcon size={18} weight="regular" /></span>
              <div>
                <h2 id="account-preferences-title">使用偏好</h2>
                <p>设置时区、界面语言与内测进度通知。</p>
              </div>
            </div>
            <form className="account-management-form" onSubmit={submitPreferences}>
              <div className="account-management-form__grid">
                <label>
                  <span>界面语言</span>
                  <select value={locale} onChange={(event) => setLocale(event.target.value)}>
                    <option value="zh-CN">简体中文</option>
                    <option value="en-US">English</option>
                  </select>
                </label>
                <label>
                  <span>时区</span>
                  <select value={timezone} onChange={(event) => setTimezone(event.target.value)}>
                    <option value="Asia/Shanghai">中国标准时间</option>
                    <option value="UTC">协调世界时</option>
                  </select>
                </label>
              </div>
              <label className="account-management-check">
                <input
                  type="checkbox"
                  checked={researchUpdatesEnabled}
                  onChange={(event) => setResearchUpdatesEnabled(event.target.checked)}
                />
                <span>
                  <strong>研究进度与内测通知</strong>
                  <small>仅发送与你的研究或内测资格直接相关的邮件。</small>
                </span>
              </label>
              <div className="account-management-form__actions">
                <button className="account-management-button" type="submit" disabled={pending}>
                  {pendingAction === 'preferences' ? '正在保存…' : '保存偏好'}
                </button>
              </div>
            </form>
          </section>

          <section className="account-settings-section" id="account-security" aria-labelledby="account-security-title">
            <div className="account-settings-section__heading">
              <span aria-hidden="true"><LockKeyIcon size={18} weight="regular" /></span>
              <div>
                <h2 id="account-security-title">安全</h2>
                <p>更新密码，并检查仍然有效的登录会话。</p>
              </div>
            </div>
            <form className="account-management-form" onSubmit={submitPassword} noValidate>
              <div className="account-management-form__grid account-management-form__grid--password">
                <label>
                  <span>当前密码</span>
                  <input
                    type="password"
                    value={currentPassword}
                    onChange={(event) => setCurrentPassword(event.target.value)}
                    autoComplete="current-password"
                    maxLength={128}
                    required
                  />
                </label>
                <label>
                  <span>新密码</span>
                  <input
                    type="password"
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                    autoComplete="new-password"
                    minLength={12}
                    maxLength={128}
                    required
                  />
                </label>
                <label>
                  <span>确认新密码</span>
                  <input
                    type="password"
                    value={passwordConfirmation}
                    onChange={(event) => setPasswordConfirmation(event.target.value)}
                    autoComplete="new-password"
                    minLength={12}
                    maxLength={128}
                    required
                  />
                </label>
              </div>
              <label className="account-management-check">
                <input
                  type="checkbox"
                  checked={revokeOtherSessions}
                  onChange={(event) => setRevokeOtherSessions(event.target.checked)}
                />
                <span>
                  <strong>撤销其他设备的会话</strong>
                  <small>建议保持开启，当前设备不会退出。</small>
                </span>
              </label>
              <div className="account-management-form__actions">
                <button className="account-management-button account-management-button--primary" type="submit" disabled={pending || !currentPassword}>
                  {pendingAction === 'password' ? '正在更新…' : '更新密码'}
                </button>
              </div>
            </form>

            <div className="account-settings-subsection">
              <div className="account-settings-subsection__heading">
                <div>
                  <h3>活跃会话</h3>
                  <p>如果不认识某个设备，立即撤销它的访问。</p>
                </div>
                <span>{sessions.length} 个会话</span>
              </div>
              <div className="account-session-list">
                {sessions.map((session) => (
                  <article className="account-session" key={session.sessionId}>
                    <span className="account-session__icon" aria-hidden="true">
                      <MonitorIcon size={18} weight="regular" />
                    </span>
                    <div>
                      <h4>{session.deviceLabel}</h4>
                      <p>最后活动 {formattedDate(session.lastSeenAt)}{session.ipAddress ? ` · ${session.ipAddress}` : ''}</p>
                    </div>
                    {session.current ? (
                      <span className="account-management-badge account-management-badge--current">当前设备</span>
                    ) : (
                      <button
                        className="account-management-button account-management-button--quiet"
                        type="button"
                        aria-label={`撤销 ${session.deviceLabel} 会话`}
                        disabled={pending}
                        onClick={(event) => {
                          sessionTriggerRef.current = event.currentTarget
                          setActionError(null)
                          setSessionToRevoke(session)
                        }}
                      >
                        撤销
                      </button>
                    )}
                  </article>
                ))}
              </div>
              {otherSessions.length === 0 ? (
                <p className="account-settings-empty">
                  <strong>没有其他活跃会话</strong>
                  <span>。只有你当前的设备保持登录。</span>
                </p>
              ) : null}
            </div>
          </section>

          <section className="account-settings-section" id="account-privacy" aria-labelledby="account-privacy-title">
            <div className="account-settings-section__heading">
              <span aria-hidden="true"><DatabaseIcon size={18} weight="regular" /></span>
              <div>
                <h2 id="account-privacy-title">数据与隐私</h2>
                <p>你可以决定研究数据的二次使用边界，并取回个人数据副本。</p>
              </div>
            </div>
            <div className="account-privacy-row">
              <div>
                <h3>允许用于改进模型</h3>
                <p>群学致知当前不会把你的研究数据用于训练。此开关默认关闭，只记录你对未来可选改进计划的授权；研究功能所需推理不受影响。</p>
                <small>授权政策 {account.preferences.consentPolicyVersion} · 更新于 {formattedDate(account.preferences.consentUpdatedAt)}</small>
              </div>
              <button
                className="account-switch-control"
                type="button"
                role="switch"
                aria-checked={account.preferences.modelImprovementAllowed}
                aria-label="允许用于改进模型"
                disabled={pending}
                ref={(node) => {
                  modelTriggerRef.current = node
                }}
                onClick={() => {
                  setActionError(null)
                  setModelAuthorizationTarget(!account.preferences.modelImprovementAllowed)
                }}
              >
                <span />
              </button>
            </div>

            <div className="account-export-row">
              <span aria-hidden="true"><DownloadSimpleIcon size={19} weight="regular" /></span>
              <div>
                <h3>导出个人数据</h3>
                <p>导出包含账户资料、研究任务与模型交互记录，不包含密码或会话凭据。</p>
              </div>
              <button
                className="account-management-button"
                type="button"
                disabled={pending}
                onClick={() => void perform(
                  'export',
                  () => api.requestDataExport({
                    idempotencyKey: mutationIntents.current.keyFor(
                      'export',
                      { format: 'json' },
                    ),
                  }),
                  setDataExport,
                  '数据副本已准备。',
                )}
              >
                {pendingAction === 'export' ? '正在准备…' : '导出我的数据'}
              </button>
            </div>
            {dataExport ? (
              <div className="account-export-result" role="status">
                {dataExport.status === 'ready' && dataExport.downloadHref ? (
                  <>
                    <span>副本已生成，下载链接将于 {formattedDate(dataExport.expiresAt)} 失效。</span>
                    <a href={dataExport.downloadHref} download>下载数据副本</a>
                  </>
                ) : (
                  <span>数据副本正在准备，请稍后重新查看。</span>
                )}
              </div>
            ) : null}
          </section>

          <section className="account-settings-section account-settings-section--danger" id="account-danger" aria-labelledby="account-danger-title">
            <div className="account-settings-section__heading">
              <span aria-hidden="true"><WarningIcon size={18} weight="regular" /></span>
              <div>
                <h2 id="account-danger-title">账户状态</h2>
                <p>先选择可恢复的停用；只有在确认不再需要数据时才永久删除。</p>
              </div>
            </div>
            {account.isProtectedAdmin ? (
              <div className="account-protected-admin-notice">
                <span aria-hidden="true"><ShieldCheckIcon size={20} weight="regular" /></span>
                <div>
                  <h3>部署管理员保护</h3>
                  <p>这个账户负责内测环境恢复，不能被降级、停用或删除。你仍可更新密码与撤销其他会话。</p>
                </div>
              </div>
            ) : (
              <>
                <div className="account-danger-row">
                  <span aria-hidden="true"><PowerIcon size={19} weight="regular" /></span>
                  <div>
                    <h3>停用账户</h3>
                    <p>立即退出所有设备并暂停访问。研究数据保留，管理员可在核验后恢复账户。</p>
                  </div>
                  <button
                    className="account-management-button"
                    type="button"
                    disabled={pending}
                    ref={(node) => {
                      deactivateTriggerRef.current = node
                    }}
                    onClick={() => {
                      setActionError(null)
                      setDeactivationOpen(true)
                    }}
                  >
                    停用账户
                  </button>
                </div>
                <div className="account-danger-row account-danger-row--irreversible">
                  <span aria-hidden="true"><TrashIcon size={19} weight="regular" /></span>
                  <div>
                    <h3>永久删除账户</h3>
                    <p>删除账户、研究任务、派生文档与个人模型交互记录。删除后无法恢复。</p>
                  </div>
                  <button
                    className="account-management-button account-management-button--danger-outline"
                    type="button"
                    disabled={pending}
                    ref={(node) => {
                      deleteTriggerRef.current = node
                    }}
                    onClick={() => {
                      setActionError(null)
                      setDeletionOpen(true)
                    }}
                  >
                    永久删除账户
                  </button>
                </div>
              </>
            )}
          </section>
        </div>
      </div>

      {sessionToRevoke ? (
        <AccountConfirmationDialog
          title="撤销这个会话？"
          description={`${sessionToRevoke.deviceLabel} 将立即退出，未保存的操作可能丢失。`}
          confirmLabel="确认撤销"
          pendingLabel="正在撤销…"
          pending={pendingAction === 'revoke-session'}
          error={actionError}
          triggerRef={sessionTriggerRef}
          onCancel={() => setSessionToRevoke(null)}
          onConfirm={() => void perform(
            'revoke-session',
            () => api.revokeSession(sessionToRevoke.sessionId, {
              idempotencyKey: mutationIntents.current.keyFor(
                'revoke-session',
                { sessionId: sessionToRevoke.sessionId },
              ),
            }),
            () => {
              replaceSessions((items) => items.filter((item) => item.sessionId !== sessionToRevoke.sessionId))
              setSessionToRevoke(null)
            },
            '会话已撤销。',
          )}
        />
      ) : null}

      {modelAuthorizationTarget !== null ? (
        <AccountConfirmationDialog
          title={modelAuthorizationTarget ? '允许用于改进模型？' : '停止用于改进模型？'}
          description={modelAuthorizationTarget
            ? '群学致知当前不使用你的数据训练模型。开启仅记录未来可选改进计划的授权；任何实际启用仍会另行告知。'
            : '停止后，未来可选改进计划不再取得你的授权；研究功能所需推理不受影响。'}
          confirmLabel={modelAuthorizationTarget ? '确认允许' : '确认停止'}
          pending={pendingAction === 'model-authorization'}
          error={actionError}
          triggerRef={modelTriggerRef}
          onCancel={() => setModelAuthorizationTarget(null)}
          onConfirm={() => void perform(
            'model-authorization',
            () => {
              const intent = {
                allowed: modelAuthorizationTarget,
                policyVersion: account.preferences.consentPolicyVersion,
                expectedVersion: account.preferences.version,
              }
              return api.updateModelDataAuthorization({
                ...intent,
                idempotencyKey: mutationIntents.current.keyFor(
                  'model-authorization',
                  intent,
                ),
              })
            },
            (preferences) => {
              replaceAccount({ ...account, preferences })
              setModelAuthorizationTarget(null)
            },
            modelAuthorizationTarget ? '模型数据授权已开启。' : '模型数据授权已关闭。',
          )}
        />
      ) : null}

      {deactivationOpen ? (
        <AccountConfirmationDialog
          title="停用账户？"
          description="停用后你会立即退出所有设备。数据会保留，管理员可在核验后恢复访问。"
          confirmLabel="确认停用"
          pending={pendingAction === 'deactivate'}
          confirmDisabled={!deactivationPassword || !deactivationReason.trim()}
          error={actionError}
          tone="danger"
          triggerRef={deactivateTriggerRef}
          onCancel={() => setDeactivationOpen(false)}
          onConfirm={() => void perform(
            'deactivate',
            () => {
              const intent = {
                currentPassword: deactivationPassword,
                reason: deactivationReason.trim(),
              }
              return api.deactivateAccount({
                ...intent,
                idempotencyKey: mutationIntents.current.keyFor('deactivate', intent),
              })
            },
            () => {
              setDeactivationOpen(false)
              onAccountDeactivated?.()
            },
            '账户已停用。',
          )}
        >
          <div className="account-management-form">
            <label>
              <span>当前密码</span>
              <input type="password" value={deactivationPassword} onChange={(event) => setDeactivationPassword(event.target.value)} autoComplete="current-password" />
            </label>
            <label>
              <span>停用原因</span>
              <textarea value={deactivationReason} onChange={(event) => setDeactivationReason(event.target.value)} maxLength={240} rows={3} />
            </label>
          </div>
        </AccountConfirmationDialog>
      ) : null}

      {deletionOpen ? (
        <AccountConfirmationDialog
          title="永久删除账户？"
          description="账户、研究任务、派生文档与个人模型交互记录将被永久删除。删除后无法恢复。"
          confirmLabel="确认永久删除"
          pendingLabel="正在删除…"
          pending={pendingAction === 'delete'}
          confirmDisabled={deletionEmail.trim().toLowerCase() !== account.email.toLowerCase() || !deletionPassword}
          error={actionError}
          tone="danger"
          triggerRef={deleteTriggerRef}
          onCancel={() => setDeletionOpen(false)}
          onConfirm={() => void perform(
            'delete',
            () => {
              const intent = {
                currentPassword: deletionPassword,
                confirmationEmail: deletionEmail.trim(),
              }
              return api.deleteAccount({
                ...intent,
                idempotencyKey: mutationIntents.current.keyFor('delete', intent),
              })
            },
            () => {
              setDeletionOpen(false)
              onAccountDeleted?.()
            },
            '账户已永久删除。',
          )}
        >
          <div className="account-management-form">
            <label>
              <span>账户邮箱</span>
              <input value={deletionEmail} onChange={(event) => setDeletionEmail(event.target.value)} autoComplete="email" placeholder={account.email} />
            </label>
            <label>
              <span>当前密码</span>
              <input type="password" value={deletionPassword} onChange={(event) => setDeletionPassword(event.target.value)} autoComplete="current-password" />
            </label>
          </div>
        </AccountConfirmationDialog>
      ) : null}
    </article>
  )
}
