import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { PropsWithChildren } from 'react'

import { privateQueryPrefix, PrivateQuerySessionContext } from '../../query/privateQueryKey'
import {
  getCurrentSessionViaApi,
  loginViaApi,
  logoutViaApi,
  registerViaApi,
  sendRegistrationCodeViaApi,
  watchSessionRejection,
} from './accountApi'
import type { AccountSession, AccountSessionState } from './types'

type AccountContextValue = {
  sessionState: AccountSessionState
  login(email: string, password: string): Promise<AccountSession>
  register(email: string, password: string, verificationCode: string): Promise<AccountSession>
  sendRegistrationCode(email: string): Promise<{ resendAfterSeconds: number }>
  logout(onSucceeded?: () => void): Promise<void>
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
  sendRegistrationCode: async () => {
    throw new Error('AccountProvider is missing.')
  },
  logout: async (_onSucceeded) => undefined,
  retrySession: () => undefined,
}

const AccountContext = createContext<AccountContextValue>(anonymousAccount)
const sessionQueryKey = ['account', 'session'] as const

function clearPrivateQueries(queryClient: QueryClient) {
  const filters = { queryKey: privateQueryPrefix }
  void queryClient.cancelQueries(filters)
  queryClient.removeQueries(filters)
}

export function AccountProvider({ children }: PropsWithChildren) {
  const queryClient = useQueryClient()
  const [expired, setExpired] = useState(false)
  const sessionQuery = useQuery({
    queryKey: sessionQueryKey,
    queryFn: async ({ signal }) => {
      const session = await getCurrentSessionViaApi(signal)
      signal.throwIfAborted()
      const previous = queryClient.getQueryData<AccountSession | null>(sessionQueryKey)
      if (previous && previous.sessionId !== session?.sessionId) clearPrivateQueries(queryClient)
      return session
    },
    retry: false,
  })
  const loginMutation = useMutation({ mutationFn: ({ email, password }: { email: string; password: string }) => loginViaApi(email, password) })
  const registerMutation = useMutation({ mutationFn: ({ email, password, verificationCode }: { email: string; password: string; verificationCode: string }) => registerViaApi(email, password, verificationCode) })
  const registrationCodeMutation = useMutation({ mutationFn: sendRegistrationCodeViaApi })
  const logoutMutation = useMutation({ mutationFn: logoutViaApi })

  const replaceSession = useCallback((session: AccountSession | null, expired: boolean) => {
    void queryClient.cancelQueries({ queryKey: sessionQueryKey })
    clearPrivateQueries(queryClient)
    setExpired(expired)
    queryClient.setQueryData(sessionQueryKey, session)
  }, [queryClient])

  useEffect(() => watchSessionRejection(() => {
    const established = queryClient.getQueryData<AccountSession | null>(sessionQueryKey)
    if (established) replaceSession(null, true)
  }), [queryClient, replaceSession])

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
      replaceSession(session, false)
      return session
    },
    async register(email, password, verificationCode) {
      const session = await registerMutation.mutateAsync({ email, password, verificationCode })
      replaceSession(session, false)
      return session
    },
    sendRegistrationCode: (email) => registrationCodeMutation.mutateAsync(email),
    async logout(onSucceeded) {
      await logoutMutation.mutateAsync()
      replaceSession(null, false)
      onSucceeded?.()
    },
    retrySession: () => void sessionQuery.refetch(),
  }), [
    loginMutation,
    logoutMutation,
    registerMutation,
    registrationCodeMutation,
    replaceSession,
    sessionQuery,
    sessionState,
  ])

  return (
    <AccountContext.Provider value={value}>
      <PrivateQuerySessionContext.Provider value={sessionState.status === 'authenticated' ? sessionState.session : null}>
        {children}
      </PrivateQuerySessionContext.Provider>
    </AccountContext.Provider>
  )
}

export function useAccount() {
  return useContext(AccountContext)
}
