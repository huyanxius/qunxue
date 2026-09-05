import { useSyncExternalStore } from 'react'

const query = '(prefers-color-scheme: dark)'

function subscribe(notify: () => void) {
  const media = window.matchMedia?.(query)
  media?.addEventListener?.('change', notify)
  // A preview may explicitly select color-scheme; GPU colors must follow the same CSS choice.
  const observer = new MutationObserver(notify)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['style', 'class'] })
  return () => {
    media?.removeEventListener?.('change', notify)
    observer.disconnect()
  }
}

function snapshot() {
  const scheme = getComputedStyle(document.documentElement).colorScheme
  if (scheme === 'dark' || scheme === 'light') return scheme === 'dark'
  return window.matchMedia?.(query).matches ?? false
}

/** CSS handles surface colors; WebGL uniforms need the same resolved appearance as a boolean. */
export function useColorScheme() {
  return useSyncExternalStore(subscribe, snapshot, () => false)
}
