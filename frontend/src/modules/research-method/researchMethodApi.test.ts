import { afterEach, describe, expect, it, vi } from 'vitest'

import { createMethodPlan, getCurrentMethodPlan } from './researchMethodApi'

afterEach(() => vi.unstubAllGlobals())

describe('research method API', () => {
  it('loads the current plan and creates a deferred method choice', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = input instanceof Request ? input : new Request(String(input), init)
      return new Response(JSON.stringify(request.method === 'GET' ? null : { plan_id: 'plan-1', method_kind: 'undecided' }), { status: request.method === 'GET' ? 200 : 201, headers: { 'Content-Type': 'application/json' } })
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(getCurrentMethodPlan('task-1')).resolves.toBeNull()
    await expect(createMethodPlan('task-1', { framework_id: 'framework-1', theory_plan_id: 'theory-1', method_kind: 'undecided' })).resolves.toMatchObject({ plan_id: 'plan-1' })
    const request = fetchMock.mock.calls[1][0] instanceof Request ? fetchMock.mock.calls[1][0] as Request : new Request(String(fetchMock.mock.calls[1][0]), fetchMock.mock.calls[1][1])
    expect(request.headers.get('Idempotency-Key')).toMatch(/^research-method:/)
  })
})
