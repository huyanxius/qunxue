import { useState } from 'react'
import type { PropsWithChildren, ReactNode } from 'react'
import { Link, NavLink, useNavigate } from 'react-router'

import { useAccount } from '../../modules/account'

type PageTitleProps = {
  eyebrow: string
  title: string
  lede?: string
}

export function PageShell({ children }: PropsWithChildren) {
  const account = useAccount()
  const navigate = useNavigate()
  const [logoutFailed, setLogoutFailed] = useState(false)

  async function logout() {
    setLogoutFailed(false)
    try {
      await account.logout()
      navigate('/', { replace: true })
    } catch {
      setLogoutFailed(true)
    }
  }

  return (
    <main className="page-shell">
      <header className="masthead">
        <Link className="wordmark" to="/" aria-label="群学致知首页">
          <span className="wordmark-mark" aria-hidden="true">群</span>
          <span>群学致知</span>
        </Link>
        <nav className="app-navigation" aria-label="主导航">
          <NavLink to="/knowledge">知识</NavLink>
          <NavLink to="/research/new">研究</NavLink>
          {account.sessionState.status === 'authenticated' ? (
            <>
              <NavLink to="/my">我的研究</NavLink>
              <span className="session-email">{account.sessionState.session.user.email}</span>
              <button className="nav-action" type="button" onClick={logout}>
                {logoutFailed ? '退出失败，请重试' : '退出'}
              </button>
            </>
          ) : account.sessionState.status === 'loading' ? (
            <span className="session-email">确认中</span>
          ) : (
            <NavLink to="/login">登录</NavLink>
          )}
        </nav>
      </header>
      {children}
    </main>
  )
}

export function PageTitle({ eyebrow, title, lede }: PageTitleProps) {
  return (
    <header className="page-title">
      <p className="eyebrow">{eyebrow}</p>
      <h1 className="display-title">{title}</h1>
      {lede ? <p className="page-title__lede">{lede}</p> : null}
    </header>
  )
}

export function PageContent({ children }: { children: ReactNode }) {
  return <section className="page-content">{children}</section>
}
