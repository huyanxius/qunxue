import { useEffect, useLayoutEffect, useState, type ReactNode } from 'react'
import { useLocation } from 'react-router'

import {
  getRouteMotionDirection,
  isContinuousResearchTransition,
  type RouteMotionDirection,
} from './route-motion-model'

const routeMotionDurationMs = 222

type RouteMotionState = {
  active: boolean
  direction: RouteMotionDirection
  pathname: string
}

/** 页面只在真实 pathname 变化后进入；search 与 hash 变化不重复播放。 */
export function RouteMotionSurface({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  const [motion, setMotion] = useState<RouteMotionState>({
    active: false,
    direction: 'lateral',
    pathname,
  })

  useLayoutEffect(() => {
    setMotion((current) => current.pathname === pathname
      ? current
      : {
          active: !isContinuousResearchTransition(current.pathname, pathname),
          direction: getRouteMotionDirection(current.pathname, pathname),
          pathname,
        })
  }, [pathname])

  useEffect(() => {
    if (!motion.active) return undefined
    const timer = window.setTimeout(() => {
      setMotion((current) => current.pathname === motion.pathname
        ? { ...current, active: false }
        : current)
    }, routeMotionDurationMs)
    return () => window.clearTimeout(timer)
  }, [motion.active, motion.pathname])

  const active = motion.active && motion.pathname === pathname
  const direction = motion.pathname === pathname ? motion.direction : 'lateral'

  return (
    <div
      className="route-motion-surface"
      data-testid="route-motion-surface"
      data-motion-active={active ? 'true' : 'false'}
      data-motion-direction={direction}
    >
      {children}
    </div>
  )
}
