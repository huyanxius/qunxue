import {
  BellIcon,
  CoinsIcon,
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
  type CreditSummary,
  type PersonalDataExport,
} from './accountManagementModels'
import { useAppLocale } from '../../i18n/AppLocaleProvider'
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
            {cancelLabel}
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
  | 'profile'
  | 'credits'
  | 'preferences'
  | 'security'
  | 'privacy'
  | 'danger'

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
  if (Number.isNaN(date.getTime())) return locale === 'en-US' ? 'Unknown time' : '时间未知'
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
  adminHref = '/admin/operations',
  onLogout,
  onProfileUpdated,
  onSessionExpired,
  onAccountDeactivated,
  onAccountDeleted,
}: AccountSettingsPageProps) {
  const [reloadToken, setReloadToken] = useState(0)
  const mutationIntents = useRef(new MutationIntentLedger())
  const [loadState, setLoadState] = useState<LoadState>({ status: 'loading' })
  const [activePartition, setActivePartition] = useState<SettingsPartition>('profile')
  const [displayName, setDisplayName] = useState('')
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
    Promise.all([
      api.getAccount(),
      api.listSessions(),
      api.getCreditSummary({ limit: creditPageSize }),
    ])
      .then(([account, sessions, credits]) => {
        if (!active) return
        setLoadState({ status: 'ready', account, sessions, credits })
        setDisplayName(account.displayName ?? '')
        const preferredLocale = account.preferences.locale === 'en-US' ? 'en-US' : 'zh-CN'
        setLocale(preferredLocale)
        setAppLocale(preferredLocale)
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
  }, [api, onSessionExpired, reloadToken, setAppLocale])

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

  function replaceCredits(credits: CreditSummary) {
    setLoadState((state) => state.status === 'ready'
      ? { ...state, credits }
      : state)
  }

  function failureMessage(failure: unknown) {
    if (isAccountManagementRequestError(failure)) {
      if (failure.status === 401) {
        onSessionExpired?.()
        return text('登录已过期，请重新登录后继续。', 'Your session expired. Sign in again to continue.')
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
        <p>{text('正在读取账户设置', 'Loading account settings')}</p>
      </section>
    )
  }

  if (loadState.status === 'error') {
    return (
      <section className="account-management-state" role="alert">
        <span className="account-management-state__icon" aria-hidden="true">
          <WarningIcon size={20} weight="regular" />
        </span>
        <h2>{text('暂时无法读取账户设置', 'Account settings are unavailable')}</h2>
        <p>{text('你的账户与研究数据没有改变。请检查网络后重试。', 'Your account and research data are unchanged. Check your connection and try again.')}</p>
        <button className="account-management-button" type="button" onClick={() => setReloadToken((value) => value + 1)}>
          {text('重试', 'Try again')}
        </button>
      </section>
    )
  }

  const { account, sessions, credits } = loadState
  const otherSessions = sessions.filter((session) => !session.current)
  const pending = pendingAction !== null
  const creditRemainingPercentage = credits.creditLimit > 0
    ? Math.min(100, Math.max(0, Math.round((credits.balance / credits.creditLimit) * 100)))
    : 0

  function submitProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalizedName = displayName.trim()
    if (!normalizedName || normalizedName.length > 80) {
      setActionError(text('显示名称需要 1-80 个字符。', 'Display name must be between 1 and 80 characters.'))
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
        onProfileUpdated?.(updated)
      },
      text('资料已保存。', 'Profile saved.'),
    )
  }

  function submitCreditRedemption(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const code = creditCode.trim()
    if (!code) {
      setActionError(text('请输入积分兑换码。', 'Enter a credit redemption code.'))
      return
    }
    const intent = { code }
    void perform(
      'credit-redemption',
      () => api.redeemCredits({
        ...intent,
        idempotencyKey: mutationIntents.current.keyFor('credit-redemption', intent),
      }),
      (redemption) => {
        mutationIntents.current.complete('credit-redemption')
        replaceCredits({
          ...credits,
          balance: redemption.balance,
        })
        setCreditCode('')
      },
      (redemption) => text(
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
      setActionError(text('新密码需要 12-128 个字符。', 'New password must be between 12 and 128 characters.'))
      return
    }
    if (newPassword !== passwordConfirmation) {
      setActionError(text('两次输入的新密码不一致。', 'The new passwords do not match.'))
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
      ({ revokedSessionCount }) => text(
        `密码已更新，已撤销 ${revokedSessionCount} 个其他会话。`,
        `Password updated. ${revokedSessionCount} other session${revokedSessionCount === 1 ? '' : 's'} revoked.`,
      ),
    )
  }

  return (
    <article className="account-management-page account-settings-page">
      <header className="account-management-hero">
        <div>
          <h1>{text('账户设置', 'Account settings')}</h1>
          <p>{text('管理个人资料、积分、安全与隐私。', 'Manage your profile, credits, security, and privacy.')}</p>
        </div>
        <div className="account-management-identity">
          <span aria-hidden="true"><UserCircleIcon size={21} weight="regular" /></span>
          <div>
            <strong>{account.displayName ?? text('研究者', 'Researcher')}</strong>
            <small>{account.email}</small>
          </div>
          <span className="account-management-badge">
            {account.role === 'admin' ? text('管理员', 'Admin') : text('内测用户', 'Beta user')}
          </span>
        </div>
        {account.role === 'admin' ? (
          <a className="account-management-admin-link" href={adminHref}>
            {text('打开用户管理', 'Open user management')}
          </a>
        ) : null}
      </header>

      <div className="account-management-layout">
        <nav className="account-settings-nav" aria-label={text('账户设置分区', 'Account settings sections')}>
          {settingsPartitions.map((partition) => (
            <button
              className={activePartition === partition ? 'is-active' : undefined}
              type="button"
              key={partition}
              aria-current={activePartition === partition ? 'page' : undefined}
              onClick={() => {
                setActivePartition(partition)
                setFeedback(null)
                setActionError(null)
              }}
            >
              {partitionLabels[partition]}
            </button>
          ))}
          <button className="account-settings-nav__logout" type="button" onClick={onLogout}>
            {text('退出登录', 'Sign out')}
          </button>
        </nav>

        <div className="account-settings-sections">
          {feedback ? <p className="account-management-feedback" role="status" aria-live="polite">{feedback}</p> : null}
          {actionError ? <p className="account-management-alert" role="alert">{actionError}</p> : null}

          {activePartition === 'profile' ? (
          <section className="account-settings-section" id="account-profile" aria-labelledby="account-profile-title">
            <div className="account-settings-section__heading">
              <span aria-hidden="true"><UserCircleIcon size={18} weight="regular" /></span>
              <div>
                <h2 id="account-profile-title">{text('个人资料', 'Profile')}</h2>
                <p>{text('这些信息会出现在你的研究档案中。', 'This information appears in your research profile.')}</p>
              </div>
            </div>
            <form className="account-management-form account-management-form--inline" onSubmit={submitProfile} noValidate>
              <label>
                <span>{text('显示名称', 'Display name')}</span>
                <input
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  maxLength={80}
                  autoComplete="name"
                  required
                />
              </label>
              <label>
                <span>{text('邮箱', 'Email')}</span>
                <input value={account.email} readOnly aria-describedby="account-email-help" />
                <small id="account-email-help">{text('邮箱用于登录，内测期间如需变更请联系管理员。', 'This email is used to sign in. Contact an administrator to change it during beta.')}</small>
              </label>
              <div className="account-management-form__actions">
                <button className="account-management-button account-management-button--primary" type="submit" disabled={pending}>
                  {pendingAction === 'profile' ? text('正在保存…', 'Saving…') : text('保存资料', 'Save profile')}
                </button>
              </div>
            </form>
          </section>
          ) : null}

          {activePartition === 'credits' ? (
          <section className="account-settings-section account-credit-section" id="account-credits" aria-labelledby="account-credits-title">
            <div className="account-settings-section__heading">
              <span aria-hidden="true"><CoinsIcon size={18} weight="regular" /></span>
              <div>
                <h2 id="account-credits-title">{text('积分与用量', 'Credits & usage')}</h2>
                <p>{text('对话按模型实际返回的 token 结算，失败或中止的回答不扣积分。', 'Conversations are charged from actual model token usage. Failed or interrupted responses are not charged.')}</p>
              </div>
            </div>
            <div className="account-credit-overview">
              <div className="account-credit-meter">
                <div className="account-credit-meter__heading">
                  <div className="account-credit-meter__label">
                    <span>{text('积分余额', 'Credit balance')}</span>
                    <small>{credits.isUnlimited
                      ? text('管理员账户不扣减积分', 'Administrator usage does not consume credits')
                      : text('当前剩余 / 额度上限', 'Remaining / credit limit')}</small>
                  </div>
                  <div className="account-credit-meter__value">
                    <strong>{credits.isUnlimited
                      ? text('无限', 'Unlimited')
                      : `${credits.balance.toLocaleString(locale)} / ${credits.creditLimit.toLocaleString(locale)}`}</strong>
                    <span>{credits.isUnlimited
                      ? text('不设上限', 'No limit')
                      : text(`剩余 ${creditRemainingPercentage}%`, `${creditRemainingPercentage}% left`)}</span>
                  </div>
                </div>
                {!credits.isUnlimited ? (
                  <div
                    className="account-credit-meter__track"
                    role="progressbar"
                    aria-label={text('积分余额', 'Credit balance')}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={creditRemainingPercentage}
                  >
                    <span style={{ width: `${creditRemainingPercentage}%` }} />
                  </div>
                ) : (
                  <div className="account-credit-meter__track is-unlimited" aria-hidden="true"><span /></div>
                )}
              </div>
            </div>
            {!credits.isUnlimited ? (
              <form className="account-credit-redemption" onSubmit={submitCreditRedemption}>
                <div>
                  <h3>{text('兑换码', 'Redemption code')}</h3>
                  <p>{text('每个兑换码仅可使用一次', 'Each code can be used once')}</p>
                </div>
                <label>
                  <span className="sr-only">{text('积分兑换码', 'Credit redemption code')}</span>
                  <input
                    aria-label={text('积分兑换码', 'Credit redemption code')}
                    autoComplete="off"
                    maxLength={64}
                    placeholder="QX-XXXX-XXXX-XXXX-XXXX"
                    value={creditCode}
                    onChange={(event) => setCreditCode(event.target.value)}
                  />
                </label>
                <button
                  className="account-management-button account-management-button--primary"
                  type="submit"
                  disabled={pending || !creditCode.trim()}
                >
                  {pendingAction === 'credit-redemption'
                    ? text('正在兑换…', 'Redeeming…')
                    : text('兑换积分', 'Redeem credits')}
                </button>
              </form>
            ) : null}
            <div className="account-credit-ledger">
              <div className="account-credit-ledger__heading">
                <h3>{text('积分消耗记录', 'Credit usage')}</h3>
                <span>{text(`共 ${credits.totalEntries} 笔`, `${credits.totalEntries} total`)}</span>
              </div>
              {credits.entries.length > 0 ? (
                <div className="account-credit-ledger__rows">
                  {credits.entries.map((entry) => (
                    <article className="account-credit-entry" key={entry.entryId}>
                      <div>
                        <strong>{entry.kind === 'usage'
                          ? text('Agent 对话', 'Agent conversation')
                          : entry.kind === 'redemption'
                            ? text('兑换码到账', 'Code redemption')
                            : text('新用户赠送', 'Welcome credits')}</strong>
                        <small>{formattedDate(entry.createdAt, locale)}</small>
                      </div>
                      <p>
                        {entry.kind === 'signup_grant'
                          ? text('欢迎加入群学致知', 'Welcome to Qunxue Zhizhi')
                          : text(
                            `${entry.inputTokens.toLocaleString('zh-CN')} 输入 · ${entry.outputTokens.toLocaleString('zh-CN')} 输出 token`,
                            `${entry.inputTokens.toLocaleString('en-US')} input · ${entry.outputTokens.toLocaleString('en-US')} output tokens`,
                          )}
                      </p>
                      <strong className={entry.points > 0 ? 'is-credit' : undefined}>
                        {entry.points > 0 ? '+' : ''}{entry.points.toLocaleString(locale)}
                      </strong>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="account-settings-empty">{text('完成首轮对话后，用量流水会出现在这里。', 'Usage will appear here after your first conversation.')}</p>
              )}
              {credits.totalEntries > creditPageSize || creditPage > 1 ? (
                <nav className="account-credit-pagination" aria-label={text('积分消耗记录分页', 'Credit usage pagination')}>
                  <button
                    className="account-management-button account-management-button--quiet"
                    type="button"
                    aria-label={text('上一页积分消耗记录', 'Previous credit usage page')}
                    disabled={pending || creditPage === 1}
                    onClick={() => void loadCreditPage(
                      creditPage - 1,
                      creditPage > 2 ? String((creditPage - 2) * creditPageSize) : undefined,
                    )}
                  >{text('上一页', 'Previous')}</button>
                  <span>{text(`第 ${creditPage} 页`, `Page ${creditPage}`)}</span>
                  <button
                    className="account-management-button account-management-button--quiet"
                    type="button"
                    aria-label={text('下一页积分消耗记录', 'Next credit usage page')}
                    disabled={pending || !credits.nextCursor}
                    onClick={() => void loadCreditPage(creditPage + 1, credits.nextCursor ?? undefined)}
                  >{text('下一页', 'Next')}</button>
                </nav>
              ) : null}
            </div>
          </section>
          ) : null}

          {activePartition === 'preferences' ? (
          <section className="account-settings-section" id="account-preferences" aria-labelledby="account-preferences-title">
            <div className="account-settings-section__heading">
              <span aria-hidden="true"><BellIcon size={18} weight="regular" /></span>
              <div>
                <h2 id="account-preferences-title">{text('使用偏好', 'Preferences')}</h2>
                <p>{text('设置时区、界面语言与内测进度通知。', 'Choose your language, time zone, and beta notifications.')}</p>
              </div>
            </div>
            <form className="account-management-form" onSubmit={submitPreferences}>
              <div className="account-management-form__grid">
                <label>
                  <span>{text('界面语言', 'Interface language')}</span>
                  <select
                    value={locale}
                    onChange={(event) => {
                      const nextLocale = event.target.value === 'en-US' ? 'en-US' : 'zh-CN'
                      setLocale(nextLocale)
                      setAppLocale(nextLocale)
                    }}
                  >
                    <option value="zh-CN">{text('简体中文', 'Chinese (Simplified)')}</option>
                    <option value="en-US">English</option>
                  </select>
                </label>
                <label>
                  <span>{text('时区', 'Time zone')}</span>
                  <select value={timezone} onChange={(event) => setTimezone(event.target.value)}>
                    <option value="Asia/Shanghai">{text('中国标准时间', 'China Standard Time')}</option>
                    <option value="UTC">{text('协调世界时', 'Coordinated Universal Time')}</option>
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
                  <strong>{text('研究进度与内测通知', 'Research progress and beta updates')}</strong>
                  <small>{text('仅发送与你的研究或内测资格直接相关的邮件。', 'Only receive emails directly related to your research or beta access.')}</small>
                </span>
              </label>
              <div className="account-management-form__actions">
                <button className="account-management-button" type="submit" disabled={pending}>
                  {pendingAction === 'preferences' ? text('正在保存…', 'Saving…') : text('保存偏好', 'Save preferences')}
                </button>
              </div>
            </form>
          </section>
          ) : null}

          {activePartition === 'security' ? (
          <section className="account-settings-section" id="account-security" aria-labelledby="account-security-title">
            <div className="account-settings-section__heading">
              <span aria-hidden="true"><LockKeyIcon size={18} weight="regular" /></span>
              <div>
                <h2 id="account-security-title">{text('安全', 'Security')}</h2>
                <p>{text('更新密码，并检查仍然有效的登录会话。', 'Update your password and review active sessions.')}</p>
              </div>
            </div>
            <form className="account-management-form" onSubmit={submitPassword} noValidate>
              <div className="account-management-form__grid account-management-form__grid--password">
                <label>
                  <span>{text('当前密码', 'Current password')}</span>
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
                  <span>{text('新密码', 'New password')}</span>
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
                  <span>{text('确认新密码', 'Confirm new password')}</span>
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
                  <strong>{text('撤销其他设备的会话', 'Sign out other devices')}</strong>
                  <small>{text('建议保持开启，当前设备不会退出。', 'Recommended. Your current device stays signed in.')}</small>
                </span>
              </label>
              <div className="account-management-form__actions">
                <button className="account-management-button account-management-button--primary" type="submit" disabled={pending || !currentPassword}>
                  {pendingAction === 'password' ? text('正在更新…', 'Updating…') : text('更新密码', 'Update password')}
                </button>
              </div>
            </form>

            <div className="account-settings-subsection">
              <div className="account-settings-subsection__heading">
                <div>
                  <h3>{text('活跃会话', 'Active sessions')}</h3>
                  <p>{text('如果不认识某个设备，立即撤销它的访问。', 'Revoke access immediately if you do not recognize a device.')}</p>
                </div>
                <span>{text(`${sessions.length} 个会话`, `${sessions.length} session${sessions.length === 1 ? '' : 's'}`)}</span>
              </div>
              <div className="account-session-list">
                {sessions.map((session) => (
                  <article className="account-session" key={session.sessionId}>
                    <span className="account-session__icon" aria-hidden="true">
                      <MonitorIcon size={18} weight="regular" />
                    </span>
                    <div>
                      <h4>{session.deviceLabel}</h4>
                      <p>{text('最后活动', 'Last active')} {formattedDate(session.lastSeenAt, locale)}{session.ipAddress ? ` · ${session.ipAddress}` : ''}</p>
                    </div>
                    {session.current ? (
                      <span className="account-management-badge account-management-badge--current">{text('当前设备', 'Current device')}</span>
                    ) : (
                      <button
                        className="account-management-button account-management-button--quiet"
                        type="button"
                        aria-label={text(`撤销 ${session.deviceLabel} 会话`, `Revoke ${session.deviceLabel} session`)}
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
                  </article>
                ))}
              </div>
              {otherSessions.length === 0 ? (
                <p className="account-settings-empty">
                  <strong>{text('没有其他活跃会话', 'No other active sessions')}</strong>
                  <span>{text('。只有你当前的设备保持登录。', '. Only your current device is signed in.')}</span>
                </p>
              ) : null}
            </div>
          </section>
          ) : null}

          {activePartition === 'privacy' ? (
          <section className="account-settings-section" id="account-privacy" aria-labelledby="account-privacy-title">
            <div className="account-settings-section__heading">
              <span aria-hidden="true"><DatabaseIcon size={18} weight="regular" /></span>
              <div>
                <h2 id="account-privacy-title">{text('数据与隐私', 'Data & privacy')}</h2>
                <p>{text('你可以决定研究数据的二次使用边界，并取回个人数据副本。', 'Control secondary use of your research data and request a copy of your personal data.')}</p>
              </div>
            </div>
            <div className="account-privacy-row">
              <div>
                <h3>{text('允许用于改进模型', 'Allow model improvement')}</h3>
                <p>{text('群学致知当前不会把你的研究数据用于训练。此开关默认关闭，只记录你对未来可选改进计划的授权；研究功能所需推理不受影响。', 'Qunxue Zhizhi does not currently use your research data for training. This optional consent is off by default and does not affect inference required for research features.')}</p>
                <small>{text('授权政策', 'Consent policy')} {account.preferences.consentPolicyVersion} · {text('更新于', 'Updated')} {formattedDate(account.preferences.consentUpdatedAt, locale)}</small>
              </div>
              <button
                className="account-switch-control"
                type="button"
                role="switch"
                aria-checked={account.preferences.modelImprovementAllowed}
                aria-label={text('允许用于改进模型', 'Allow model improvement')}
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
                <h3>{text('导出个人数据', 'Export personal data')}</h3>
                <p>{text('导出包含账户资料、研究任务与模型交互记录，不包含密码或会话凭据。', 'The export includes your profile, research tasks, and model interaction records. Passwords and session credentials are excluded.')}</p>
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
                  text('数据副本已准备。', 'Your data copy is ready.'),
                )}
              >
                {pendingAction === 'export' ? text('正在准备…', 'Preparing…') : text('导出我的数据', 'Export my data')}
              </button>
            </div>
            {dataExport ? (
              <div className="account-export-result" role="status">
                {dataExport.status === 'ready' && dataExport.downloadHref ? (
                  <>
                    <span>{text('副本已生成，下载链接将于', 'Your copy is ready. The download link expires')} {formattedDate(dataExport.expiresAt, locale)}.</span>
                    <a href={dataExport.downloadHref} download>{text('下载数据副本', 'Download data copy')}</a>
                  </>
                ) : (
                  <span>{text('数据副本正在准备，请稍后重新查看。', 'Your data copy is being prepared. Check again later.')}</span>
                )}
              </div>
            ) : null}
          </section>
          ) : null}

          {activePartition === 'danger' ? (
          <section className="account-settings-section account-settings-section--danger" id="account-danger" aria-labelledby="account-danger-title">
            <div className="account-settings-section__heading">
              <span aria-hidden="true"><WarningIcon size={18} weight="regular" /></span>
              <div>
                <h2 id="account-danger-title">{text('账户状态', 'Account status')}</h2>
                <p>{text('先选择可恢复的停用；只有在确认不再需要数据时才永久删除。', 'Deactivate for a recoverable pause. Delete only when you no longer need the data.')}</p>
              </div>
            </div>
            {account.isProtectedAdmin ? (
              <div className="account-protected-admin-notice">
                <span aria-hidden="true"><ShieldCheckIcon size={20} weight="regular" /></span>
                <div>
                  <h3>{text('部署管理员保护', 'Deployment admin protection')}</h3>
                  <p>{text('这个账户负责内测环境恢复，不能被降级、停用或删除。你仍可更新密码与撤销其他会话。', 'This account protects beta environment recovery and cannot be demoted, deactivated, or deleted. You can still update its password and revoke sessions.')}</p>
                </div>
              </div>
            ) : (
              <>
                <div className="account-danger-row">
                  <span aria-hidden="true"><PowerIcon size={19} weight="regular" /></span>
                  <div>
                    <h3>{text('停用账户', 'Deactivate account')}</h3>
                    <p>{text('立即退出所有设备并暂停访问。研究数据保留，管理员可在核验后恢复账户。', 'Sign out all devices and pause access. Research data is retained, and an administrator can restore the account after verification.')}</p>
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
                    {text('停用账户', 'Deactivate account')}
                  </button>
                </div>
                <div className="account-danger-row account-danger-row--irreversible">
                  <span aria-hidden="true"><TrashIcon size={19} weight="regular" /></span>
                  <div>
                    <h3>{text('永久删除账户', 'Permanently delete account')}</h3>
                    <p>{text('删除账户、研究任务、派生文档与个人模型交互记录。删除后无法恢复。', 'Delete your account, research tasks, derived documents, and personal model interaction records. This cannot be undone.')}</p>
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
                    {text('永久删除账户', 'Permanently delete account')}
                  </button>
                </div>
              </>
            )}
          </section>
          ) : null}
        </div>
      </div>

      {sessionToRevoke ? (
        <AccountConfirmationDialog
          title={text('撤销这个会话？', 'Revoke this session?')}
          description={text(`${sessionToRevoke.deviceLabel} 将立即退出，未保存的操作可能丢失。`, `${sessionToRevoke.deviceLabel} will be signed out immediately. Unsaved work may be lost.`)}
          confirmLabel={text('确认撤销', 'Revoke session')}
          cancelLabel={text('取消', 'Cancel')}
          pendingLabel={text('正在撤销…', 'Revoking…')}
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
            text('会话已撤销。', 'Session revoked.'),
          )}
        />
      ) : null}

      {modelAuthorizationTarget !== null ? (
        <AccountConfirmationDialog
          title={modelAuthorizationTarget ? text('允许用于改进模型？', 'Allow model improvement?') : text('停止用于改进模型？', 'Stop model improvement access?')}
          description={modelAuthorizationTarget
            ? text('群学致知当前不使用你的数据训练模型。开启仅记录未来可选改进计划的授权；任何实际启用仍会另行告知。', 'Qunxue Zhizhi does not currently train on your data. Enabling this only records consent for a future optional improvement program; you will be notified before any actual use.')
            : text('停止后，未来可选改进计划不再取得你的授权；研究功能所需推理不受影响。', 'Future optional improvement programs will no longer have your consent. Inference required for research features is unaffected.')}
          confirmLabel={modelAuthorizationTarget ? text('确认允许', 'Allow') : text('确认停止', 'Stop allowing')}
          cancelLabel={text('取消', 'Cancel')}
          pendingLabel={text('正在处理…', 'Updating…')}
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
            modelAuthorizationTarget
              ? text('模型数据授权已开启。', 'Model improvement consent enabled.')
              : text('模型数据授权已关闭。', 'Model improvement consent disabled.'),
          )}
        />
      ) : null}

      {deactivationOpen ? (
        <AccountConfirmationDialog
          title={text('停用账户？', 'Deactivate account?')}
          description={text('停用后你会立即退出所有设备。数据会保留，管理员可在核验后恢复访问。', 'You will be signed out on every device. Your data is retained, and an administrator can restore access after verification.')}
          confirmLabel={text('确认停用', 'Deactivate')}
          cancelLabel={text('取消', 'Cancel')}
          pendingLabel={text('正在停用…', 'Deactivating…')}
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
            text('账户已停用。', 'Account deactivated.'),
          )}
        >
          <div className="account-management-form">
            <label>
              <span>{text('当前密码', 'Current password')}</span>
              <input type="password" value={deactivationPassword} onChange={(event) => setDeactivationPassword(event.target.value)} autoComplete="current-password" />
            </label>
            <label>
              <span>{text('停用原因', 'Reason for deactivation')}</span>
              <textarea value={deactivationReason} onChange={(event) => setDeactivationReason(event.target.value)} maxLength={240} rows={3} />
            </label>
          </div>
        </AccountConfirmationDialog>
      ) : null}

      {deletionOpen ? (
        <AccountConfirmationDialog
          title={text('永久删除账户？', 'Permanently delete account?')}
          description={text('账户、研究任务、派生文档与个人模型交互记录将被永久删除。删除后无法恢复。', 'Your account, research tasks, derived documents, and personal model interaction records will be permanently deleted. This cannot be undone.')}
          confirmLabel={text('确认永久删除', 'Permanently delete')}
          cancelLabel={text('取消', 'Cancel')}
          pendingLabel={text('正在删除…', 'Deleting…')}
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
            text('账户已永久删除。', 'Account permanently deleted.'),
          )}
        >
          <div className="account-management-form">
            <label>
              <span>{text('账户邮箱', 'Account email')}</span>
              <input value={deletionEmail} onChange={(event) => setDeletionEmail(event.target.value)} autoComplete="email" placeholder={account.email} />
            </label>
            <label>
              <span>{text('当前密码', 'Current password')}</span>
              <input type="password" value={deletionPassword} onChange={(event) => setDeletionPassword(event.target.value)} autoComplete="current-password" />
            </label>
          </div>
        </AccountConfirmationDialog>
      ) : null}
    </article>
  )
}
