import { apiClient } from '../../api/client'
import type {
  AccountAuditEvent,
  AccountManagementApi,
  AccountPreferences,
  AccountProfile,
  AccountSession,
  AdminUser,
  PersonalDataExport,
} from './accountManagementModels'
import { AccountManagementRequestError } from './accountManagementModels'

type ErrorEnvelope = {
  error?: {
    code?: string
    message?: string
  }
}

type RawPreferences = {
  locale: string
  timezone: string
  research_updates_enabled: boolean
  model_improvement_allowed: boolean
  consent_policy_version: string
  consent_updated_at: string | null
  version: number
}

type RawAccount = {
  user_id: string
  email: string
  display_name: string | null
  role: AccountProfile['role']
  status: AccountProfile['status']
  version: number
  created_at: string
  updated_at: string
  last_login_at: string | null
  is_protected_admin: boolean
  preferences: RawPreferences
}

type RawSession = {
  session_id: string
  current: boolean
  created_at: string
  last_seen_at: string
  expires_at: string
  device_label: string
  ip_address: string | null
}

type RawAdminUser = {
  user_id: string
  email: string
  display_name: string | null
  role: AdminUser['role']
  status: AdminUser['status']
  version: number
  created_at: string
  last_active_at: string | null
  is_current_user: boolean
  is_protected_admin: boolean
}

function absoluteApiHref(href: string) {
  const apiOrigin = import.meta.env.VITE_API_BASE_URL
  return apiOrigin ? new URL(href, apiOrigin).toString() : href
}

async function requestJson<T>(
  method: 'GET' | 'POST' | 'PATCH',
  url: string,
  options: { body?: unknown; idempotencyKey?: string } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (options.idempotencyKey) headers['Idempotency-Key'] = options.idempotencyKey

  const result = await apiClient.request<T, ErrorEnvelope>({
    method,
    url,
    headers,
    body: options.body,
    bodySerializer: options.body === undefined
      ? undefined
      : (body) => JSON.stringify(body),
  })
  if (result.data !== undefined) return result.data as T

  const failure = result.error as ErrorEnvelope | undefined
  throw new AccountManagementRequestError(
    failure?.error?.message ?? '账户服务暂时不可用。',
    result.response?.status,
    failure?.error?.code,
  )
}

function toPreferences(value: RawPreferences): AccountPreferences {
  return {
    locale: value.locale,
    timezone: value.timezone,
    researchUpdatesEnabled: value.research_updates_enabled,
    modelImprovementAllowed: value.model_improvement_allowed,
    consentPolicyVersion: value.consent_policy_version,
    consentUpdatedAt: value.consent_updated_at,
    version: value.version,
  }
}

function toAccount(value: RawAccount): AccountProfile {
  return {
    userId: value.user_id,
    email: value.email,
    displayName: value.display_name,
    role: value.role,
    status: value.status,
    version: value.version,
    createdAt: value.created_at,
    isProtectedAdmin: value.is_protected_admin,
    preferences: toPreferences(value.preferences),
  }
}

function toSession(value: RawSession): AccountSession {
  return {
    sessionId: value.session_id,
    current: value.current,
    createdAt: value.created_at,
    lastSeenAt: value.last_seen_at,
    expiresAt: value.expires_at,
    deviceLabel: value.device_label,
    ipAddress: value.ip_address,
  }
}

function toAdminUser(value: RawAdminUser): AdminUser {
  return {
    userId: value.user_id,
    email: value.email,
    displayName: value.display_name,
    role: value.role,
    status: value.status,
    version: value.version,
    createdAt: value.created_at,
    lastActiveAt: value.last_active_at,
    isCurrentUser: value.is_current_user,
    isProtectedAdmin: value.is_protected_admin,
  }
}

export const accountManagementApi: AccountManagementApi = {
  async getAccount() {
    return toAccount(await requestJson<RawAccount>('GET', '/api/account'))
  },

  async updateProfile(input) {
    const result = await requestJson<RawAccount>('PATCH', '/api/account/profile', {
      idempotencyKey: input.idempotencyKey,
      body: {
        display_name: input.displayName,
        expected_version: input.expectedVersion,
      },
    })
    return toAccount(result)
  },

  async updatePreferences(input) {
    const result = await requestJson<RawPreferences>('PATCH', '/api/account/preferences', {
      idempotencyKey: input.idempotencyKey,
      body: {
        locale: input.locale,
        timezone: input.timezone,
        research_updates_enabled: input.researchUpdatesEnabled,
        expected_version: input.expectedVersion,
      },
    })
    return toPreferences(result)
  },

  async updateModelDataAuthorization(input) {
    const result = await requestJson<RawPreferences>(
      'PATCH',
      '/api/account/model-data-authorization',
      {
        idempotencyKey: input.idempotencyKey,
        body: {
          allowed: input.allowed,
          policy_version: input.policyVersion,
          expected_version: input.expectedVersion,
        },
      },
    )
    return toPreferences(result)
  },

  async changePassword(input) {
    const result = await requestJson<{ revoked_session_count: number }>(
      'POST',
      '/api/account/password/change',
      {
        idempotencyKey: input.idempotencyKey,
        body: {
          current_password: input.currentPassword,
          new_password: input.newPassword,
          revoke_other_sessions: input.revokeOtherSessions,
        },
      },
    )
    return { revokedSessionCount: result.revoked_session_count }
  },

  async listSessions() {
    const result = await requestJson<{ items: RawSession[] }>('GET', '/api/account/sessions')
    return result.items.map(toSession)
  },

  async revokeSession(sessionId, intent) {
    await requestJson('POST', `/api/account/sessions/${encodeURIComponent(sessionId)}/revoke`, {
      idempotencyKey: intent.idempotencyKey,
    })
  },

  async requestDataExport(intent) {
    const result = await requestJson<{
      export_id: string
      status: PersonalDataExport['status']
      created_at: string
      expires_at: string
      download_href: string
    }>('POST', '/api/account/data-exports', {
      idempotencyKey: intent.idempotencyKey,
      body: { format: 'json' },
    })
    return {
      exportId: result.export_id,
      status: result.status,
      createdAt: result.created_at,
      expiresAt: result.expires_at,
      downloadHref: absoluteApiHref(result.download_href),
    }
  },

  async deactivateAccount(input) {
    return requestJson('POST', '/api/account/deactivate', {
      idempotencyKey: input.idempotencyKey,
      body: { current_password: input.currentPassword, reason: input.reason },
    })
  },

  async deleteAccount(input) {
    return requestJson('POST', '/api/account/delete', {
      idempotencyKey: input.idempotencyKey,
      body: {
        current_password: input.currentPassword,
        confirmation_email: input.confirmationEmail,
      },
    })
  },

  async listAdminUsers(input) {
    const search = new URLSearchParams()
    if (input.query) search.set('query', input.query)
    if (input.status) search.set('status', input.status)
    if (input.cursor) search.set('cursor', input.cursor)
    const suffix = search.size ? `?${search.toString()}` : ''
    const result = await requestJson<{
      items: RawAdminUser[]
      total: number
      next_cursor: string | null
    }>('GET', `/api/admin/users${suffix}`)
    return {
      items: result.items.map(toAdminUser),
      total: result.total,
      nextCursor: result.next_cursor,
    }
  },

  async updateUserRole(userId, input) {
    return toAdminUser(await requestJson<RawAdminUser>(
      'PATCH',
      `/api/admin/users/${encodeURIComponent(userId)}/role`,
      {
        idempotencyKey: input.idempotencyKey,
        body: {
          role: input.role,
          expected_version: input.expectedVersion,
          reason: input.reason,
        },
      },
    ))
  },

  async disableUser(userId, input) {
    return toAdminUser(await requestJson<RawAdminUser>(
      'POST',
      `/api/admin/users/${encodeURIComponent(userId)}/disable`,
      {
        idempotencyKey: input.idempotencyKey,
        body: { expected_version: input.expectedVersion, reason: input.reason },
      },
    ))
  },

  async enableUser(userId, input) {
    return toAdminUser(await requestJson<RawAdminUser>(
      'POST',
      `/api/admin/users/${encodeURIComponent(userId)}/enable`,
      {
        idempotencyKey: input.idempotencyKey,
        body: { expected_version: input.expectedVersion, reason: input.reason },
      },
    ))
  },

  async createPasswordReset(userId, intent) {
    const result = await requestJson<{
      reset_id: string
      expires_at: string
      reset_token: string | null
    }>('POST', `/api/admin/users/${encodeURIComponent(userId)}/password-reset-links`, {
      idempotencyKey: intent.idempotencyKey,
    })
    return {
      resetId: result.reset_id,
      resetUrl: result.reset_token
        ? `/password-reset/${encodeURIComponent(result.reset_token)}`
        : '',
      expiresAt: result.expires_at,
    }
  },

  async listAuditEvents(input = {}) {
    const search = new URLSearchParams()
    if (input.cursor) search.set('cursor', input.cursor)
    if (input.limit) search.set('limit', String(input.limit))
    const suffix = search.size ? `?${search.toString()}` : ''
    const result = await requestJson<{
      items: Array<{
        event_id: string
        action: string
        outcome: AccountAuditEvent['outcome']
        actor_email: string | null
        target_email: string | null
        reason: string | null
        occurred_at: string
      }>
      next_cursor: string | null
    }>('GET', `/api/admin/audit-events${suffix}`)
    return {
      items: result.items.map((event) => ({
        eventId: event.event_id,
        action: event.action,
        outcome: event.outcome,
        actorEmail: event.actor_email,
        targetEmail: event.target_email,
        reason: event.reason,
        occurredAt: event.occurred_at,
      })),
      nextCursor: result.next_cursor,
    }
  },

  async consumePasswordReset(input) {
    await requestJson('POST', '/api/account/password-resets/consume', {
      idempotencyKey: input.idempotencyKey,
      body: { token: input.token, new_password: input.newPassword },
    })
  },
}
