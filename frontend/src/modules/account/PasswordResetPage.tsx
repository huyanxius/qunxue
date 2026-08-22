import { CheckCircleIcon, LockKeyIcon } from '@phosphor-icons/react'
import { useRef, useState } from 'react'
import type { FormEvent } from 'react'

import brandMark from '../../assets/qunxue-brand-mark.svg'
import {
  isAccountManagementRequestError,
  type AccountManagementApi,
} from './accountManagementModels'
import { accountManagementApi } from './accountManagementApi'
import { MutationIntentLedger } from './mutationIntent'
import './account-management.css'

type PasswordResetPageProps = {
  api?: AccountManagementApi
  token: string
  loginHref: string
  onReset?(): void
}

export function PasswordResetPage({
  api = accountManagementApi,
  token,
  loginHref,
  onReset,
}: PasswordResetPageProps) {
  const submittingRef = useRef(false)
  const mutationIntents = useRef(new MutationIntentLedger())
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [completed, setCompleted] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submittingRef.current) return

    const data = new FormData(event.currentTarget)
    const password = String(data.get('password') ?? '')
    const confirmation = String(data.get('confirmation') ?? '')
    if (password.length < 12 || password.length > 128) {
      setError('密码需要 12-128 个字符。')
      return
    }
    if (password !== confirmation) {
      setError('两次输入的密码不一致。')
      return
    }

    submittingRef.current = true
    setSubmitting(true)
    setError(null)
    try {
      const intent = { token, newPassword: password }
      await api.consumePasswordReset({
        ...intent,
        idempotencyKey: mutationIntents.current.keyFor('password-reset', intent),
      })
      mutationIntents.current.complete('password-reset')
      setCompleted(true)
      onReset?.()
    } catch (failure) {
      setError(
        isAccountManagementRequestError(failure) && failure.status === 410
          ? '重置链接已过期或已使用。请联系管理员创建新链接。'
          : '暂时无法重设密码。请检查网络后重试。',
      )
    } finally {
      submittingRef.current = false
      setSubmitting(false)
    }
  }

  if (completed) {
    return (
      <main className="account-flow" aria-labelledby="password-reset-success-title">
        <section className="account-flow__sheet account-flow__sheet--success">
          <span className="account-flow__result-icon" aria-hidden="true">
            <CheckCircleIcon size={24} weight="regular" />
          </span>
          <p className="account-flow__eyebrow">PASSWORD UPDATED</p>
          <h1 id="password-reset-success-title">密码已重设</h1>
          <p>
            <strong>所有旧会话都已撤销</strong>
            <span>。请使用新密码重新登录。</span>
          </p>
          <a className="account-management-button account-management-button--primary" href={loginHref}>
            使用新密码登录
          </a>
        </section>
      </main>
    )
  }

  if (!token.trim()) {
    return (
      <main className="account-flow" aria-labelledby="invalid-reset-title">
        <section className="account-flow__sheet" role="alert">
          <p className="account-flow__eyebrow">PASSWORD RESET</p>
          <h1 id="invalid-reset-title">重置链接无效</h1>
          <p>链接中缺少必要的重置信息。请联系管理员创建新链接。</p>
        </section>
      </main>
    )
  }

  return (
    <main className="account-flow" aria-labelledby="password-reset-title">
      <section className="account-flow__sheet">
        <header className="account-flow__header">
          <img src={brandMark} alt="" aria-hidden="true" />
          <span className="account-flow__header-icon" aria-hidden="true">
            <LockKeyIcon size={18} weight="regular" />
          </span>
          <p className="account-flow__eyebrow">ACCOUNT SECURITY</p>
          <h1 id="password-reset-title">重设密码</h1>
          <p>新密码生效后，所有旧会话会被撤销。</p>
        </header>

        <form className="account-management-form" onSubmit={submit} noValidate>
          <label>
            <span>新密码</span>
            <input
              name="password"
              aria-label="新密码"
              type="password"
              autoComplete="new-password"
              minLength={12}
              maxLength={128}
              aria-describedby="reset-password-help"
              required
            />
            <small id="reset-password-help">12-128 个字符，请使用不同于其他网站的密码。</small>
          </label>
          <label>
            <span>确认新密码</span>
            <input
              name="confirmation"
              aria-label="确认新密码"
              type="password"
              autoComplete="new-password"
              minLength={12}
              maxLength={128}
              required
            />
          </label>
          {error ? <p className="account-management-alert" role="alert">{error}</p> : null}
          <button
            className="account-management-button account-management-button--primary"
            type="submit"
            disabled={submitting}
          >
            {submitting ? '正在重设…' : '重设密码'}
          </button>
        </form>
        <p className="account-flow__footer">想起密码了？<a href={loginHref}>返回登录</a></p>
      </section>
    </main>
  )
}
