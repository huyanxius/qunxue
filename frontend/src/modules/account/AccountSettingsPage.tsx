import {
  SignOutIcon,
  SlidersHorizontalIcon,
  CoinsIcon,
  DatabaseIcon,
  LockKeyIcon,
  PowerIcon,
  ShieldCheckIcon,
  UserCircleIcon,
  WarningIcon,
} from '@phosphor-icons/react'
import { useEffect, useId, useRef, useState } from 'react'
import type { FormEvent, MutableRefObject, ReactNode } from 'react'

import {
  isAccountManagementRequestError,
  type AccountManagementApi,
  type AccountProfile,
  type AccountSession,
  type CreditSummary,
  type PersonalDataExport,
} from './accountManagementModels'
import { useAppLocale } from '../../i18n/AppLocaleProvider'
import { accountManagementApi } from './accountManagementApi'
import { MutationIntentLedger } from './mutationIntent'
import './account-settings.css'

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
  cancelLabel?: string
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
  cancelLabel = '取消',
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
    <div className="qs-confirmation">
      <section
        className={`qs-dialog qs-dialog--${tone}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        ref={dialogRef}
        tabIndex={-1}
      >
        <span className="qs-dialog-mark" aria-hidden="true">
          {tone === 'danger' ? (
            <WarningIcon size={20} weight="regular" />
          ) : (
            <ShieldCheckIcon size={20} weight="regular" />
          )}
        </span>
        <h2 id={titleId}>{title}</h2>
        <p id={descriptionId}>{description}</p>
        {children ? <div className="qs-dialog-body">{children}</div> : null}
        {error ? (
          <p className="qs-alert" role="alert">
            {error}
          </p>
        ) : null}
        <div className="qs-actions">
          <button
            className="qs-button"
            type="button"
            disabled={pending}
            ref={cancelRef}
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
          <button
            className={`qs-button ${tone === 'danger' ? 'qs-button--danger' : 'qs-button--primary'}`}
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
  onLogout?(): void
  onProfileUpdated?(account: AccountProfile): void
  onSessionExpired?(): void
  onAccountDeactivated?(): void
  onAccountDeleted?(): void
}

type LoadState =
  | { status: 'loading' }
  | { status: 'error' }
  | {
      status: 'ready'
      account: AccountProfile
      sessions: AccountSession[]
      credits: CreditSummary
    }

type SettingsPartition =
  'profile' | 'credits' | 'preferences' | 'security' | 'privacy' | 'danger'

const partitionIcons = {
  profile: UserCircleIcon,
  credits: CoinsIcon,
  preferences: SlidersHorizontalIcon,
  security: LockKeyIcon,
  privacy: DatabaseIcon,
  danger: PowerIcon,
}

const settingsPartitions: SettingsPartition[] = [
  'profile',
  'credits',
  'preferences',
  'security',
  'privacy',
  'danger',
]

const creditPageSize = 10

function formattedDate(value: string | null, locale = 'zh-CN') {
  if (!value) return locale === 'en-US' ? 'No record' : '暂无记录'
  const date = new Date(value)
  if (Number.isNaN(date.getTime()))
    return locale === 'en-US' ? 'Unknown time' : '时间未知'
  return date.toLocaleString(locale, {
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
  onLogout,
  onProfileUpdated,
  onSessionExpired,
  onAccountDeactivated,
  onAccountDeleted,
}: AccountSettingsPageProps) {
  const [reloadToken, setReloadToken] = useState(0)
  const mutationIntents = useRef(new MutationIntentLedger())
  const [loadState, setLoadState] = useState<LoadState>({ status: 'loading' })
  const [activePartition, setActivePartition] =
    useState<SettingsPartition>('profile')
  const [displayName, setDisplayName] = useState('')
  const [profileEditing, setProfileEditing] = useState(false)
  const { locale: appLocale, setLocale: setAppLocale } = useAppLocale()
  const [locale, setLocale] = useState(appLocale)
  const [timezone, setTimezone] = useState('Asia/Shanghai')
  const [researchUpdatesEnabled, setResearchUpdatesEnabled] = useState(true)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [passwordConfirmation, setPasswordConfirmation] = useState('')
  const [creditCode, setCreditCode] = useState('')
  const [creditPage, setCreditPage] = useState(1)
  const [revokeOtherSessions, setRevokeOtherSessions] = useState(true)
  const [pendingAction, setPendingAction] = useState<string | null>(null)
  const pendingActionRef = useRef<string | null>(null)
  const english = locale === 'en-US'
  const text = (zh: string, en: string) => (english ? en : zh)
  const partitionLabels: Record<SettingsPartition, string> = {
    profile: text('个人资料', 'Profile'),
    credits: text('积分与用量', 'Credits & usage'),
    preferences: text('使用偏好', 'Preferences'),
    security: text('安全', 'Security'),
    privacy: text('数据与隐私', 'Data & privacy'),
    danger: text('账户状态', 'Account status'),
  }

  const [feedback, setFeedback] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [dataExport, setDataExport] = useState<PersonalDataExport | null>(null)
  const [sessionToRevoke, setSessionToRevoke] = useState<AccountSession | null>(
    null,
  )
  const [modelAuthorizationTarget, setModelAuthorizationTarget] = useState<
    boolean | null
  >(null)
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
    Promise.all([
      api.getAccount(),
      api.listSessions(),
      api.getCreditSummary({ limit: creditPageSize }),
    ])
      .then(([account, sessions, credits]) => {
        if (!active) return
        setLoadState({ status: 'ready', account, sessions, credits })
        setDisplayName(account.displayName ?? '')
        const preferredLocale =
          account.preferences.locale === 'en-US' ? 'en-US' : 'zh-CN'
        setLocale(preferredLocale)
        setAppLocale(preferredLocale)
        setTimezone(account.preferences.timezone)
        setResearchUpdatesEnabled(account.preferences.researchUpdatesEnabled)
      })
      .catch((failure: unknown) => {
        if (!active) return
        if (
          isAccountManagementRequestError(failure) &&
          failure.status === 401
        ) {
          onSessionExpired?.()
        }
        setLoadState({ status: 'error' })
      })
    return () => {
      active = false
    }
  }, [api, onSessionExpired, reloadToken, setAppLocale])

  function replaceAccount(account: AccountProfile) {
    setLoadState((state) =>
      state.status === 'ready' ? { ...state, account } : state,
    )
  }

  function replaceSessions(
    update: (sessions: AccountSession[]) => AccountSession[],
  ) {
    setLoadState((state) =>
      state.status === 'ready'
        ? { ...state, sessions: update(state.sessions) }
        : state,
    )
  }

  function replaceCredits(credits: CreditSummary) {
    setLoadState((state) =>
      state.status === 'ready' ? { ...state, credits } : state,
    )
  }

  function failureMessage(failure: unknown) {
    if (isAccountManagementRequestError(failure)) {
      if (failure.status === 401) {
        onSessionExpired?.()
        return text(
          '登录已过期，请重新登录后继续。',
          'Your session expired. Sign in again to continue.',
        )
      }
      if (failure.status === 409) {
        return failure.message
      }
    }
    return text(
      '操作未完成，已保留当前数据。请检查网络后重试。',
      'The change was not completed. Your current data is unchanged. Check your connection and try again.',
    )
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
      setFeedback(
        typeof successMessage === 'function'
          ? successMessage(result)
          : successMessage,
      )
    } catch (failure) {
      setActionError(failureMessage(failure))
    } finally {
      pendingActionRef.current = null
      setPendingAction(null)
    }
  }

  if (loadState.status === 'loading') {
    return (
      <section className="qs-state qs-loading" role="status" aria-live="polite">
        <span className="qs-loading-line" />
        <span className="qs-loading-line" />
        <span className="qs-loading-line" />
        <p>{text('正在读取账户设置', 'Loading account settings')}</p>
      </section>
    )
  }

  if (loadState.status === 'error') {
    return (
      <section className="qs-state" role="alert">
        <span className="qs-state-icon" aria-hidden="true">
          <WarningIcon size={20} weight="regular" />
        </span>
        <h2>
          {text('暂时无法读取账户设置', 'Account settings are unavailable')}
        </h2>
        <p>
          {text(
            '你的账户与研究数据没有改变。请检查网络后重试。',
            'Your account and research data are unchanged. Check your connection and try again.',
          )}
        </p>
        <button
          className="qs-button"
          type="button"
          onClick={() => setReloadToken((value) => value + 1)}
        >
          {text('重试', 'Try again')}
        </button>
      </section>
    )
  }

  const { account, sessions, credits } = loadState
  const accountName = account.displayName ?? text('研究者', 'Researcher')
  const accountInitial = Array.from(accountName.trim())[0] ?? text('研', 'R')
  const otherSessions = sessions.filter((session) => !session.current)
  const pending = pendingAction !== null
  const creditRemainingPercentage =
    credits.creditLimit > 0
      ? Math.min(
          100,
          Math.max(
            0,
            Math.round((credits.balance / credits.creditLimit) * 100),
          ),
        )
      : 0

  function submitProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalizedName = displayName.trim()
    if (!normalizedName || normalizedName.length > 80) {
      setActionError(
        text(
          '显示名称需要 1-80 个字符。',
          'Display name must be between 1 and 80 characters.',
        ),
      )
      return
    }
    void perform(
      'profile',
      () => {
        const intent = {
          displayName: normalizedName,
          expectedVersion: account.version,
        }
        return api.updateProfile({
          ...intent,
          idempotencyKey: mutationIntents.current.keyFor('profile', intent),
        })
      },
      (updated) => {
        replaceAccount(updated)
        setDisplayName(updated.displayName ?? '')
        setProfileEditing(false)
        onProfileUpdated?.(updated)
      },
      text('资料已保存。', 'Profile saved.'),
    )
  }

  function submitCreditRedemption(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const code = creditCode.trim()
    if (!code) {
      setActionError(
        text('请输入积分兑换码。', 'Enter a credit redemption code.'),
      )
      return
    }
    const intent = { code }
    void perform(
      'credit-redemption',
      () =>
        api.redeemCredits({
          ...intent,
          idempotencyKey: mutationIntents.current.keyFor(
            'credit-redemption',
            intent,
          ),
        }),
      (redemption) => {
        mutationIntents.current.complete('credit-redemption')
        replaceCredits({
          ...credits,
          balance: redemption.balance,
        })
        setCreditCode('')
      },
      (redemption) =>
        text(
          `积分已恢复至 ${redemption.balance.toLocaleString('zh-CN')}。`,
          `Credits restored to ${redemption.balance.toLocaleString('en-US')}.`,
        ),
    )
  }

  async function loadCreditPage(nextPage: number, cursor?: string) {
    if (pendingActionRef.current) return
    pendingActionRef.current = 'credit-page'
    setPendingAction('credit-page')
    setActionError(null)
    try {
      const nextCredits = await api.getCreditSummary({
        ...(cursor ? { cursor } : {}),
        limit: creditPageSize,
      })
      replaceCredits(nextCredits)
      setCreditPage(nextPage)
    } catch (failure) {
      setActionError(failureMessage(failure))
    } finally {
      pendingActionRef.current = null
      setPendingAction(null)
    }
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
      text('偏好已保存。', 'Preferences saved.'),
    )
  }

  function submitPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (newPassword.length < 12 || newPassword.length > 128) {
      setActionError(
        text(
          '新密码需要 12-128 个字符。',
          'New password must be between 12 and 128 characters.',
        ),
      )
      return
    }
    if (newPassword !== passwordConfirmation) {
      setActionError(
        text('两次输入的新密码不一致。', 'The new passwords do not match.'),
      )
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
        if (revokeOtherSessions)
          replaceSessions((items) => items.filter((item) => item.current))
      },
      ({ revokedSessionCount }) =>
        text(
          `密码已更新，已撤销 ${revokedSessionCount} 个其他会话。`,
          `Password updated. ${revokedSessionCount} other session${revokedSessionCount === 1 ? '' : 's'} revoked.`,
        ),
    )
  }

  return (
    <article className="qs-settings">
      <aside className="qs-sidebar">
        <div className="qs-identity">
          <span className="qs-avatar" aria-hidden="true">
            {accountInitial}
          </span>
          <div>
            <strong>{accountName}</strong>
            <small>
              {account.role === 'admin'
                ? text('管理员', 'Administrator')
                : text('个人账户', 'Personal account')}
            </small>
          </div>
        </div>
        <h1>{text('账户设置', 'Account settings')}</h1>
        <nav aria-label={text('账户设置分区', 'Account settings sections')}>
          {settingsPartitions.map((partition) => {
            const Icon = partitionIcons[partition]
            return (
              <button
                key={partition}
                type="button"
                aria-current={
                  activePartition === partition ? 'page' : undefined
                }
                onClick={() => {
                  setActivePartition(partition)
                  setFeedback(null)
                  setActionError(null)
                }}
              >
                <Icon size={18} aria-hidden="true" />
                {partitionLabels[partition]}
              </button>
            )
          })}
        </nav>
        <div className="qs-sidebar-footer">
          {account.role === 'admin' ? (
            <a href={adminHref}>
              {text('打开用户管理', 'Open user management')}
            </a>
          ) : null}
          <button type="button" onClick={onLogout}>
            <SignOutIcon size={18} aria-hidden="true" />
            {text('退出登录', 'Sign out')}
          </button>
        </div>
      </aside>
      <section className="qs-content" aria-labelledby="qs-section-title">
        <header className="qs-header">
          <h2 id="qs-section-title">{partitionLabels[activePartition]}</h2>
        </header>
        {feedback ? (
          <p className="qs-feedback" role="status" aria-live="polite">
            {feedback}
          </p>
        ) : null}
        {actionError ? (
          <p className="qs-alert" role="alert">
            {actionError}
          </p>
        ) : null}
        {activePartition === 'profile' && (
          <>
            <div className="qs-profile">
              <span className="qs-avatar qs-avatar--large" aria-hidden="true">
                {accountInitial}
              </span>
              <div>
                <strong>{accountName}</strong>
                <p>
                  {account.role === 'admin'
                    ? text('管理员', 'Administrator')
                    : text('内测用户', 'Beta user')}
                </p>
              </div>
            </div>
            <div className="qs-row">
              <div>
                <h3>{text('显示名称', 'Display name')}</h3>
                {!profileEditing && <p>{accountName}</p>}
              </div>
              {profileEditing ? (
                <form className="qs-edit" onSubmit={submitProfile} noValidate>
                  <label>
                    <span className="qs-sr-only">
                      {text('显示名称', 'Display name')}
                    </span>
                    <input
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      maxLength={80}
                      autoComplete="name"
                      autoFocus
                      required
                    />
                  </label>
                  <div className="qs-actions">
                    <button
                      className="qs-button"
                      type="button"
                      disabled={pending}
                      onClick={() => {
                        setProfileEditing(false)
                        setDisplayName(account.displayName ?? '')
                        setActionError(null)
                      }}
                    >
                      {text('取消', 'Cancel')}
                    </button>
                    <button
                      className="qs-button qs-button--primary"
                      disabled={pending}
                    >
                      {pendingAction === 'profile'
                        ? text('正在保存…', 'Saving…')
                        : text('保存资料', 'Save profile')}
                    </button>
                  </div>
                </form>
              ) : (
                <button
                  className="qs-button"
                  type="button"
                  aria-label={text('修改显示名称', 'Edit display name')}
                  onClick={() => setProfileEditing(true)}
                >
                  {text('修改', 'Edit')}
                </button>
              )}
            </div>
            <div className="qs-row">
              <div>
                <h3>{text('邮箱', 'Email')}</h3>
                <p>{account.email}</p>
              </div>
              <small>
                {text('变更请联系管理员', 'Contact an administrator to change')}
              </small>
            </div>
            <div className="qs-row">
              <div>
                <h3>{text('加入时间', 'Joined')}</h3>
                <p>{formattedDate(account.createdAt, locale)}</p>
              </div>
            </div>
          </>
        )}
        {activePartition === 'preferences' && (
          <form onSubmit={submitPreferences}>
            <label className="qs-row">
              <span>
                <strong>{text('界面语言', 'Interface language')}</strong>
                <small>
                  {text(
                    '应用于导航、设置与操作提示',
                    'Navigation, settings, and interface messages',
                  )}
                </small>
              </span>
              <select
                aria-label={text('界面语言', 'Interface language')}
                value={locale}
                onChange={(e) => {
                  const next = e.target.value === 'en-US' ? 'en-US' : 'zh-CN'
                  setLocale(next)
                  setAppLocale(next)
                }}
              >
                <option value="zh-CN">
                  {text('简体中文', 'Chinese (Simplified)')}
                </option>
                <option value="en-US">English</option>
              </select>
            </label>
            <label className="qs-row">
              <span>
                <strong>{text('时区', 'Time zone')}</strong>
                <small>
                  {text(
                    '用于显示研究与账户活动时间',
                    'Research and account activity timestamps',
                  )}
                </small>
              </span>
              <select
                aria-label={text('时区', 'Time zone')}
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
              >
                <option value="Asia/Shanghai">
                  {text('中国标准时间', 'China Standard Time')}
                </option>
                <option value="UTC">
                  {text('协调世界时', 'Coordinated Universal Time')}
                </option>
              </select>
            </label>
            <div className="qs-actions qs-actions--footer">
              <button
                className="qs-button qs-button--primary"
                disabled={pending}
              >
                {pendingAction === 'preferences'
                  ? text('正在保存…', 'Saving…')
                  : text('保存偏好', 'Save preferences')}
              </button>
            </div>
          </form>
        )}
        {activePartition === 'credits' && (
          <>
            <div className="qs-balance">
              <span>{text('积分余额', 'Credit balance')}</span>
              <div aria-label={text('积分余额数值', 'Credit balance value')}>
                <strong>
                  {credits.isUnlimited
                    ? text('无限', 'Unlimited')
                    : credits.balance.toLocaleString(locale)}
                </strong>
                {!credits.isUnlimited && (
                  <span>/ {credits.creditLimit.toLocaleString(locale)}</span>
                )}
              </div>
              {!credits.isUnlimited && (
                <>
                  <div
                    className="qs-meter"
                    role="progressbar"
                    aria-label={text('积分余额', 'Credit balance')}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={creditRemainingPercentage}
                  >
                    <span style={{ width: `${creditRemainingPercentage}%` }} />
                  </div>
                  <p>
                    {text(
                      `剩余 ${creditRemainingPercentage}%`,
                      `${creditRemainingPercentage}% left`,
                    )}
                  </p>
                </>
              )}
              {credits.isUnlimited && (
                <p>
                  {text(
                    '管理员账户不扣减积分',
                    'Administrator usage does not consume credits',
                  )}
                </p>
              )}
            </div>
            {!credits.isUnlimited && (
              <form className="qs-row" onSubmit={submitCreditRedemption}>
                <div>
                  <h3>{text('兑换码', 'Redemption code')}</h3>
                  <p>
                    {text(
                      '每个兑换码仅可使用一次',
                      'Each code can be used once',
                    )}
                  </p>
                </div>
                <div className="qs-redemption">
                  <input
                    aria-label={text('积分兑换码', 'Credit redemption code')}
                    autoComplete="off"
                    maxLength={64}
                    placeholder="QX-XXXX-XXXX"
                    value={creditCode}
                    onChange={(e) => setCreditCode(e.target.value)}
                  />
                  <button
                    className="qs-button"
                    disabled={pending || !creditCode.trim()}
                  >
                    {pendingAction === 'credit-redemption'
                      ? text('正在兑换…', 'Redeeming…')
                      : text('兑换积分', 'Redeem credits')}
                  </button>
                </div>
              </form>
            )}
            <div className="qs-subheading">
              <h3>{text('积分消耗记录', 'Credit usage')}</h3>
              <span>
                {text(
                  `共 ${credits.totalEntries} 笔`,
                  `${credits.totalEntries} total`,
                )}
              </span>
            </div>
            {credits.entries.length ? (
              credits.entries.map((entry) => (
                <div className="qs-row qs-ledger" key={entry.entryId}>
                  <div>
                    <h3>
                      {entry.kind === 'usage'
                        ? text('Agent 对话', 'Agent conversation')
                        : entry.kind === 'redemption'
                          ? text('兑换码到账', 'Code redemption')
                          : text('新用户赠送', 'Welcome credits')}
                    </h3>
                    <p>{formattedDate(entry.createdAt, locale)}</p>
                    {entry.kind === 'usage' && (
                      <small>
                        {entry.inputTokens.toLocaleString(locale)}{' '}
                        {text('输入', 'input')} ·{' '}
                        {entry.outputTokens.toLocaleString(locale)}{' '}
                        {text('输出', 'output')} token
                      </small>
                    )}
                  </div>
                  <strong>
                    {entry.points > 0 ? '+' : ''}
                    {entry.points.toLocaleString(locale)}
                  </strong>
                </div>
              ))
            ) : (
              <p className="qs-empty">
                {text(
                  '完成首轮对话后，用量流水会出现在这里。',
                  'Usage will appear here after your first conversation.',
                )}
              </p>
            )}
            {credits.totalEntries > creditPageSize && (
              <nav
                className="qs-pagination"
                aria-label={text('积分记录分页', 'Credit usage pages')}
              >
                <button
                  className="qs-button"
                  aria-label={text(
                    '上一页积分消耗记录',
                    'Previous credit usage page',
                  )}
                  disabled={pending || creditPage === 1}
                  onClick={() =>
                    void loadCreditPage(
                      creditPage - 1,
                      creditPage > 2
                        ? String((creditPage - 2) * creditPageSize)
                        : undefined,
                    )
                  }
                >
                  {text('上一页', 'Previous')}
                </button>
                <span>{text(`第 ${creditPage} 页`, `Page ${creditPage}`)}</span>
                <button
                  className="qs-button"
                  aria-label={text(
                    '下一页积分消耗记录',
                    'Next credit usage page',
                  )}
                  disabled={pending || !credits.nextCursor}
                  onClick={() =>
                    void loadCreditPage(
                      creditPage + 1,
                      credits.nextCursor ?? undefined,
                    )
                  }
                >
                  {text('下一页', 'Next')}
                </button>
              </nav>
            )}
            <p className="qs-footnote">
              {text(
                '按模型实际 token 用量结算，失败或中止的回答不扣积分。',
                'Charged by actual token usage. Failed or interrupted responses are not charged.',
              )}
            </p>
          </>
        )}
        {activePartition === 'security' && (
          <>
            <details className="qs-disclosure" open><summary>{text('登录密码', 'Sign-in password')}</summary>
            <form className="qs-password" onSubmit={submitPassword} noValidate>
              <label className="qs-row">
                <span>{text('当前密码', 'Current password')}</span>
                <input
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  autoComplete="current-password"
                  maxLength={128}
                  required
                />
              </label>
              <label className="qs-row">
                <span>{text('新密码', 'New password')}</span>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  autoComplete="new-password"
                  minLength={12}
                  maxLength={128}
                  required
                />
              </label>
              <label className="qs-row">
                <span>{text('确认新密码', 'Confirm new password')}</span>
                <input
                  type="password"
                  value={passwordConfirmation}
                  onChange={(e) => setPasswordConfirmation(e.target.value)}
                  autoComplete="new-password"
                  minLength={12}
                  maxLength={128}
                  required
                />
              </label>
              <label className="qs-check">
                <input
                  type="checkbox"
                  checked={revokeOtherSessions}
                  onChange={(e) => setRevokeOtherSessions(e.target.checked)}
                />
                <span>
                  {text('撤销其他设备的会话', 'Sign out other devices')}
                  <small>
                    {text(
                      '当前设备不会退出。',
                      'Your current device stays signed in.',
                    )}
                  </small>
                </span>
              </label>
              <div className="qs-actions">
                <button
                  className="qs-button qs-button--primary"
                  disabled={pending || !currentPassword}
                >
                  {pendingAction === 'password'
                    ? text('正在更新…', 'Updating…')
                    : text('更新密码', 'Update password')}
                </button>
              </div>
            </form>
            </details>
            <div className="qs-subheading">
              <h3>{text('活跃会话', 'Active sessions')}</h3>
            </div>
            {sessions.map((session) => (
              <div className="qs-row" key={session.sessionId}>
                <div>
                  <h3>{session.deviceLabel}</h3>
                  <p>
                    {text('最近活动', 'Last active')} ·{' '}
                    {formattedDate(session.lastSeenAt, locale)}
                  </p>
                </div>
                {session.current ? (
                  <span className="qs-badge">
                    {text('当前会话', 'Current session')}
                  </span>
                ) : (
                  <button
                    className="qs-button"
                    aria-label={text(
                      `撤销 ${session.deviceLabel} 会话`,
                      `Revoke ${session.deviceLabel} session`,
                    )}
                    disabled={pending}
                    onClick={(event) => {
                      sessionTriggerRef.current = event.currentTarget
                      setActionError(null)
                      setSessionToRevoke(session)
                    }}
                  >
                    {text('撤销', 'Revoke')}
                  </button>
                )}
              </div>
            ))}
            {otherSessions.length === 0 && (
              <p className="qs-empty">
                <strong>
                  {text('没有其他活跃会话', 'No other active sessions')}
                </strong>
              </p>
            )}
          </>
        )}
        {activePartition === 'privacy' && (
          <>
            <div className="qs-row qs-row--long">
              <div>
                <h3>{text('允许用于改进模型', 'Allow model improvement')}</h3>
                <p>
                  {text(
                    '目前不使用研究数据训练模型。此项仅记录未来可选改进计划的授权，可随时撤回。',
                    'Your data is not currently used for training. This records revocable consent for a future optional program.',
                  )}
                </p>
              </div>
              <button
                className="qs-switch"
                type="button"
                role="switch"
                aria-checked={account.preferences.modelImprovementAllowed}
                aria-label={text('允许用于改进模型', 'Allow model improvement')}
                disabled={pending}
                ref={
                  modelTriggerRef as MutableRefObject<HTMLButtonElement | null>
                }
                onClick={() => {
                  setActionError(null)
                  setModelAuthorizationTarget(
                    !account.preferences.modelImprovementAllowed,
                  )
                }}
              >
                <span />
              </button>
            </div>
            <div className="qs-row qs-row--long">
              <div>
                <h3>{text('导出个人数据', 'Export personal data')}</h3>
                <p>
                  {text(
                    '包含账户资料、研究任务与模型交互记录，不包含密码或会话凭据。',
                    'Includes your profile, research tasks, and model interactions. Excludes passwords and session credentials.',
                  )}
                </p>
              </div>
              <button
                className="qs-button"
                disabled={pending}
                onClick={() =>
                  void perform(
                    'export',
                    () =>
                      api.requestDataExport({
                        idempotencyKey: mutationIntents.current.keyFor(
                          'export',
                          { format: 'json' },
                        ),
                      }),
                    setDataExport,
                    text('数据副本已准备。', 'Your data copy is ready.'),
                  )
                }
              >
                {pendingAction === 'export'
                  ? text('正在准备…', 'Preparing…')
                  : text('导出我的数据', 'Export my data')}
              </button>
            </div>
            {dataExport && (
              <div className="qs-feedback" role="status">
                {dataExport.status === 'ready' && dataExport.downloadHref ? (
                  <a href={dataExport.downloadHref} download>
                    {text('下载数据副本', 'Download data copy')}
                  </a>
                ) : (
                  text(
                    '数据副本正在准备，请稍后重新查看。',
                    'Your data copy is being prepared. Check again later.',
                  )
                )}
              </div>
            )}
          </>
        )}
        {activePartition === 'danger' && (
          <>
            {account.isProtectedAdmin ? (
              <div className="qs-empty">
                <h3>{text('部署管理员保护', 'Deployment admin protection')}</h3>
                <p>
                  {text(
                    '此账户不能被降级、停用或删除。仍可更新密码与撤销其他会话。',
                    'This account cannot be demoted, deactivated, or deleted. You can still update its password and revoke sessions.',
                  )}
                </p>
              </div>
            ) : (
              <>
                <div className="qs-row qs-row--long">
                  <div>
                    <h3>{text('停用账户', 'Deactivate account')}</h3>
                    <p>
                      {text(
                        '退出所有设备并暂停访问。研究数据保留，管理员可在核验后恢复账户。',
                        'Sign out all devices and pause access. Your data is retained; an administrator can restore access.',
                      )}
                    </p>
                  </div>
                  <button
                    className="qs-button"
                    disabled={pending}
                    ref={
                      deactivateTriggerRef as MutableRefObject<HTMLButtonElement | null>
                    }
                    onClick={() => {
                      setActionError(null)
                      setDeactivationOpen(true)
                    }}
                  >
                    {text('停用账户', 'Deactivate account')}
                  </button>
                </div>
                <div className="qs-row qs-row--long">
                  <div>
                    <h3>
                      {text('永久删除账户', 'Permanently delete account')}
                    </h3>
                    <p>
                      {text(
                        '永久删除账户、研究任务与个人模型交互记录。此操作无法恢复。',
                        'Permanently delete your account, research tasks, and personal model interactions. This cannot be undone.',
                      )}
                    </p>
                  </div>
                  <button
                    className="qs-button qs-button--danger"
                    disabled={pending}
                    ref={
                      deleteTriggerRef as MutableRefObject<HTMLButtonElement | null>
                    }
                    onClick={() => {
                      setActionError(null)
                      setDeletionOpen(true)
                    }}
                  >
                    {text('永久删除账户', 'Permanently delete account')}
                  </button>
                </div>
              </>
            )}
          </>
        )}
      </section>
      {sessionToRevoke ? (
        <AccountConfirmationDialog
          title={text('撤销这个会话？', 'Revoke this session?')}
          description={text(
            `${sessionToRevoke.deviceLabel} 将立即退出，未保存的操作可能丢失。`,
            `${sessionToRevoke.deviceLabel} will be signed out immediately. Unsaved work may be lost.`,
          )}
          confirmLabel={text('确认撤销', 'Revoke session')}
          cancelLabel={text('取消', 'Cancel')}
          pendingLabel={text('正在撤销…', 'Revoking…')}
          pending={pendingAction === 'revoke-session'}
          error={actionError}
          triggerRef={sessionTriggerRef}
          onCancel={() => setSessionToRevoke(null)}
          onConfirm={() =>
            void perform(
              'revoke-session',
              () =>
                api.revokeSession(sessionToRevoke.sessionId, {
                  idempotencyKey: mutationIntents.current.keyFor(
                    'revoke-session',
                    { sessionId: sessionToRevoke.sessionId },
                  ),
                }),
              () => {
                replaceSessions((items) =>
                  items.filter(
                    (item) => item.sessionId !== sessionToRevoke.sessionId,
                  ),
                )
                setSessionToRevoke(null)
              },
              text('会话已撤销。', 'Session revoked.'),
            )
          }
        />
      ) : null}

      {modelAuthorizationTarget !== null ? (
        <AccountConfirmationDialog
          title={
            modelAuthorizationTarget
              ? text('允许用于改进模型？', 'Allow model improvement?')
              : text('停止用于改进模型？', 'Stop model improvement access?')
          }
          description={
            modelAuthorizationTarget
              ? text(
                  '群学致知当前不使用你的数据训练模型。开启仅记录未来可选改进计划的授权；任何实际启用仍会另行告知。',
                  'Qunxue Zhizhi does not currently train on your data. Enabling this only records consent for a future optional improvement program; you will be notified before any actual use.',
                )
              : text(
                  '停止后，未来可选改进计划不再取得你的授权；研究功能所需推理不受影响。',
                  'Future optional improvement programs will no longer have your consent. Inference required for research features is unaffected.',
                )
          }
          confirmLabel={
            modelAuthorizationTarget
              ? text('确认允许', 'Allow')
              : text('确认停止', 'Stop allowing')
          }
          cancelLabel={text('取消', 'Cancel')}
          pendingLabel={text('正在处理…', 'Updating…')}
          pending={pendingAction === 'model-authorization'}
          error={actionError}
          triggerRef={modelTriggerRef}
          onCancel={() => setModelAuthorizationTarget(null)}
          onConfirm={() =>
            void perform(
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
              modelAuthorizationTarget
                ? text(
                    '模型数据授权已开启。',
                    'Model improvement consent enabled.',
                  )
                : text(
                    '模型数据授权已关闭。',
                    'Model improvement consent disabled.',
                  ),
            )
          }
        />
      ) : null}

      {deactivationOpen ? (
        <AccountConfirmationDialog
          title={text('停用账户？', 'Deactivate account?')}
          description={text(
            '停用后你会立即退出所有设备。数据会保留，管理员可在核验后恢复访问。',
            'You will be signed out on every device. Your data is retained, and an administrator can restore access after verification.',
          )}
          confirmLabel={text('确认停用', 'Deactivate')}
          cancelLabel={text('取消', 'Cancel')}
          pendingLabel={text('正在停用…', 'Deactivating…')}
          pending={pendingAction === 'deactivate'}
          confirmDisabled={!deactivationPassword || !deactivationReason.trim()}
          error={actionError}
          tone="danger"
          triggerRef={deactivateTriggerRef}
          onCancel={() => setDeactivationOpen(false)}
          onConfirm={() =>
            void perform(
              'deactivate',
              () => {
                const intent = {
                  currentPassword: deactivationPassword,
                  reason: deactivationReason.trim(),
                }
                return api.deactivateAccount({
                  ...intent,
                  idempotencyKey: mutationIntents.current.keyFor(
                    'deactivate',
                    intent,
                  ),
                })
              },
              () => {
                setDeactivationOpen(false)
                onAccountDeactivated?.()
              },
              text('账户已停用。', 'Account deactivated.'),
            )
          }
        >
          <div className="qs-form">
            <label>
              <span>{text('当前密码', 'Current password')}</span>
              <input
                type="password"
                value={deactivationPassword}
                onChange={(event) =>
                  setDeactivationPassword(event.target.value)
                }
                autoComplete="current-password"
              />
            </label>
            <label>
              <span>{text('停用原因', 'Reason for deactivation')}</span>
              <textarea
                value={deactivationReason}
                onChange={(event) => setDeactivationReason(event.target.value)}
                maxLength={240}
                rows={3}
              />
            </label>
          </div>
        </AccountConfirmationDialog>
      ) : null}

      {deletionOpen ? (
        <AccountConfirmationDialog
          title={text('永久删除账户？', 'Permanently delete account?')}
          description={text(
            '账户、研究任务、派生文档与个人模型交互记录将被永久删除。删除后无法恢复。',
            'Your account, research tasks, derived documents, and personal model interaction records will be permanently deleted. This cannot be undone.',
          )}
          confirmLabel={text('确认永久删除', 'Permanently delete')}
          cancelLabel={text('取消', 'Cancel')}
          pendingLabel={text('正在删除…', 'Deleting…')}
          pending={pendingAction === 'delete'}
          confirmDisabled={
            deletionEmail.trim().toLowerCase() !==
              account.email.toLowerCase() || !deletionPassword
          }
          error={actionError}
          tone="danger"
          triggerRef={deleteTriggerRef}
          onCancel={() => setDeletionOpen(false)}
          onConfirm={() =>
            void perform(
              'delete',
              () => {
                const intent = {
                  currentPassword: deletionPassword,
                  confirmationEmail: deletionEmail.trim(),
                }
                return api.deleteAccount({
                  ...intent,
                  idempotencyKey: mutationIntents.current.keyFor(
                    'delete',
                    intent,
                  ),
                })
              },
              () => {
                setDeletionOpen(false)
                onAccountDeleted?.()
              },
              text('账户已永久删除。', 'Account permanently deleted.'),
            )
          }
        >
          <div className="qs-form">
            <label>
              <span>{text('账户邮箱', 'Account email')}</span>
              <input
                value={deletionEmail}
                onChange={(event) => setDeletionEmail(event.target.value)}
                autoComplete="email"
                placeholder={account.email}
              />
            </label>
            <label>
              <span>{text('当前密码', 'Current password')}</span>
              <input
                type="password"
                value={deletionPassword}
                onChange={(event) => setDeletionPassword(event.target.value)}
                autoComplete="current-password"
              />
            </label>
          </div>
        </AccountConfirmationDialog>
      ) : null}
    </article>
  )
}
