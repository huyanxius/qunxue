import { describe, expect, it } from 'vitest'

import { knowledgeListContextKey, readKnowledgeListScroll, saveKnowledgeListScroll } from './listContext'

describe('knowledge list context', () => {
  it('keeps scroll positions separate for each release and filter state', () => {
    const storage = new Map<string, string>()
    const adapter = {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => { storage.set(key, value) },
    }
    const state = { releaseId: 'release-a', query: '概念', loadedPages: 3 }

    saveKnowledgeListScroll(state, 864, adapter)

    expect(readKnowledgeListScroll(state, adapter)).toBe(864)
    expect(readKnowledgeListScroll({ ...state, query: '理论' }, adapter)).toBeUndefined()
    expect(knowledgeListContextKey(state)).toContain('loaded_pages=3')
  })

  it('ignores invalid stored positions', () => {
    const adapter = { getItem: () => '-12', setItem: () => undefined }

    expect(readKnowledgeListScroll({ releaseId: 'release-a' }, adapter)).toBeUndefined()
  })
})
