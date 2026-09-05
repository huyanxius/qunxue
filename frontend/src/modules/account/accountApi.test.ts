import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  getCurrentSessionViaApi,
  listMyResearchViaApi,
  loginViaApi,
} from './accountApi'

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

  it('uses the server navigation projection without deriving a route or labels from stage actions', async () => {
    const blocker = {
      action: 'start_matching',
      code: 'match_unavailable',
      message: '知识发布暂时不可用。',
      recoverable: true,
    }
    const retry = {
      action: 'start_matching',
      href: '/research/task-1/framework',
      label: '服务端重试',
      method: 'GET',
    }
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      items: [{
        adopted_theory_count: 1,
        allowed_actions: [],
        blocker,
        conversation_id: 'conversation-1',
        created_at: '2026-08-21T08:00:00Z',
        current_framework_id: null,
        current_match_run_id: null,
        current_material_intake_run_id: null,
        current_phenomenon_candidate_id: null,
        current_stage: 'phenomenon_input',
        current_theory_plan_id: null,
        entry_type: 'direct_input',
        knowledge_release_id: 'release-formal-1',
        next_action_label: '由服务端决定的下一步',
        project_title: '线上互助研究',
        phenomenon_summary: {
          phenomenon: '平台迁移后，线上互助为何持续减少？',
          phenomenon_query_id: '59f192dd-85fc-41bf-abaf-d66caa7df958',
          research_intent: null,
          version: 1,
        },
        resume_path: '/research/task-1/framework',
        retry,
        seed_theory_id: null,
        seed_theory_name: null,
        source_run_id: 'run-1',
        source_turn_id: 'turn-1',
        stage_label: '由服务端决定的阶段',
        status: 'in_progress',
        task_id: 'task-1',
        updated_at: '2026-08-21T09:00:00Z',
        version: 3,
      }],
      next_cursor: null,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    await expect(listMyResearchViaApi()).resolves.toEqual([{
      adoptedTheoryCount: 1,
      blocker,
      createdAt: '2026-08-21T08:00:00Z',
      entryPath: '/research/task-1/framework',
      nextActionLabel: '由服务端决定的下一步',
      projectTitle: '线上互助研究',
      phenomenonSummary: '平台迁移后，线上互助为何持续减少？',
      retry,
      stageLabel: '由服务端决定的阶段',
      taskId: 'task-1',
      updatedAt: '2026-08-21T09:00:00Z',
    }])
  })
})
