export type AccountRole = 'member' | 'admin'
export type AccountStatus = 'active' | 'disabled' | 'deactivated'

export type AccountPreferences = {
  locale: string
  timezone: string
  researchUpdatesEnabled: boolean
  modelImprovementAllowed: boolean
  consentPolicyVersion: string
  consentUpdatedAt: string | null
  version: number
}

export type AccountProfile = {
  userId: string
  email: string
  displayName: string | null
  role: AccountRole
  status: AccountStatus
  version: number
  createdAt: string
  isProtectedAdmin: boolean
  preferences: AccountPreferences
}

export type AccountSession = {
  sessionId: string
  current: boolean
  createdAt: string
  lastSeenAt: string
  expiresAt: string
  deviceLabel: string
  ipAddress: string | null
}

export type CreditLedgerEntry = {
  entryId: string
  kind: 'signup_grant' | 'usage' | 'redemption'
  points: number
  balanceAfter: number
  inputTokens: number
  outputTokens: number
  createdAt: string
}

export type CreditSummary = {
  balance: number
  creditLimit: number
  grantAmount: number
  isUnlimited: boolean
  inputTokensPerCredit: number
  outputTokensPerCredit: number
  entries: CreditLedgerEntry[]
  totalEntries: number
  nextCursor: string | null
}

export type AccountSystemHealth = {
  capability: 'unavailable' | 'mock' | 'base' | 'sft'
  contractVersion: string
  knowledgeReleaseId: string | null
  modelVersion: string
  persistence: 'sqlite'
  provider: string
  runtimeMode: 'mock' | 'base' | 'sft'
  service: string
  status: 'ok'
}

export type CreditRedemption = {
  redeemedPoints: number
  balance: number
}

export type CreditRedemptionCodeBatch = {
  codes: string[]
  points: number
  expiresAt: string
}

export type PersonalDataExport = {
  exportId: string
  status: 'pending' | 'ready' | 'failed' | 'expired'
  createdAt: string
  expiresAt: string | null
  downloadHref: string | null
}

export type AdminUser = {
  userId: string
  email: string
  displayName: string | null
  role: AccountRole
  status: AccountStatus
  version: number
  createdAt: string
  lastActiveAt: string | null
  isCurrentUser: boolean
  isProtectedAdmin: boolean
}

export type AdminUserPage = {
  items: AdminUser[]
  total: number
  nextCursor: string | null
}

export type AdminRuntimeSettings = {
  model: string
  reasoningEffort: string
  providerBaseUrl: string
  restartRequired: boolean
}

export type PasswordResetLink = {
  resetId: string
  resetUrl: string
  expiresAt: string
}

export type AccountAuditEvent = {
  eventId: string
  action: string
  outcome?: 'succeeded' | 'denied' | 'failed'
  actorEmail: string | null
  targetEmail: string | null
  reason: string | null
  occurredAt: string
}

export type AccountAuditPage = {
  items: AccountAuditEvent[]
  nextCursor: string | null
}

export type MutationIntent = {
  idempotencyKey: string
}

export type AccountManagementApi = {
  getAccount(): Promise<AccountProfile>
  getCreditSummary(input?: { cursor?: string; limit?: number }): Promise<CreditSummary>
  redeemCredits(input: MutationIntent & { code: string }): Promise<CreditRedemption>
  createCreditRedemptionCodes(input: MutationIntent & {
    count: number
    expiresInDays: number
  }): Promise<CreditRedemptionCodeBatch>
  updateProfile(input: MutationIntent & {
    displayName: string
    expectedVersion: number
  }): Promise<AccountProfile>
  updatePreferences(input: MutationIntent & {
    locale: string
    timezone: string
    researchUpdatesEnabled: boolean
    expectedVersion: number
  }): Promise<AccountPreferences>
  updateModelDataAuthorization(input: MutationIntent & {
    allowed: boolean
    policyVersion: string
    expectedVersion: number
  }): Promise<AccountPreferences>
  changePassword(input: MutationIntent & {
    currentPassword: string
    newPassword: string
    revokeOtherSessions: boolean
  }): Promise<{ revokedSessionCount: number }>
  listSessions(): Promise<AccountSession[]>
  revokeSession(sessionId: string, intent: MutationIntent): Promise<void>
  requestDataExport(intent: MutationIntent): Promise<PersonalDataExport>
  deactivateAccount(input: MutationIntent & {
    currentPassword: string
    reason: string
  }): Promise<{ recoverable: true }>
  deleteAccount(input: MutationIntent & {
    currentPassword: string
    confirmationEmail: string
  }): Promise<{ recoverable: false }>
  listAdminUsers(input: {
    query?: string
    status?: AccountStatus
    cursor?: string
  }): Promise<AdminUserPage>
  updateUserRole(userId: string, input: MutationIntent & {
    role: AccountRole
    expectedVersion: number
    reason: string
  }): Promise<AdminUser>
  disableUser(userId: string, input: MutationIntent & {
    expectedVersion: number
    reason: string
  }): Promise<AdminUser>
  enableUser(userId: string, input: MutationIntent & {
    expectedVersion: number
    reason: string
  }): Promise<AdminUser>
  createPasswordReset(userId: string, intent: MutationIntent): Promise<PasswordResetLink>
  listAuditEvents(input?: { cursor?: string; limit?: number }): Promise<AccountAuditPage>
  getRuntimeSettings?(): Promise<AdminRuntimeSettings>
  updateRuntimeSettings?(input: { model: string; reasoningEffort: string }): Promise<AdminRuntimeSettings>
  consumePasswordReset(input: MutationIntent & {
    token: string
    newPassword: string
  }): Promise<void>
}

export class AccountManagementRequestError extends Error {
  readonly status: number | undefined
  readonly code: string | undefined

  constructor(message: string, status?: number, code?: string) {
    super(message)
    this.name = 'AccountManagementRequestError'
    this.status = status
    this.code = code
  }
}

export function isAccountManagementRequestError(
  failure: unknown,
): failure is AccountManagementRequestError {
  return failure instanceof AccountManagementRequestError
}
