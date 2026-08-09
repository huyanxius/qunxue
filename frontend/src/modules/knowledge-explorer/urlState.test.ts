import { describe, expect, it } from 'vitest'

import {
  readKnowledgeGraphReturnTo,
  readKnowledgeUrlState,
  writeKnowledgeUrlState,
} from './urlState'

describe('knowledge URL state', () => {
  it('restores a fixed release with query and directory filters', () => {
    const state = readKnowledgeUrlState(new URLSearchParams(
      'knowledge_release_id=release-a&query=%E6%A6%82%E5%BF%B5&dimension_id=D1&category_id=C001&loaded_pages=3&return_to=%2Fresearch%2Ftask-1%2Fmatch',
    ))

    expect(state).toEqual({
      categoryId: 'C001',
      dimensionId: 'D1',
      loadedPages: 3,
      query: '概念',
      releaseId: 'release-a',
      returnTo: '/research/task-1/match',
    })
    expect(writeKnowledgeUrlState(state).toString()).toBe(
      'knowledge_release_id=release-a&query=%E6%A6%82%E5%BF%B5&dimension_id=D1&category_id=C001&loaded_pages=3&return_to=%2Fresearch%2Ftask-1%2Fmatch',
    )
  })

  it.each(['0', '-1', 'not-a-number'])('drops invalid loaded page count %s', (loadedPages) => {
    const state = readKnowledgeUrlState(new URLSearchParams({ loaded_pages: loadedPages }))

    expect(state.loadedPages).toBeUndefined()
  })

  it('does not retain an external return target', () => {
    const state = readKnowledgeUrlState(new URLSearchParams(
      'knowledge_release_id=release-a&return_to=https%3A%2F%2Fexample.test',
    ))

    expect(state.returnTo).toBeUndefined()
  })

  it('restores only safe graph context keys from a knowledge return target', () => {
    const params = new URLSearchParams({
      return_to: '/knowledge/graph?knowledge_release_id=release-a&query=社会&center=D1:C001&pending=1&redirect=https://evil.test',
    })

    expect(readKnowledgeGraphReturnTo(params)).toBe(
      '/knowledge/graph?knowledge_release_id=release-a&query=%E7%A4%BE%E4%BC%9A&center=D1%3AC001&pending=1',
    )
  })

  it.each([
    'https://evil.test/takeover',
    '//evil.test/takeover',
    '/research/task-1/match',
    '/knowledge/D1:C001',
  ])('rejects an unsafe graph return target %s', (returnTo) => {
    expect(readKnowledgeGraphReturnTo(new URLSearchParams({ return_to: returnTo }))).toBeUndefined()
  })
})
