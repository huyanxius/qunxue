import { useLayoutEffect } from 'react'

/** Keep the mobile shell inside the visible area when the software keyboard opens. */
export function useMobileViewport(active: boolean) {
  useLayoutEffect(() => {
    if (!active) return
    const root = document.documentElement.style
    const properties = ['--qunxue-mobile-height', '--qunxue-mobile-offset-top'] as const
    const previous = properties.map(name => [name, root.getPropertyValue(name), root.getPropertyPriority(name)] as const)
    const viewport = window.visualViewport
    let pending = 0
    const update = () => {
      pending = 0
      if (viewport && Math.abs(viewport.scale - 1) > .01) return
      const height = viewport?.height ?? window.innerHeight
      if (height <= 0) return
      root.setProperty('--qunxue-mobile-height', `${Math.round(height)}px`)
      root.setProperty('--qunxue-mobile-offset-top', `${Math.max(0, Math.round(viewport?.offsetTop ?? 0))}px`)
    }
    const schedule = () => { if (!pending) pending = window.requestAnimationFrame(update) }
    update()
    window.addEventListener('resize', schedule)
    viewport?.addEventListener('resize', schedule)
    viewport?.addEventListener('scroll', schedule)
    return () => {
      window.cancelAnimationFrame(pending)
      window.removeEventListener('resize', schedule)
      viewport?.removeEventListener('resize', schedule)
      viewport?.removeEventListener('scroll', schedule)
      for (const [name, value, priority] of previous) {
        if (value) root.setProperty(name, value, priority)
        else root.removeProperty(name)
      }
    }
  }, [active])
}
