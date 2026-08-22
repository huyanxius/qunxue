export type AccountUser = {
  userId: string
  email: string
  displayName: string | null
}

export type AccountSession = {
  sessionId: string
  user: AccountUser
  expiresAt: string
}

export type AccountSessionState =
  | { status: 'loading' }
  | { status: 'authenticated'; session: AccountSession }
  | { status: 'anonymous' }
  | { status: 'expired' }
  | { status: 'error' }

export type MyResearchItem = {
  taskId: string
  stageLabel: string
  nextActionLabel: string
  entryPath: string
  blocker: {
    action: string | null
    code: string
    message: string
    recoverable: boolean
  } | null
  retry: {
    action: string
    method: 'GET' | 'POST' | 'PATCH'
    href: string
    label: string
  } | null
  phenomenonSummary: string
  adoptedTheoryCount: number
  createdAt: string
  updatedAt: string
}
