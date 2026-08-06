import { afterEach, describe, expect, it, vi } from 'vitest'

import { createResearchTaskViaApi, getResearchTaskViaApi } from './researchTaskApi'

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
          phenomenon: 'Communities repeat the same apology script after sanctions.',
          research_intent: 'Study ritualized repair language.',
          context: 'Observed in a volunteer moderation queue.',
          source: 'user_input',
          created_at: '2026-08-05T00:00:00Z',
          updated_at: '2026-08-05T00:00:00Z',
        }),
        { status: 201, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const input = {
      phenomenon: 'Communities repeat the same apology script after sanctions.',
      researchIntent: 'Study ritualized repair language.',
      context: 'Observed in a volunteer moderation queue.',
    }

    const firstTask = await createResearchTaskViaApi(input)
    const secondTask = await createResearchTaskViaApi(input)

    expect(fetchMock).toHaveBeenCalledTimes(2)
    const request = fetchMock.mock.calls[0][0] as Request
    const repeatedRequest = fetchMock.mock.calls[1][0] as Request
    expect(await request.clone().json()).toEqual({
      phenomenon: 'Communities repeat the same apology script after sanctions.',
      research_intent: 'Study ritualized repair language.',
      context: 'Observed in a volunteer moderation queue.',
    })
    expect(request.headers.get('Idempotency-Key')).toBeTruthy()
    expect(request.headers.get('Idempotency-Key')).toBe(
      repeatedRequest.headers.get('Idempotency-Key'),
    )
    expect(firstTask).toEqual({
      taskId: '9c2fb49f-cfd0-41f1-9556-118371c9de65',
      entryType: 'direct_input',
      status: 'draft',
      version: 1,
      allowedActions: ['submit_phenomenon'],
      phenomenon: 'Communities repeat the same apology script after sanctions.',
      researchIntent: 'Study ritualized repair language.',
      context: 'Observed in a volunteer moderation queue.',
      source: 'user_input',
      createdAt: '2026-08-05T00:00:00Z',
      updatedAt: '2026-08-05T00:00:00Z',
    })
    expect(secondTask.taskId).toBe(firstTask.taskId)
    expect(firstTask).not.toHaveProperty('task_id')
    expect(firstTask).not.toHaveProperty('research_intent')
  })

  it('restores a task through the generated transport', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL) =>
      new Response(
        JSON.stringify({
          task_id: '9c2fb49f-cfd0-41f1-9556-118371c9de65',
          entry_type: 'direct_input',
          status: 'draft',
          version: 1,
          allowed_actions: ['submit_phenomenon'],
          phenomenon: 'Informal mentoring stops after layoffs.',
          research_intent: null,
          context: null,
          source: 'user_input',
          created_at: '2026-08-05T00:00:00Z',
          updated_at: '2026-08-05T00:00:00Z',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const task = await getResearchTaskViaApi(
      '9c2fb49f-cfd0-41f1-9556-118371c9de65',
    )

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(task.phenomenon).toBe('Informal mentoring stops after layoffs.')
    expect(task.status).toBe('draft')
    expect(task.allowedActions).toEqual(['submit_phenomenon'])
    expect(task.source).toBe('user_input')
  })
})
