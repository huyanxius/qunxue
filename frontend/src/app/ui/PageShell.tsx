import { useState } from 'react'
import type { PropsWithChildren, ReactNode } from 'react'
import { Link, NavLink, useNavigate } from 'react-router'
import {
  BooksIcon,
  ChatCircleDotsIcon,
  ClockCounterClockwiseIcon,
  GraphIcon,
  HouseIcon,
  PlusIcon,
  SidebarSimpleIcon,
  SignOutIcon,
  TreeStructureIcon,
  UserCircleIcon,
} from '@phosphor-icons/react'

import { useAccount } from '../../modules/account'

type PageTitleProps = {
  eyebrow: string
  title: string
  lede?: string
}

const navigationItems = [
  { href: '/app', label: '工作台', mobileLabel: '工作台', icon: HouseIcon, end: true },
  { href: '/agent', label: '研究 Agent', mobileLabel: 'Agent', icon: ChatCircleDotsIcon, end: true },
  { href: '/research/new', label: '新建研究', mobileLabel: '新建', icon: PlusIcon },
  { href: '/my', label: '我的研究', mobileLabel: '研究', icon: ClockCounterClockwiseIcon },
  { href: '/knowledge', label: '知识库', mobileLabel: '知识', icon: BooksIcon, end: true },
  { href: '/knowledge/graph', label: '知识图谱', mobileLabel: '图谱', icon: TreeStructureIcon },
]

function ProductMark() {
  return (
    <span className="product-mark" aria-hidden="true">
      <GraphIcon size={21} weight="regular" />
    </span>
  )
}

function PrimaryNavigation({
  className,
  label,
  compact = false,
}: {
  className: string
  label: string
  compact?: boolean
}) {
  return (
    <nav className={className} aria-label={label}>
      {navigationItems.map(({ href, label: itemLabel, mobileLabel, icon: NavigationIcon, end }) => (
        <NavLink key={href} to={href} end={end}>
          <span className="navigation-icon" aria-hidden="true">
            <NavigationIcon size={18} weight="regular" />
          </span>
          <span className="navigation-label">{compact ? mobileLabel : itemLabel}</span>
        </NavLink>
      ))}
    </nav>
  )
}

export function PageShell({
  children,
  workspace = false,
  immersive = false,
  wide = false,
  defaultRailCollapsed = false,
  railContent,
}: PropsWithChildren<{
  workspace?: boolean
  immersive?: boolean
  wide?: boolean
  defaultRailCollapsed?: boolean
  railContent?: ReactNode
}>) {
  const account = useAccount()
  const navigate = useNavigate()
  const [logoutFailed, setLogoutFailed] = useState(false)
  const [railCollapsed, setRailCollapsed] = useState(defaultRailCollapsed)

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
    <div className={[
      'app-frame',
      immersive ? 'app-frame--immersive' : '',
      railCollapsed && !immersive ? 'app-frame--rail-collapsed' : '',
    ].filter(Boolean).join(' ')}>
      {immersive ? null : (
        <>
          <a className="skip-link" href="#main-content">跳到主要内容</a>
          <header className="masthead mobile-masthead">
            <Link className="wordmark" to="/app" aria-label="群学致知工作台">
              <ProductMark />
              <strong>群学致知</strong>
            </Link>
            <nav className="account-navigation" aria-label="账户导航">
              {account.sessionState.status === 'authenticated' ? (
                <>
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

          <aside className={`desktop-rail${railCollapsed ? ' desktop-rail--collapsed' : ''}`} aria-label="群学致知功能栏">
            <div className="desktop-rail__topbar">
              <Link className="desktop-rail__brand" to="/app" aria-label="群学致知工作台">
                <ProductMark />
                <strong>群学致知</strong>
              </Link>
              <button
                className="desktop-rail__collapse"
                type="button"
                aria-label={railCollapsed ? '展开侧栏' : '收起侧栏'}
                title={railCollapsed ? '展开侧栏' : '收起侧栏'}
                onClick={() => setRailCollapsed((collapsed) => !collapsed)}
              >
                <SidebarSimpleIcon size={18} weight="regular" />
              </button>
            </div>
            <div className="desktop-rail__body">
              <PrimaryNavigation className="desktop-navigation" label="桌面主导航" />
              {railContent ? (
                <div className="desktop-rail__secondary">{railContent}</div>
              ) : null}
            </div>
            <div className="desktop-rail__account">
              {account.sessionState.status === 'authenticated' ? (
                <>
                  <NavLink
                    to="/my"
                    aria-label={`账户 ${account.sessionState.session.user.email}`}
                    title={account.sessionState.session.user.email}
                  >
                    <UserCircleIcon size={18} weight="regular" />
                    <span>
                      <strong>{account.sessionState.session.user.displayName ?? '研究者'}</strong>
                      <small>{account.sessionState.session.user.email}</small>
                    </span>
                  </NavLink>
                  <button
                    type="button"
                    aria-label={logoutFailed ? '退出失败，请重试' : '退出'}
                    title={logoutFailed ? '退出失败，请重试' : '退出'}
                    onClick={logout}
                  >
                    <SignOutIcon size={18} weight="regular" aria-hidden="true" />
                    <span>{logoutFailed ? '退出失败' : '退出'}</span>
                  </button>
                </>
              ) : account.sessionState.status === 'loading' ? (
                <span className="desktop-rail__session" role="status" aria-label="正在确认账户" />
              ) : (
                <NavLink to="/login" aria-label="登录" title="登录">
                  <UserCircleIcon size={18} weight="regular" />
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
        wide ? 'page-shell--wide' : '',
      ].filter(Boolean).join(' ')} id="main-content">{children}</main>

      {immersive ? null : <PrimaryNavigation className="mobile-navigation" label="移动主导航" compact />}
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
