import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import type { PropsWithChildren } from 'react'

export type AppLocale = 'zh-CN' | 'en-US'

type AppLocaleContextValue = {
  locale: AppLocale
  setLocale(locale: AppLocale): void
  text(zh: string, en: string): string
}

const localeStorageKey = 'qunxue.interface-locale'
const defaultLocaleContext: AppLocaleContextValue = {
  locale: 'zh-CN',
  setLocale: () => undefined,
  text: (zh) => zh,
}

const AppLocaleContext = createContext(defaultLocaleContext)

function storedLocale(): AppLocale {
  if (typeof window === 'undefined') return 'zh-CN'
  return window.localStorage.getItem(localeStorageKey) === 'en-US' ? 'en-US' : 'zh-CN'
}

export function AppLocaleProvider({ children }: PropsWithChildren) {
  const [locale, setLocale] = useState<AppLocale>(storedLocale)

  useEffect(() => {
    const previousLanguage = document.documentElement.lang
    document.documentElement.lang = locale === 'en-US' ? 'en' : 'zh-CN'
    window.localStorage.setItem(localeStorageKey, locale)
    return () => {
      document.documentElement.lang = previousLanguage
    }
  }, [locale])

  const value = useMemo<AppLocaleContextValue>(() => ({
    locale,
    setLocale,
    text: (zh, en) => (locale === 'en-US' ? en : zh),
  }), [locale])

  return <AppLocaleContext.Provider value={value}>{children}</AppLocaleContext.Provider>
}

export function useAppLocale() {
  return useContext(AppLocaleContext)
}
