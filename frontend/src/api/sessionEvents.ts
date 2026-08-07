const listeners = new Set<() => void>()

export function notifySessionRejected() {
  for (const listener of listeners) listener()
}

export function subscribeToSessionRejected(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
