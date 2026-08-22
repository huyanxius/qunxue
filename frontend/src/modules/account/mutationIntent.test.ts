import { describe, expect, it } from 'vitest'

import { MutationIntentLedger } from './mutationIntent'

describe('MutationIntentLedger', () => {
  it('reuses a key for a network retry and replaces it after success or changed input', () => {
    const ledger = new MutationIntentLedger()
    const first = ledger.keyFor('profile', { displayName: '林同学' })

    expect(ledger.keyFor('profile', { displayName: '林同学' })).toBe(first)
    expect(ledger.keyFor('profile', { displayName: '另一名字' })).not.toBe(first)

    const changed = ledger.keyFor('profile', { displayName: '另一名字' })
    ledger.complete('profile')
    expect(ledger.keyFor('profile', { displayName: '另一名字' })).not.toBe(changed)
  })
})
