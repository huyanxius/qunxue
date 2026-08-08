import { useState } from 'react'
import type { PropsWithChildren, ReactNode } from 'react'
import { Link, NavLink, useNavigate } from 'react-router'

import { useAccount } from '../../modules/account'

import brandMark from '../../assets/qunxue-brand-mark.svg'

type PageTitleProps = {
  eyebrow: string
  title: string
  lede?: string
}

const navigationItems = [
  { href: '/', label: '首页', mark: '·', end: true },
  { href: '/knowledge', label: '知识', mark: '知' },
  { href: '/research/new', label: '研究', mark: '研' },
  { href: '/my', label: '我的', mark: '我' },
]

function PrimaryNavigation({
  className,
  label,
}: {
  className: string
  label: string
}) {
  return (
    <nav className={className} aria-label={label}>
      {navigationItems.map(({ href, label: itemLabel, mark, end }) => (
        <NavLink key={href} to={href} end={end}>
          <span aria-hidden="true">{mark}</span>
          <span>{itemLabel}</span>
        </NavLink>
      ))}
    </nav>
  )
}

export function PageShell({ children }: PropsWithChildren) {
  const account = useAccount()
  const navigate = useNavigate()
  const [logoutFailed, setLogoutFailed] = useState(false)

  async function logout() {
    setLogoutFailed(false)
    try {
      await account.logout(() => {
        navigate('/', { replace: true })
      })
    } catch {
      setLogoutFailed(true)
    }
  }

  return (
    <div className="app-frame">
      <header className="masthead">
        <Link className="wordmark" to="/" aria-label="群学致知首页">
          <img src={brandMark} alt="" />
          <span className="wordmark__copy">
            <strong>群学致知</strong>
            <small>COLLECTIVE INQUIRY</small>
          </span>
        </Link>
        <span className="masthead__context">社会学理论发现与研究设计</span>
        <nav className="account-navigation" aria-label="账户导航">
          {account.sessionState.status === 'authenticated' ? (
            <>
              <NavLink className="account-navigation__research" to="/my">我的研究</NavLink>
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

      <aside className="desktop-rail">
        <PrimaryNavigation className="desktop-navigation" label="桌面主导航" />
      </aside>

      <main className="page-shell">{children}</main>

      <PrimaryNavigation className="mobile-navigation" label="移动主导航" />
    </div>
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
