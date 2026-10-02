import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router'
import brandMark from '../../assets/qunxue-brand-mark.svg'
import './site-header.css'

import { featureLinks, docLinks } from './siteNavigation'
type Menu = 'features' | 'docs'

export function SiteHeader({ authenticated = false }: { authenticated?: boolean }) {
  const [menu, setMenu] = useState<Menu | null>(null)
  const rootRef = useRef<HTMLElement>(null)
  const triggerRefs = useRef<Partial<Record<Menu, HTMLButtonElement | null>>>({})
  const panelRef = useRef<HTMLDivElement>(null)
  const keyboardOpen = useRef(false)
  const location = useLocation()

  useLayoutEffect(() => { setMenu(null) }, [location.pathname, location.hash])
  useEffect(() => {
    if (!menu) return
    if (keyboardOpen.current) {
      panelRef.current?.querySelector<HTMLAnchorElement>('a')?.focus()
      keyboardOpen.current = false
    }
    const dismiss = (event: PointerEvent) => {
      if (event.target instanceof Node && !rootRef.current?.contains(event.target)) setMenu(null)
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      setMenu(null)
      triggerRefs.current[menu]?.focus()
    }
    document.addEventListener('pointerdown', dismiss)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('pointerdown', dismiss)
      document.removeEventListener('keydown', escape)
    }
  }, [menu])

  const links = menu === 'features' ? featureLinks : docLinks
  return (
    <header className={`public-header site-header${menu ? ' site-header--open' : ''}`} ref={rootRef}
      onBlur={(event) => {
        if (event.relatedTarget instanceof Node && !event.currentTarget.contains(event.relatedTarget)) setMenu(null)
      }}>
      <a className="site-skip" href="#site-main">跳至正文</a>
      <div className="site-header__inner">
        <Link className="site-brand" to="/welcome" aria-label="群学致知介绍页">
          <img src={brandMark} alt="" /><span><strong>群学致知</strong><small>COLLECTIVE INQUIRY</small></span>
        </Link>
        <nav className="site-nav" aria-label="官网导航">
          {(['features', 'docs'] as const).map((key) => (
            <button key={key} type="button" ref={(node) => { triggerRefs.current[key] = node }}
              aria-expanded={menu === key} aria-controls={`site-${key}`}
              onClick={() => setMenu(menu === key ? null : key)}
              onKeyDown={(event) => {
                if (event.key === 'ArrowDown') {
                  event.preventDefault()
                  keyboardOpen.current = true
                  if (menu === key) panelRef.current?.querySelector<HTMLAnchorElement>('a')?.focus()
                  else setMenu(key)
                }
              }}>
              {key === 'features' ? '功能' : 'Docs'}<svg viewBox="0 0 12 12" aria-hidden="true"><path d="m3 4.5 3 3 3-3" /></svg>
            </button>
          ))}
        </nav>
        <div className="site-account">
          <Link className="site-login" to={authenticated ? '/app' : '/login'}>{authenticated ? '工作台' : '登录'}</Link>
          <Link className="site-start" to={authenticated ? '/agent' : '/register'}>开始体验<span aria-hidden="true"> ↗</span></Link>
        </div>
      </div>
      {menu && <>
        <button className="site-scrim" tabIndex={-1} aria-label="关闭导航" onClick={() => setMenu(null)} />
        <div className="site-menu" id={`site-${menu}`} ref={panelRef}>
          <div className="site-menu__inner">
            <div className="site-menu__lead"><span>{menu === 'features' ? '用群学开展研究' : '群学使用手册'}</span>
              <Link to={menu === 'features' ? '/features' : '/docs'} onClick={() => setMenu(null)}>
                {menu === 'features' ? '探索功能' : '阅读 Docs'}<span aria-hidden="true"> ↗</span>
              </Link>
              <p>{menu === 'features' ? '了解每项功能能帮你完成什么，再进入实际工作区。' : '从第一次提问，到核对材料与引用。按操作查找答案。'}</p>
            </div>
            <nav className="site-menu__links" aria-label={menu === 'features' ? '功能列表' : '文档目录'}>
              {links.map((item) => <Link key={item.id} to={`/${menu}#${item.id}`} onClick={() => setMenu(null)}>
                <strong>{item.title}</strong><span>{item.detail}</span>
              </Link>)}
            </nav>
          </div>
        </div>
      </>}
    </header>
  )
}
