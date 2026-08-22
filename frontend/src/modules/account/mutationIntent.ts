type IntentEntry = {
  fingerprint: string
  key: string
}

function createKey() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `account-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export class MutationIntentLedger {
  private readonly entries = new Map<string, IntentEntry>()

  keyFor(action: string, payload: unknown) {
    const fingerprint = JSON.stringify(payload)
    const existing = this.entries.get(action)
    if (existing?.fingerprint === fingerprint) return existing.key

    const key = createKey()
    this.entries.set(action, { fingerprint, key })
    return key
  }

  complete(action: string) {
    this.entries.delete(action)
  }
}
