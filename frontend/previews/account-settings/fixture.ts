import type {
  AccountManagementApi,
  AccountProfile,
  AccountSession,
} from '../../src/modules/account/accountManagementModels'

// 仅替换已有账户接口的验收数据；生产组件仍默认使用 accountManagementApi。
let account: AccountProfile = {
  userId: 'user-1',
  email: 'researcher@example.com',
  displayName: '胡言',
  role: 'member',
  status: 'active',
  version: 3,
  createdAt: '2026-08-01T08:00:00Z',
  isProtectedAdmin: false,
  preferences: {
    locale: 'zh-CN',
    timezone: 'Asia/Shanghai',
    researchUpdatesEnabled: true,
    modelImprovementAllowed: false,
    consentPolicyVersion: '2026-08-secondary-use-v1',
    consentUpdatedAt: null,
    version: 2,
  },
}

let sessions: AccountSession[] = [
  {
    sessionId: 'session-current',
    current: true,
    createdAt: '2026-08-22T02:00:00Z',
    lastSeenAt: '2026-08-22T05:30:00Z',
    expiresAt: '2026-09-13T02:00:00Z',
    deviceLabel: 'Safari · macOS',
    ipAddress: '127.0.0.1',
  },
  {
    sessionId: 'session-other',
    current: false,
    createdAt: '2026-08-21T02:00:00Z',
    lastSeenAt: '2026-08-21T09:30:00Z',
    expiresAt: '2026-09-12T02:00:00Z',
    deviceLabel: 'Chrome · Windows',
    ipAddress: '192.0.2.10',
  },
]

function createApi(
  overrides: Partial<AccountManagementApi> = {},
): AccountManagementApi {
  return {
    getAccount: async () => account,
    getCreditSummary: async () => ({
      balance: 2460,
      creditLimit: 3000,
      grantAmount: 3000,
      isUnlimited: false,
      inputTokensPerCredit: 100,
      outputTokensPerCredit: 25,
      entries: [
        { entryId: 'preview-1', kind: 'usage', points: -24, balanceAfter: 2460, inputTokens: 800, outputTokens: 400, createdAt: '2026-09-06T00:42:00+08:00' },
        { entryId: 'preview-2', kind: 'usage', points: -36, balanceAfter: 2484, inputTokens: 1600, outputTokens: 500, createdAt: '2026-09-05T22:16:00+08:00' },
        { entryId: 'preview-3', kind: 'usage', points: -480, balanceAfter: 2520, inputTokens: 28000, outputTokens: 5000, createdAt: '2026-09-05T16:30:00+08:00' },
      ],
      totalEntries: 3,
      nextCursor: null,
    }),
    redeemCredits: async () => ({ redeemedPoints: 3000, balance: 3000 }),
    createCreditRedemptionCodes: async () => ({
      codes: [],
      points: 3000,
      expiresAt: '2026-09-22T23:59:59Z',
    }),
    updateProfile: async ({ displayName }) =>
      (account = { ...account, displayName, version: account.version + 1 }),
    updatePreferences: async (input) => (account.preferences = {
      ...account.preferences,
      locale: input.locale,
      timezone: input.timezone,
      researchUpdatesEnabled: input.researchUpdatesEnabled,
      version: account.preferences.version + 1,
    }),
    updateModelDataAuthorization: async ({ allowed, policyVersion }) => (account.preferences = {
      ...account.preferences,
      modelImprovementAllowed: allowed,
      consentPolicyVersion: policyVersion,
      consentUpdatedAt: '2026-08-22T06:00:00Z',
      version: account.preferences.version + 1,
    }),
    changePassword: async () => ({ revokedSessionCount: 1 }),
    listSessions: async () => sessions,
    revokeSession: async (id) => {
      sessions = sessions.filter((item) => item.sessionId !== id)
    },
    requestDataExport: async () => ({
      exportId: 'export-1',
      status: 'ready',
      createdAt: '2026-08-22T06:00:00Z',
      expiresAt: '2026-08-29T06:00:00Z',
      downloadHref:
        'data:application/json;charset=utf-8,' +
        encodeURIComponent(JSON.stringify({ preview: true, account })),
    }),
    deactivateAccount: async () => ({ recoverable: true }),
    deleteAccount: async () => ({ recoverable: false }),
    listAdminUsers: async () => ({ items: [], total: 0, nextCursor: null }),
    updateUserRole: async () => {
      throw new Error('not used')
    },
    disableUser: async () => {
      throw new Error('not used')
    },
    enableUser: async () => {
      throw new Error('not used')
    },
    createPasswordReset: async () => {
      throw new Error('not used')
    },
    listAuditEvents: async () => ({ items: [], nextCursor: null }),
    consumePasswordReset: async () => undefined,
    ...overrides,
  }
}

export const previewApi = createApi()
