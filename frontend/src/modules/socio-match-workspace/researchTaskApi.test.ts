import { afterEach, describe, expect, it, vi } from 'vitest'

import { createResearchTaskViaApi } from './researchTaskApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('research task API', () => {
  it('sends a stable idempotency key through the generated transport', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL) =>
      new Response(
        JSON.stringify({
          task_id: '9c2fb49f-cfd0-41f1-9556-118371c9de65',
          entry_type: 'direct_input',
          status: 'draft',
          version: 1,
          allowed_actions: ['submit_phenomenon'],
          created_at: '2026-07-28T00:00:00Z',
          updated_at: '2026-07-28T00:00:00Z',
        }),
        { status: 201, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const task = await createResearchTaskViaApi('stable-request-key')

    expect(fetchMock).toHaveBeenCalledOnce()
    const request = fetchMock.mock.calls[0][0] as Request
    expect(request.headers.get('Idempotency-Key')).toBe('stable-request-key')
    expect(task).toEqual({
      taskId: '9c2fb49f-cfd0-41f1-9556-118371c9de65',
      entryType: 'direct_input',
      status: 'draft',
      version: 1,
      allowedActions: ['submit_phenomenon'],
      createdAt: '2026-07-28T00:00:00Z',
      updatedAt: '2026-07-28T00:00:00Z',
    })
    expect(task).not.toHaveProperty('task_id')
    expect(task).not.toHaveProperty('allowed_actions')
  })
})
