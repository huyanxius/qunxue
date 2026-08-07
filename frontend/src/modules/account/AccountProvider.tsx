import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import type { PropsWithChildren } from 'react'

import {
  getCurrentSessionViaApi,
  loginViaApi,
  logoutViaApi,
  registerViaApi,
  watchSessionRejection,
} from './accountApi'
import type { AccountSession, AccountSessionState } from './types'

type AccountContextValue = {
  sessionState: AccountSessionState
  login(email: string, password: string): Promise<AccountSession>
  register(email: string, password: string): Promise<AccountSession>
  logout(): Promise<void>
  retrySession(): void
}

const anonymousAccount: AccountContextValue = {
  sessionState: { status: 'anonymous' },
  login: async () => {
    throw new Error('AccountProvider is missing.')
  },
  register: async () => {
    throw new Error('AccountProvider is missing.')
  },
  logout: async () => undefined,
  retrySession: () => undefined,
}

const AccountContext = createContext<AccountContextValue>(anonymousAccount)
const sessionQueryKey = ['account', 'session'] as const

export function AccountProvider({ children }: PropsWithChildren) {
  const queryClient = useQueryClient()
  const [expired, setExpired] = useState(false)
  const sessionQuery = useQuery({
    queryKey: sessionQueryKey,
    queryFn: getCurrentSessionViaApi,
    retry: false,
  })
  const loginMutation = useMutation({ mutationFn: ({ email, password }: { email: string; password: string }) => loginViaApi(email, password) })
  const registerMutation = useMutation({ mutationFn: ({ email, password }: { email: string; password: string }) => registerViaApi(email, password) })
  const logoutMutation = useMutation({ mutationFn: logoutViaApi })

  useEffect(() => watchSessionRejection(() => {
    const established = queryClient.getQueryData<AccountSession | null>(sessionQueryKey)
    if (established) {
      setExpired(true)
      queryClient.setQueryData(sessionQueryKey, null)
    }
  }), [queryClient])

  const sessionState: AccountSessionState = expired
    ? { status: 'expired' }
    : sessionQuery.isPending
    ? { status: 'loading' }
    : sessionQuery.isError
      ? { status: 'error' }
      : sessionQuery.data
        ? { status: 'authenticated', session: sessionQuery.data }
        : { status: 'anonymous' }

  const value = useMemo<AccountContextValue>(() => ({
    sessionState,
    async login(email, password) {
      const session = await loginMutation.mutateAsync({ email, password })
      setExpired(false)
      queryClient.setQueryData(sessionQueryKey, session)
      return session
    },
    async register(email, password) {
      const session = await registerMutation.mutateAsync({ email, password })
      setExpired(false)
      queryClient.setQueryData(sessionQueryKey, session)
      return session
    },
    async logout() {
      await logoutMutation.mutateAsync()
      setExpired(false)
      queryClient.setQueryData(sessionQueryKey, null)
    },
    retrySession: () => void sessionQuery.refetch(),
  }), [
    loginMutation,
    logoutMutation,
    queryClient,
    registerMutation,
    setExpired,
    sessionQuery,
    sessionState,
  ])

  return <AccountContext.Provider value={value}>{children}</AccountContext.Provider>
}

export function useAccount() {
  return useContext(AccountContext)
}
