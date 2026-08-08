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
  entryPath: string
  phenomenonSummary: string
  adoptedTheoryCount: number
  createdAt: string
  updatedAt: string
}
