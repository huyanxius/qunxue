import { useState } from 'react'
import type { FormEvent, ReactNode } from 'react'

import brandMark from '../../assets/qunxue-brand-mark.svg'
import { isLoginServiceFailure } from './accountApi'
import { AccountPaperShader } from './AccountPaperShader'
import './account.css'

type LoginPageProps = {
  onLogin(email: string, password: string): Promise<unknown>
  onAuthenticated(): void
  registerHref: string
  sessionExpired?: boolean
}

type RegisterPageProps = {
  onRegister(email: string, password: string): Promise<unknown>
  onAuthenticated(): void
  loginHref: string
}

const emailPattern = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

function AccountPortal({
  kind,
  title,
  formLabel,
  children,
  switcher,
}: {
  kind: 'login' | 'register'
  title: string
  formLabel: string
  children: ReactNode
  switcher: ReactNode
}) {
  return (
    <section className={`account-portal account-portal--${kind}`} aria-labelledby={`account-${kind}-title`}>
      <div className="account-paper-field" aria-hidden="true">
        <AccountPaperShader />
      </div>
      <div className="account-portal__story">
        <img className="account-portal__brand-echo" src={brandMark} alt="" aria-hidden="true" />
        <a className="account-portal__brand" href="/" aria-label="返回群学致知首页">
          <span className="account-portal__brand-mark"><img src={brandMark} alt="" /></span>
          <span className="account-portal__brand-copy">
            <strong>群学致知</strong>
            <small>COLLECTIVE INQUIRY</small>
          </span>
        </a>
        <h1 id={`account-${kind}-title`}>{title}</h1>
        <div className="account-portal__axis" aria-hidden="true">
          <span>现象</span>
          <span>理论</span>
          <span>证据</span>
        </div>
      </div>

      <div className="account-portal__entry">
        <div className="account-portal__entry-inner">
          <div className="account-portal__form-heading">
            <img src={brandMark} alt="" aria-hidden="true" />
            <p className="account-portal__form-label">{formLabel}</p>
          </div>
          {children}
          {switcher}
        </div>
      </div>
    </section>
  )
}

export function LoginPage({
  onLogin,
  onAuthenticated,
  registerHref,
  sessionExpired = false,
}: LoginPageProps) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const email = String(data.get('email') ?? '').trim()
    const password = String(data.get('password') ?? '')
    if (
      !emailPattern.test(email)
      || email.length > 320
      || password.length < 8
      || password.length > 128
    ) {
      setError('请检查邮箱格式，密码需要 8-128 个字符。')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await onLogin(email, password)
      onAuthenticated()
    } catch (failure) {
      if (isLoginServiceFailure(failure)) {
        setError('登录服务暂时不可用，请稍后重试。')
      } else {
        setError('邮箱或密码不正确，请重新输入。')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AccountPortal
      kind="login"
      title="登录"
      formLabel="登录到研究档案"
      switcher={<p className="account-switch">还没有账号？<a href={registerHref}>创建账号</a></p>}
    >
      <form className="account-form" onSubmit={submit} noValidate>
        {sessionExpired ? (
          <p className="account-notice" role="status">登录已过期，请重新登录后继续。</p>
        ) : null}
        <label>
          <span>邮箱</span>
          <input name="email" type="email" autoComplete="email" maxLength={320} required />
        </label>
        <label>
          <span>密码</span>
          <input name="password" type="password" autoComplete="current-password" minLength={8} maxLength={128} required />
        </label>
        {error ? <p className="account-error" role="alert">{error}</p> : null}
        <button className="account-primary" type="submit" disabled={submitting}>
          {submitting ? '正在登录…' : '登录并继续'}
        </button>
      </form>
    </AccountPortal>
  )
}

export function RegisterPage({
  onRegister,
  onAuthenticated,
  loginHref,
}: RegisterPageProps) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const email = String(data.get('email') ?? '').trim()
    const password = String(data.get('password') ?? '')
    const confirmation = String(data.get('confirmation') ?? '')
    if (!emailPattern.test(email) || email.length > 320) {
      setError('请输入有效的邮箱地址。')
      return
    }
    if (password.length < 8 || password.length > 128) {
      setError('密码需要 8-128 个字符。')
      return
    }
    if (password !== confirmation) {
      setError('两次输入的密码不一致。')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await onRegister(email, password)
      onAuthenticated()
    } catch {
      setError('账号创建失败，请稍后重试。')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AccountPortal
      kind="register"
      title="注册"
      formLabel="创建研究档案"
      switcher={<p className="account-switch">已有账号？<a href={loginHref}>返回登录</a></p>}
    >
      <form className="account-form" onSubmit={submit} noValidate>
        <label>
          <span>邮箱</span>
          <input name="email" type="email" autoComplete="email" maxLength={320} required />
        </label>
        <div className="account-field">
          <label htmlFor="register-password">密码</label>
          <input id="register-password" name="password" type="password" autoComplete="new-password" minLength={8} maxLength={128} aria-describedby="password-help" required />
          <small id="password-help">8-128 个字符。</small>
        </div>
        <label>
          <span>确认密码</span>
          <input name="confirmation" type="password" autoComplete="new-password" minLength={8} maxLength={128} required />
        </label>
        {error ? <p className="account-error" role="alert">{error}</p> : null}
        <button className="account-primary" type="submit" disabled={submitting}>
          {submitting ? '正在创建…' : '创建账号'}
        </button>
      </form>
    </AccountPortal>
  )
}
