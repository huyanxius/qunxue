export type MutationAttempt<T> = Readonly<{
  expectedVersion: number
  idempotencyKey: string
  localValue: T
}>

export type MutationFailure =
  | Readonly<{ kind: 'network' | 'server' }>
  | Readonly<{ kind: 'conflict'; remoteVersion: number }>

export type ReconciledMutation<T> =
  | Readonly<{ state: 'retryable'; attempt: MutationAttempt<T>; localValue: T }>
  | Readonly<{
      state: 'conflict'
      attempt: MutationAttempt<T>
      expectedVersion: number
      remoteVersion: number
      localValue: T
    }>

export function createMutationAttempt<T>(input: {
  expectedVersion: number
  idempotencyKey: string
  localValue: T
}): MutationAttempt<T> {
  return Object.freeze({ ...input })
}

export function reconcileMutationFailure<T>(
  attempt: MutationAttempt<T>,
  failure: MutationFailure,
): ReconciledMutation<T> {
  if (failure.kind === 'conflict') {
    return {
      state: 'conflict',
      attempt,
      expectedVersion: attempt.expectedVersion,
      remoteVersion: failure.remoteVersion,
      localValue: attempt.localValue,
    }
  }
  return { state: 'retryable', attempt, localValue: attempt.localValue }
}

export function retryMutationAttempt<T>(
  failure: ReconciledMutation<T>,
): MutationAttempt<T> {
  return failure.attempt
}
