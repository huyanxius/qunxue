import { afterEach, describe, expect, it, vi } from 'vitest'

import { getCurrentSessionViaApi, loginViaApi } from './accountApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

const sessionResponse = {
  session_id: '25b191bb-2d85-4a88-8863-2cabf506a7a8',
  status: 'active',
  version: 1,
  allowed_actions: ['logout'],
  user: {
    user_id: '95306bf9-194d-4677-be2d-eef4f6aa86d1',
    email: 'researcher@example.com',
    display_name: null,
  },
  expires_at: '2026-08-14T00:00:00Z',
}

describe('account API adapter', () => {
  it('restores the current session through an HttpOnly-cookie request', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL) =>
      new Response(JSON.stringify(sessionResponse), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(getCurrentSessionViaApi()).resolves.toEqual({
      sessionId: sessionResponse.session_id,
      user: {
        userId: sessionResponse.user.user_id,
        email: sessionResponse.user.email,
        displayName: null,
      },
      expiresAt: sessionResponse.expires_at,
    })
    const request = fetchMock.mock.calls[0][0] as Request
    expect(request.credentials).toBe('include')
  })

  it('treats a missing cookie session as anonymous', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            error: {
              code: 'unauthenticated',
              message: '请先登录。',
              trace_id: 'trace-1',
            },
          }),
          { status: 401, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )

    await expect(getCurrentSessionViaApi()).resolves.toBeNull()
  })

  it('sends credentials only in the login body and uses an idempotency key', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL) =>
      new Response(JSON.stringify(sessionResponse), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await loginViaApi('researcher@example.com', 'research-passphrase')

    const request = fetchMock.mock.calls[0][0] as Request
    expect(request.url).not.toContain('research-passphrase')
    expect(request.headers.get('Idempotency-Key')).toBeTruthy()
    await expect(request.clone().json()).resolves.toMatchObject({
      email: 'researcher@example.com',
      password: 'research-passphrase',
    })
  })
})
