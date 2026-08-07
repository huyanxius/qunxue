import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  createResearchTaskViaApi,
  startPhenomenonViaApi,
} from './researchTaskApi'

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

  it('uses generated calls for the direct-input candidate chain', async () => {
    const taskId = '9c2fb49f-cfd0-41f1-9556-118371c9de65'
    const candidateId = '45e7c24b-fbe4-4630-b6f5-6ed8b398a242'
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const request = input as Request
      if (request.url.endsWith('/api/research-tasks')) {
        return Response.json({
          task_id: taskId,
          entry_type: 'direct_input',
          status: 'draft',
          version: 1,
          allowed_actions: ['submit_phenomenon'],
          created_at: '2026-08-07T00:00:00Z',
          updated_at: '2026-08-07T00:00:00Z',
        }, { status: 201 })
      }
      if (request.url.endsWith('/inputs/direct')) {
        return Response.json({
          input_id: '539b93ac-d35e-499d-9138-9898138b69ae',
          task_id: taskId,
          entry_type: 'direct_input',
          version: 1,
          allowed_actions: ['extract_phenomenon_candidates'],
          source_ref_ids: ['input:direct'],
          accepted_at: '2026-08-07T00:00:00Z',
        })
      }
      return Response.json({
        task_id: taskId,
        version: 1,
        allowed_actions: ['update', 'confirm'],
        candidates: [{
          candidate_id: candidateId,
          task_id: taskId,
          version: 1,
          status: 'proposed',
          allowed_actions: ['update', 'confirm'],
          phenomenon: '社区互助为何减少？',
          research_intent: null,
          context: null,
          source_ref_ids: ['input:direct'],
          evidence_refs: [],
          model: {
            provider: 'deterministic-mock',
            model_version: 'mock-sociology-v1',
            capability: 'mock',
            degraded: false,
            knowledge_release_id: null,
            trace: {
              trace_id: 'e8d819ab-3cb0-4cc8-9c40-c0113ab72a55',
              request_id: '92b8e6e7-61d6-49d5-bd80-0b6d793fab31',
              contract_version: 'v1',
            },
          },
        }],
        stable_order: [candidateId],
        next_cursor: null,
        model: {
          provider: 'deterministic-mock',
          model_version: 'mock-sociology-v1',
          capability: 'mock',
          degraded: false,
          knowledge_release_id: null,
          trace: {
            trace_id: 'e8d819ab-3cb0-4cc8-9c40-c0113ab72a55',
            request_id: '92b8e6e7-61d6-49d5-bd80-0b6d793fab31',
            contract_version: 'v1',
          },
        },
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    const started = await startPhenomenonViaApi('社区互助为何减少？')

    expect(started.taskId).toBe(taskId)
    expect(started.candidate.candidateId).toBe(candidateId)
    expect(fetchMock).toHaveBeenCalledTimes(3)
    const directRequest = fetchMock.mock.calls[1][0] as Request
    expect(await directRequest.json()).toMatchObject({
      phenomenon: '社区互助为何减少？',
    })
  })
})
