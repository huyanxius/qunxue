import { describe, expect, it } from 'vitest'

import { readKnowledgeUrlState, writeKnowledgeUrlState } from './urlState'

describe('knowledge URL state', () => {
  it('restores a fixed release with query and directory filters', () => {
    const state = readKnowledgeUrlState(new URLSearchParams(
      'knowledge_release_id=release-a&query=%E6%A6%82%E5%BF%B5&dimension_id=D1&category_id=C001&return_to=%2Fresearch%2Ftask-1%2Fmatch',
    ))

    expect(state).toEqual({
      categoryId: 'C001',
      dimensionId: 'D1',
      query: '概念',
      releaseId: 'release-a',
      returnTo: '/research/task-1/match',
    })
    expect(writeKnowledgeUrlState(state).toString()).toBe(
      'knowledge_release_id=release-a&query=%E6%A6%82%E5%BF%B5&dimension_id=D1&category_id=C001&return_to=%2Fresearch%2Ftask-1%2Fmatch',
    )
  })

  it('does not retain an external return target', () => {
    const state = readKnowledgeUrlState(new URLSearchParams(
      'knowledge_release_id=release-a&return_to=https%3A%2F%2Fexample.test',
    ))

    expect(state.returnTo).toBeUndefined()
  })
})
