import { afterEach, describe, expect, it, vi } from 'vitest'

import { accountManagementApi, getAccountSystemHealth } from './accountManagementApi'
import { AccountManagementRequestError } from './accountManagementModels'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

const rawAccount = {
  user_id: '95306bf9-194d-4677-be2d-eef4f6aa86d1',
  email: 'researcher@example.com',
  display_name: '林研究员',
  role: 'member',
  status: 'active',
  version: 2,
  created_at: '2026-08-20T08:00:00Z',
  updated_at: '2026-08-22T08:00:00Z',
  last_login_at: '2026-08-22T07:00:00Z',
  is_protected_admin: false,
  preferences: {
    locale: 'zh-CN',
    timezone: 'Asia/Shanghai',
    research_updates_enabled: true,
    model_improvement_allowed: false,
    consent_policy_version: '2026-08-secondary-use-v1',
    consent_updated_at: null,
    version: 1,
  },
} as const

describe('account management API adapter', () => {
  it('exposes system health through the account module adapter', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL) => new Response(JSON.stringify({
      capability: 'base',
      contract_version: 'v1',
      knowledge_release_id: 'release-1',
      model_version: 'deepseek-v4-flash',
      persistence: 'sqlite',
      provider: 'openai-compatible',
      runtime_mode: 'base',
      service: 'qunxue-api',
      status: 'ok',
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getAccountSystemHealth()).resolves.toMatchObject({
      contractVersion: 'v1',
      knowledgeReleaseId: 'release-1',
      modelVersion: 'deepseek-v4-flash',
    })
    expect(new URL((fetchMock.mock.calls[0][0] as Request).url).pathname).toBe('/api/health')
  })

  it('forwards the caller-owned mutation key with cookie credentials', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL) => new Response(JSON.stringify(rawAccount), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await accountManagementApi.updateProfile({
      displayName: '林研究员',
      expectedVersion: 1,
      idempotencyKey: 'profile-intent-1',
    })

    const request = fetchMock.mock.calls[0][0] as Request
    expect(request.credentials).toBe('include')
    expect(request.headers.get('Idempotency-Key')).toBe('profile-intent-1')
    await expect(request.clone().json()).resolves.toEqual({
      display_name: '林研究员',
      expected_version: 1,
    })
  })

  it('preserves the stable server error code for conflict recovery', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      error: {
        code: 'idempotency_conflict',
        message: '该请求标识已用于另一项操作，请重新提交。',
        trace_id: 'trace-1',
      },
    }), {
      status: 409,
      headers: { 'Content-Type': 'application/json' },
    })))

    const failure = await accountManagementApi.updateProfile({
      displayName: '另一个名称',
      expectedVersion: 1,
      idempotencyKey: 'profile-intent-1',
    }).catch((error: unknown) => error)

    expect(failure).toBeInstanceOf(AccountManagementRequestError)
    expect(failure).toMatchObject({
      status: 409,
      code: 'idempotency_conflict',
    })
  })

  it('resolves export downloads against the API origin in split-port deployments', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://127.0.0.1:8017')
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      export_id: 'export-1',
      status: 'ready',
      created_at: '2026-08-22T08:00:00Z',
      expires_at: '2026-08-29T08:00:00Z',
      download_href: '/api/account/data-exports/export-1/download',
    }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    })))

    const result = await accountManagementApi.requestDataExport({
      idempotencyKey: 'export-intent-1',
    })

    expect(result.downloadHref).toBe(
      'http://127.0.0.1:8017/api/account/data-exports/export-1/download',
    )
  })

  it('keeps export downloads relative for same-origin deployments', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '')
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      export_id: 'export-2',
      status: 'ready',
      created_at: '2026-08-22T08:00:00Z',
      expires_at: '2026-08-29T08:00:00Z',
      download_href: '/api/account/data-exports/export-2/download',
    }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    })))

    const result = await accountManagementApi.requestDataExport({
      idempotencyKey: 'export-intent-2',
    })

    expect(result.downloadHref).toBe(
      '/api/account/data-exports/export-2/download',
    )
  })
})
