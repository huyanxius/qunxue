import { createContext, useContext, useState } from 'react'
import type { Dispatch, PropsWithChildren, ReactNode, Ref, SetStateAction } from 'react'
import { Link, NavLink, useNavigate } from 'react-router'
import {
  BellIcon,
  BooksIcon,
  ChatCircleDotsIcon,
  FileTextIcon,
  HouseIcon,
  PlusIcon,
  SidebarSimpleIcon,
  ToolboxIcon,
  TreeStructureIcon,
  UserCircleIcon,
} from '@phosphor-icons/react'

import brandMark from '../../assets/qunxue-brand-mark.svg'
import { useAccount } from '../../modules/account'
import { useAppLocale } from '../i18n/AppLocaleProvider'
import { AppFrameShader } from './AppFrameShader'
import { NetworkStatusNotice } from './NetworkStatusNotice'

type PageTitleProps = {
  eyebrow: string
  title: string
  lede?: string
}

type RailState = {
  collapsed: boolean
  setCollapsed: Dispatch<SetStateAction<boolean>>
}

const RailStateContext = createContext<RailState | null>(null)

/** 侧栏宽度属于顶层应用状态，不随中间内容的路由切换重置。 */
export function RailStateProvider({ children }: PropsWithChildren) {
  const [collapsed, setCollapsed] = useState(false)
  return (
    <RailStateContext.Provider value={{ collapsed, setCollapsed }}>
      {children}
    </RailStateContext.Provider>
  )
}

function ProductMark() {
  return (
    <span className="product-mark" aria-hidden="true">
      <img src={brandMark} alt="" />
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
  const { text } = useAppLocale()
  const navigationItems = [
    { href: '/app', label: text('工作台', 'Workbench'), mobileLabel: text('工作台', 'Home'), icon: HouseIcon, end: true },
    { href: '/agent', label: text('研究 Agent', 'Research Agent'), mobileLabel: 'Agent', icon: ChatCircleDotsIcon, end: true },
    { href: '/research/new', label: text('新建研究', 'New research'), mobileLabel: text('新建', 'New'), icon: PlusIcon },
    { href: '/research/tools', label: text('研究工具', 'Research tools'), mobileLabel: text('工具', 'Tools'), icon: ToolboxIcon, end: true },
    { href: '/research/materials', label: text('研究材料', 'Research materials'), mobileLabel: text('材料', 'Materials'), icon: FileTextIcon, end: true },
    { href: '/knowledge', label: text('知识库', 'Knowledge base'), mobileLabel: text('知识', 'Library'), icon: BooksIcon, end: true },
    { href: '/knowledge/graph', label: text('知识图谱', 'Knowledge graph'), mobileLabel: text('图谱', 'Graph'), icon: TreeStructureIcon },
  ]
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
  shader = false,
  defaultRailCollapsed = false,
  railContent,
  railContentRef,
}: PropsWithChildren<{
  workspace?: boolean
  immersive?: boolean
  wide?: boolean
  shader?: boolean
  defaultRailCollapsed?: boolean
  railContent?: ReactNode
  railContentRef?: Ref<HTMLDivElement>
}>) {
  const account = useAccount()
  const { text } = useAppLocale()
  const navigate = useNavigate()
  const [logoutFailed, setLogoutFailed] = useState(false)
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const sharedRailState = useContext(RailStateContext)
  const [localRailCollapsed, setLocalRailCollapsed] = useState(defaultRailCollapsed)
  const railCollapsed = sharedRailState?.collapsed ?? localRailCollapsed
  const setRailCollapsed = sharedRailState?.setCollapsed ?? setLocalRailCollapsed
  const accountName = account.sessionState.status === 'authenticated'
    ? account.sessionState.session.user.displayName ?? text('研究者', 'Researcher')
    : text('研究者', 'Researcher')
  const accountInitial = Array.from(accountName.trim())[0] ?? text('研', 'R')

  async function logout() {
    setLogoutFailed(false)
    try {
      await account.logout(() => {
        navigate('/', { replace: true, state: { loggedOut: true } })
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
        <div className="app-frame__backdrop" aria-hidden="true">
          {shader ? <AppFrameShader /> : null}
        </div>
      )}
      <NetworkStatusNotice />
      {immersive ? null : (
        <>
          <a className="skip-link" href="#main-content">{text('跳到主要内容', 'Skip to main content')}</a>
          <header className="masthead mobile-masthead">
            <Link className="wordmark" to="/app" aria-label={text('群学致知工作台', 'Qunxue Zhizhi workbench')}>
              <ProductMark />
              <strong>群学致知</strong>
            </Link>
            <nav className="account-navigation" aria-label={text('账户导航', 'Account navigation')}>
              {account.sessionState.status === 'authenticated' ? (
                <>
                  <NavLink to="/settings">{text('账户', 'Account')}</NavLink>
                  <button className="nav-action" type="button" onClick={logout}>
                    {logoutFailed ? text('退出失败，请重试', 'Sign out failed. Try again') : text('退出', 'Sign out')}
                  </button>
                </>
              ) : account.sessionState.status === 'loading' ? (
                <span className="session-email">{text('确认中', 'Checking…')}</span>
              ) : (
                <NavLink to="/login">{text('登录', 'Sign in')}</NavLink>
              )}
            </nav>
          </header>

          <aside className={`desktop-rail${railCollapsed ? ' desktop-rail--collapsed' : ''}`} aria-label={text('群学致知功能栏', 'Qunxue Zhizhi navigation')}>
            <div className="desktop-rail__topbar">
              <Link className="desktop-rail__brand" to="/app" aria-label={text('群学致知工作台', 'Qunxue Zhizhi workbench')}>
                <ProductMark />
                <strong>群学致知</strong>
              </Link>
              <button
                className="desktop-rail__collapse"
                type="button"
                aria-label={railCollapsed ? text('展开侧栏', 'Expand sidebar') : text('收起侧栏', 'Collapse sidebar')}
                title={railCollapsed ? text('展开侧栏', 'Expand sidebar') : text('收起侧栏', 'Collapse sidebar')}
                onClick={() => setRailCollapsed((collapsed) => !collapsed)}
              >
                <SidebarSimpleIcon size={18} weight="regular" />
              </button>
            </div>
            <div className="desktop-rail__body">
              <PrimaryNavigation className="desktop-navigation" label={text('桌面主导航', 'Main navigation')} />
              {railContent || railContentRef ? (
                <div ref={railContentRef} className="desktop-rail__secondary">{railContent}</div>
              ) : null}
            </div>
            <div className="desktop-rail__account">
              {account.sessionState.status === 'authenticated' ? (
                <>
                  <NavLink
                    className="desktop-rail__identity"
                    to="/settings"
                    aria-label={text(`账户 ${accountName}`, `Account ${accountName}`)}
                    title={accountName}
                  >
                    <span className="desktop-rail__avatar" aria-hidden="true">{accountInitial}</span>
                    <strong>{accountName}</strong>
                  </NavLink>
                  <button
                    className="desktop-rail__notifications"
                    type="button"
                    aria-label={text('通知', 'Notifications')}
                    aria-expanded={notificationsOpen}
                    aria-controls="desktop-notifications"
                    title={text('通知', 'Notifications')}
                    onClick={() => setNotificationsOpen((open) => !open)}
                  >
                    <BellIcon size={19} weight="regular" aria-hidden="true" />
                  </button>
                  {notificationsOpen ? (
                    <div className="desktop-rail__notification-panel" id="desktop-notifications" role="status">
                      <strong>{text('暂无通知', 'No notifications')}</strong>
                      <p>{text('服务器通知会显示在这里。', 'Server notifications will appear here.')}</p>
                    </div>
                  ) : null}
                </>
              ) : account.sessionState.status === 'loading' ? (
                <span className="desktop-rail__session" role="status" aria-label={text('正在确认账户', 'Checking account')} />
              ) : (
                <NavLink to="/login" aria-label={text('登录', 'Sign in')} title={text('登录', 'Sign in')}>
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

      {immersive ? null : <PrimaryNavigation className="mobile-navigation" label={text('移动主导航', 'Mobile navigation')} compact />}
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
