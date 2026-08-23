export type RouteMotionDirection = 'forward' | 'backward' | 'lateral'

type RouteDescription = {
  depth: number
  order: number
  section: string
}

function describeRoute(pathname: string): RouteDescription {
  if (pathname === '/' || pathname === '/welcome') {
    return { section: 'marketing', order: -1, depth: 0 }
  }
  if (/^\/(login|register|password-reset)/.test(pathname)) {
    return { section: 'account-access', order: -1, depth: 0 }
  }
  if (pathname === '/app') return { section: 'workspace', order: 0, depth: 0 }
  if (pathname.startsWith('/agent')) return { section: 'agent', order: 1, depth: 0 }

  if (pathname === '/research/new') {
    return { section: 'research', order: 2, depth: 0 }
  }

  const researchRoute = pathname.match(/^\/research\/([^/]+)(?:\/(phenomenon|match|framework))?$/)
  if (researchRoute) {
    const stageDepth = { phenomenon: 1, match: 2, framework: 3 } as const
    const stage = researchRoute[2] as keyof typeof stageDepth | undefined
    return {
      section: `research:${researchRoute[1]}`,
      order: 2,
      depth: stage ? stageDepth[stage] : 0,
    }
  }

  if (pathname === '/knowledge') return { section: 'knowledge', order: 3, depth: 0 }
  if (pathname.startsWith('/knowledge/graph')) {
    return { section: 'knowledge-graph', order: 4, depth: 0 }
  }
  if (pathname.startsWith('/knowledge/')) {
    return { section: 'knowledge', order: 3, depth: 1 }
  }
  if (pathname === '/settings' || pathname === '/my') {
    return { section: 'account', order: 5, depth: 0 }
  }
  if (pathname.startsWith('/admin')) return { section: 'admin', order: 6, depth: 0 }

  return { section: pathname, order: 7, depth: 0 }
}

export function getRouteMotionDirection(
  currentPath: string,
  nextPath: string,
): RouteMotionDirection {
  const current = describeRoute(currentPath)
  const next = describeRoute(nextPath)

  if (current.section === next.section && current.depth !== next.depth) {
    return next.depth > current.depth ? 'forward' : 'backward'
  }
  if (current.section === next.section || current.order === next.order) return 'lateral'
  return next.order > current.order ? 'forward' : 'backward'
}

export function isContinuousResearchTransition(currentPath: string, nextPath: string) {
  return currentPath.startsWith('/research/') && nextPath.startsWith('/research/')
}
