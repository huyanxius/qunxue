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

type NavigationIconName = 'home' | 'workspace' | 'knowledge' | 'graph' | 'research' | 'account'

function NavigationIcon({ name }: { name: NavigationIconName }) {
  const paths: Record<NavigationIconName, ReactNode> = {
    home: (
      <>
        <path d="M4.4 12c1.9-4.2 4.4-6.3 7.6-6.3s5.7 2.1 7.6 6.3c-1.9 4.2-4.4 6.3-7.6 6.3S6.3 16.2 4.4 12Z" />
        <path d="M8.3 12c.9-1.7 2.1-2.6 3.7-2.6s2.8.9 3.7 2.6c-.9 1.7-2.1 2.6-3.7 2.6S9.2 13.7 8.3 12Z" />
        <circle className="navigation-icon__node" cx="12" cy="12" r="1.2" />
      </>
    ),
    workspace: (
      <>
        <path d="m10.1 10.3-1.5 1.5a3.9 3.9 0 0 1-5.5-5.5l2.2-2.2a3.9 3.9 0 0 1 5.5 0l1.1 1.1" />
        <path d="m13.9 13.7 1.5-1.5a3.9 3.9 0 0 1 5.5 5.5l-2.2 2.2a3.9 3.9 0 0 1-5.5 0l-1.1-1.1" />
        <path d="m8.4 15.6 7.2-7.2" />
        <circle className="navigation-icon__node" cx="12" cy="12" r="1.25" />
      </>
    ),
    knowledge: (
      <>
        <path d="M12 19.5V7.7" />
        <path d="M11.9 11.2C9 11.1 6.8 9.7 5.4 6.8c3-.2 5.3.8 6.5 3.1" />
        <path d="M12.1 14.5c2.8-.1 5-1.5 6.5-4.4-3-.2-5.3.8-6.5 3.2" />
        <circle className="navigation-icon__node" cx="12" cy="5.2" r="1.35" />
      </>
    ),
    graph: (
      <>
        <path d="M5 16.8C7.5 9.1 12 6.3 18.8 8.8" />
        <path d="M5 16.8c4.8 2.3 9.3 1.3 13.8-3.1" />
        <path d="M11.5 10.2c.7 3.2 2.4 5.1 5.2 5.8" />
        <circle className="navigation-icon__node" cx="5" cy="16.8" r="1.35" />
        <circle className="navigation-icon__node" cx="11.5" cy="10.2" r="1.15" />
        <circle className="navigation-icon__node" cx="18.8" cy="8.8" r="1.35" />
        <circle className="navigation-icon__node" cx="16.7" cy="16" r="1.15" />
      </>
    ),
    research: (
      <>
        <path d="M4.5 17.7c3.3 0 4.7-3.2 6.1-6.1 1.5-3.1 3.1-5.5 6.9-5.5" />
        <path d="m15.1 3.9 2.8 2.2-2.2 2.9" />
        <path d="M7.4 20.1c2.1-.7 3.7-2 4.8-3.8" />
        <circle className="navigation-icon__node" cx="4.5" cy="17.7" r="1.35" />
      </>
    ),
    account: (
      <>
        <circle cx="12" cy="7.5" r="2.7" />
        <path d="M5.3 19.5c1.1-4.2 3.4-6.2 6.7-6.2s5.6 2 6.7 6.2" />
        <path d="M8.7 17.1c1-.7 2.1-1 3.3-1s2.3.3 3.3 1" />
        <circle className="navigation-icon__node" cx="12" cy="7.5" r="0.75" />
      </>
    ),
  }

  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.45" strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  )
}

function LogoutIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.45" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M10.5 4.2H6.2a2 2 0 0 0-2 2v11.6a2 2 0 0 0 2 2h4.3" />
      <path d="M13.2 8.2 17 12l-3.8 3.8M8.8 12H17" />
    </svg>
  )
}

const navigationItems = [
  { href: '/', label: '首页', icon: 'home' as const, end: true },
  { href: '/app', label: '工作台', icon: 'workspace' as const, end: true },
  { href: '/knowledge', label: '知识', icon: 'knowledge' as const, end: true },
  { href: '/knowledge/graph', label: '图谱', icon: 'graph' as const },
  { href: '/research/new', label: '研究', icon: 'research' as const },
  { href: '/my', label: '我的', icon: 'account' as const },
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
      {navigationItems.map(({ href, label: itemLabel, icon, end }) => (
        <NavLink key={href} to={href} end={end}>
          <span className="navigation-icon" aria-hidden="true"><NavigationIcon name={icon} /></span>
          <span className="navigation-label">{itemLabel}</span>
        </NavLink>
      ))}
    </nav>
  )
}

export function PageShell({
  children,
  workspace = false,
  immersive = false,
}: PropsWithChildren<{ workspace?: boolean; immersive?: boolean }>) {
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
    <div className={`app-frame${immersive ? ' app-frame--immersive' : ''}`}>
      {immersive ? null : (
        <>
          <header className="masthead mobile-masthead">
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

          <aside className="desktop-rail" aria-label="群学致知功能栏">
            <Link className="desktop-rail__brand" to="/" aria-label="群学致知首页">
              <img src={brandMark} alt="" />
            </Link>
            <PrimaryNavigation className="desktop-navigation" label="桌面主导航" />
            <div className="desktop-rail__account">
              {account.sessionState.status === 'authenticated' ? (
                <>
                  <NavLink
                    to="/my"
                    aria-label={`账户 ${account.sessionState.session.user.email}`}
                    title={account.sessionState.session.user.email}
                  >
                    <NavigationIcon name="account" />
                  </NavLink>
                  <button
                    type="button"
                    aria-label={logoutFailed ? '退出失败，请重试' : '退出'}
                    title={logoutFailed ? '退出失败，请重试' : '退出'}
                    onClick={logout}
                  >
                    <LogoutIcon />
                  </button>
                </>
              ) : account.sessionState.status === 'loading' ? (
                <span className="desktop-rail__session" role="status" aria-label="正在确认账户" />
              ) : (
                <NavLink to="/login" aria-label="登录" title="登录">
                  <NavigationIcon name="account" />
                </NavLink>
              )}
            </div>
          </aside>
        </>
      )}

      <main className={[
        'page-shell',
        workspace ? 'page-shell--workspace' : '',
        immersive ? 'page-shell--immersive' : '',
      ].filter(Boolean).join(' ')}>{children}</main>

      {immersive ? null : <PrimaryNavigation className="mobile-navigation" label="移动主导航" />}
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
