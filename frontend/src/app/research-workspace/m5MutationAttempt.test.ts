import { describe, expect, it } from 'vitest'

import {
  createMutationAttempt,
  reconcileMutationFailure,
  retryMutationAttempt,
} from './m5MutationAttempt'

describe('M5 document mutation attempts', () => {
  it('reuses the original idempotency key and local content for a network retry', () => {
    const attempt = createMutationAttempt({
      expectedVersion: 7,
      localValue: '尚未同步的研究方法正文',
      idempotencyKey: 'save-attempt-1',
    })

    const failure = reconcileMutationFailure(attempt, { kind: 'network' })
    const retry = retryMutationAttempt(failure)

    expect(failure.state).toBe('retryable')
    expect(retry).toBe(attempt)
    expect(retry.idempotencyKey).toBe('save-attempt-1')
    expect(retry.localValue).toBe('尚未同步的研究方法正文')
  })

  it('keeps local content available when CAS detects a newer remote version', () => {
    const attempt = createMutationAttempt({
      expectedVersion: 7,
      localValue: '用户正在编辑的本地版本',
      idempotencyKey: 'save-attempt-2',
    })

    const conflict = reconcileMutationFailure(attempt, {
      kind: 'conflict',
      remoteVersion: 8,
    })

    expect(conflict).toMatchObject({
      state: 'conflict',
      expectedVersion: 7,
      remoteVersion: 8,
      localValue: '用户正在编辑的本地版本',
    })
  })
})
