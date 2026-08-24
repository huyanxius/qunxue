import { EyeIcon, EyeSlashIcon } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'

import brandMark from '../../assets/qunxue-brand-mark.svg'
import {
  isLoginServiceFailure,
  registrationCodeFailureMessage,
  registrationFailureMessage,
} from './accountApi'
import { AccountPaperShader } from './AccountPaperShader'
import './account.css'

type LoginPageProps = {
  onLogin(email: string, password: string): Promise<unknown>
  onAuthenticated(): void
  registerHref: string
  sessionExpired?: boolean
}

type RegisterPageProps = {
  onRegister(email: string, password: string, verificationCode: string): Promise<unknown>
  onSendRegistrationCode(email: string): Promise<{ resendAfterSeconds: number }>
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
  const [passwordVisible, setPasswordVisible] = useState(false)

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
        <div className="account-field">
          <label htmlFor="login-password">密码</label>
          <div className="account-password-field">
            <input
              id="login-password"
              className="account-password-field__input"
              name="password"
              type={passwordVisible ? 'text' : 'password'}
              autoComplete="current-password"
              minLength={8}
              maxLength={128}
              required
            />
            <button
              className="account-password-field__toggle"
              type="button"
              aria-label={passwordVisible ? '隐藏密码' : '显示密码'}
              aria-pressed={passwordVisible}
              onClick={() => setPasswordVisible((visible) => !visible)}
            >
              {passwordVisible ? <EyeSlashIcon aria-hidden="true" /> : <EyeIcon aria-hidden="true" />}
            </button>
          </div>
        </div>
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
  onSendRegistrationCode,
  onAuthenticated,
  loginHref,
}: RegisterPageProps) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [step, setStep] = useState<'email' | 'code' | 'password'>('email')
  const [email, setEmail] = useState('')
  const [verificationCode, setVerificationCode] = useState('')
  const [resendAfter, setResendAfter] = useState(0)

  useEffect(() => {
    if (resendAfter <= 0) return
    const timer = window.setTimeout(() => setResendAfter((value) => Math.max(0, value - 1)), 1000)
    return () => window.clearTimeout(timer)
  }, [resendAfter])

  async function sendCode(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault()
    const normalizedEmail = email.trim()
    if (!emailPattern.test(normalizedEmail) || normalizedEmail.length > 320) {
      setError('请输入有效的邮箱地址。')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const result = await onSendRegistrationCode(normalizedEmail)
      setEmail(normalizedEmail)
      setResendAfter(result.resendAfterSeconds)
      setStep('code')
    } catch (failure) {
      setError(registrationCodeFailureMessage(failure))
    } finally {
      setSubmitting(false)
    }
  }

  function continueToPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!/^\d{6}$/.test(verificationCode)) {
      setError('请输入邮件中的 6 位验证码。')
      return
    }
    setError(null)
    setStep('password')
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const password = String(data.get('password') ?? '')
    const confirmation = String(data.get('confirmation') ?? '')
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
      await onRegister(email, password, verificationCode)
      onAuthenticated()
    } catch (failure) {
      setError(registrationFailureMessage(failure))
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
      <div className="account-register-progress" aria-live="polite">
        <span>第 {step === 'email' ? 1 : step === 'code' ? 2 : 3} 步，共 3 步</span>
        <span className="account-register-progress__track" aria-hidden="true">
          <span style={{ width: step === 'email' ? '33.333%' : step === 'code' ? '66.666%' : '100%' }} />
        </span>
      </div>
      {step === 'email' ? (
        <form className="account-form" onSubmit={sendCode} noValidate>
          <label>
            <span>邮箱</span>
            <input value={email} onChange={(event) => setEmail(event.target.value)} name="email" type="email" autoComplete="email" maxLength={320} required autoFocus />
          </label>
          {error ? <p className="account-error" role="alert">{error}</p> : null}
          <button className="account-primary" type="submit" disabled={submitting}>
            {submitting ? '正在发送…' : '发送验证码'}
          </button>
        </form>
      ) : step === 'code' ? (
        <form className="account-form" onSubmit={continueToPassword} noValidate>
          <div className="account-register-summary">
            <span>验证码已发送至</span><strong>{email}</strong>
            <button type="button" onClick={() => { setStep('email'); setError(null) }}>修改邮箱</button>
          </div>
          <label>
            <span>验证码</span>
            <input value={verificationCode} onChange={(event) => setVerificationCode(event.target.value.replace(/\D/g, '').slice(0, 6))} name="verification-code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required autoFocus />
          </label>
          {error ? <p className="account-error" role="alert">{error}</p> : null}
          <button className="account-primary" type="submit">继续设置密码</button>
          <button className="account-secondary" type="button" disabled={submitting || resendAfter > 0} onClick={() => void sendCode()}>
            {resendAfter > 0 ? `${resendAfter} 秒后可重新发送` : '重新发送验证码'}
          </button>
        </form>
      ) : (
        <form className="account-form" onSubmit={submit} noValidate>
          <div className="account-register-summary">
            <span>注册邮箱</span><strong>{email}</strong>
            <button type="button" onClick={() => { setStep('code'); setError(null) }}>返回验证码</button>
          </div>
          <div className="account-field">
            <label htmlFor="register-password">密码</label>
            <input id="register-password" name="password" type="password" autoComplete="new-password" minLength={8} maxLength={128} aria-describedby="password-help" required autoFocus />
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
      )}
    </AccountPortal>
  )
}
