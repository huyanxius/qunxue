import { beforeEach, expect, it, vi } from 'vitest'

const generated = vi.hoisted(() => ({
  getRoadshowSettings: vi.fn(),
  saveRoadshowSettings: vi.fn(),
  resetRoadshowSettings: vi.fn(),
}))
vi.mock('./generated', () => generated)
vi.mock('./client', () => ({ apiClient: { adapter: 'test' } }))

import { resetRoadshowSettings, saveRoadshowSettings } from './roadshow'

beforeEach(() => vi.clearAllMocks())

it('supplies distinct idempotency keys for save and reset through the generated client', () => {
  const body = { cases: [{ title: 'test', keywords: ['test'], question: 'question', options: ['one'], steps: ['read'], answer: 'answer' }] }
  saveRoadshowSettings(body)
  resetRoadshowSettings()
  const save = generated.saveRoadshowSettings.mock.calls[0][0]
  const reset = generated.resetRoadshowSettings.mock.calls[0][0]
  expect(save.body).toBe(body)
  expect(save.headers['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/)
  expect(reset.headers['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/)
  expect(save.headers['Idempotency-Key']).not.toBe(reset.headers['Idempotency-Key'])
  expect(save.throwOnError).toBe(true)
  expect(reset.throwOnError).toBe(true)
})
