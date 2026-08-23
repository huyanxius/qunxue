import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { PropsWithChildren } from 'react'

import { AccountProvider } from '../modules/account'
import { AppLocaleProvider } from '../i18n/AppLocaleProvider'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
})

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <QueryClientProvider client={queryClient}>
      <AppLocaleProvider>
        <AccountProvider>{children}</AccountProvider>
      </AppLocaleProvider>
    </QueryClientProvider>
  )
}
