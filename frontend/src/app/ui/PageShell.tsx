import type { PropsWithChildren, ReactNode } from 'react'
import { Link, NavLink } from 'react-router'

type PageTitleProps = {
  eyebrow: string
  title: string
  lede?: string
}

export function PageShell({ children }: PropsWithChildren) {
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
          <NavLink to="/my">我的</NavLink>
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
