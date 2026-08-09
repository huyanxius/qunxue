export interface KnowledgeUrlState {
  releaseId?: string
  query?: string
  dimensionId?: string
  categoryId?: string
  loadedPages?: number
  returnTo?: string
}

function value(params: URLSearchParams, name: string) {
  return params.get(name)?.trim() || undefined
}

function loadedPages(params: URLSearchParams) {
  const parsed = Number(params.get('loaded_pages'))
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 50) return undefined
  return parsed > 1 ? parsed : undefined
}

function researchReturnTo(input: string | undefined) {
  if (!input?.startsWith('/research/')) return undefined
  const target = new URL(input, 'https://qunxue.local')
  if (target.origin !== 'https://qunxue.local') return undefined
  if (!target.pathname.startsWith('/research/')) return undefined
  return `${target.pathname}${target.search}${target.hash}`
}

const graphReturnQueryKeys = new Set([
  'knowledge_release_id',
  'query',
  'center',
  'pending',
])

export function readKnowledgeGraphReturnTo(params: URLSearchParams) {
  const input = value(params, 'return_to')
  if (!input?.startsWith('/') || input.startsWith('//')) return undefined

  try {
    const target = new URL(input, 'https://qunxue.local')
    if (target.origin !== 'https://qunxue.local') return undefined
    if (target.pathname !== '/knowledge' && target.pathname !== '/knowledge/graph') {
      return undefined
    }
    const safeQuery = new URLSearchParams()
    target.searchParams.forEach((queryValue, key) => {
      if (graphReturnQueryKeys.has(key)) safeQuery.append(key, queryValue)
    })
    const query = safeQuery.toString()
    return `${target.pathname}${query ? `?${query}` : ''}`
  } catch {
    return undefined
  }
}

export function readKnowledgeUrlState(
  params: URLSearchParams,
): KnowledgeUrlState {
  return {
    releaseId: value(params, 'knowledge_release_id'),
    query: value(params, 'query'),
    dimensionId: value(params, 'dimension_id'),
    categoryId: value(params, 'category_id'),
    loadedPages: loadedPages(params),
    returnTo: researchReturnTo(value(params, 'return_to')),
  }
}

export function writeKnowledgeUrlState(state: KnowledgeUrlState) {
  const params = new URLSearchParams()
  if (state.releaseId) params.set('knowledge_release_id', state.releaseId)
  if (state.query) params.set('query', state.query)
  if (state.dimensionId) params.set('dimension_id', state.dimensionId)
  if (state.categoryId) params.set('category_id', state.categoryId)
  if (state.loadedPages && state.loadedPages > 1) params.set('loaded_pages', String(state.loadedPages))
  if (state.returnTo) params.set('return_to', state.returnTo)
  return params
}
