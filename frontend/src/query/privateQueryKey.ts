import type { QueryKey } from '@tanstack/react-query'
import { createContext, useContext } from 'react'

export const privateQueryPrefix = ['private'] as const
export const PrivateQuerySessionContext = createContext<{
  sessionId: string
  user: { userId: string }
} | null>(null)

export function usePrivateQueryKey(...key: QueryKey) {
  const session = useContext(PrivateQuerySessionContext)
  // A new sign-in gets a new session ID even for the same user.
  return [...privateQueryPrefix, session?.user.userId ?? null, session?.sessionId ?? null, ...key] as const
}
