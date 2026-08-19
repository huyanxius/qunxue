import { useSyncExternalStore } from 'react'

function subscribe(listener: () => void) {
  window.addEventListener('online', listener)
  window.addEventListener('offline', listener)
  return () => {
    window.removeEventListener('online', listener)
    window.removeEventListener('offline', listener)
  }
}

function onlineSnapshot() {
  return navigator.onLine
}

export function NetworkStatusNotice() {
  const online = useSyncExternalStore(subscribe, onlineSnapshot, () => true)
  if (online) return null

  return (
    <aside className="network-status-notice" role="status" aria-live="polite">
      浏览器当前处于离线状态。已加载内容可以继续查看；提交或重试前请先恢复网络。
    </aside>
  )
}
