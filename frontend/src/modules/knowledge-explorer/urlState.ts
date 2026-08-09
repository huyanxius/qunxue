export interface KnowledgeUrlState {
  releaseId?: string
  query?: string
  dimensionId?: string
  categoryId?: string
  returnTo?: string
}

function value(params: URLSearchParams, name: string) {
  return params.get(name)?.trim() || undefined
}

function researchReturnTo(input: string | undefined) {
  if (!input?.startsWith('/research/')) return undefined
  const target = new URL(input, 'https://qunxue.local')
  if (target.origin !== 'https://qunxue.local') return undefined
  if (!target.pathname.startsWith('/research/')) return undefined
  return `${target.pathname}${target.search}${target.hash}`
}

export function readKnowledgeUrlState(
  params: URLSearchParams,
): KnowledgeUrlState {
  return {
    releaseId: value(params, 'knowledge_release_id'),
    query: value(params, 'query'),
    dimensionId: value(params, 'dimension_id'),
    categoryId: value(params, 'category_id'),
    returnTo: researchReturnTo(value(params, 'return_to')),
  }
}

export function writeKnowledgeUrlState(state: KnowledgeUrlState) {
  const params = new URLSearchParams()
  if (state.releaseId) params.set('knowledge_release_id', state.releaseId)
  if (state.query) params.set('query', state.query)
  if (state.dimensionId) params.set('dimension_id', state.dimensionId)
  if (state.categoryId) params.set('category_id', state.categoryId)
  if (state.returnTo) params.set('return_to', state.returnTo)
  return params
}
