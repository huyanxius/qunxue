import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { RecentResearchPanel } from './RecentResearchPanel'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function renderPanel(items: unknown[], queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
    items,
    next_cursor: null,
  }), { status: 200, headers: { 'Content-Type': 'application/json' } })))
  return render(
    <QueryClientProvider client={queryClient}>
      <RecentResearchPanel emptyIntro={<p>首次研究引导</p>} />
    </QueryClientProvider>,
  )
}

describe('RecentResearchPanel onboarding', () => {
  it('shows the first-use guide only while the research list is empty', async () => {
    renderPanel([])

    expect(await screen.findByText('首次研究引导')).toBeVisible()
    expect(screen.getByRole('heading', { name: '还没有研究任务' }).closest('section')).toHaveClass(
      'recent-research--with-intro',
    )
  })

  it('keeps the first-use guide out of an established workspace', async () => {
    renderPanel([{
      adopted_theory_count: 0,
      allowed_actions: ['confirm_phenomenon'],
      blocker: null,
      created_at: '2026-08-08T08:00:00Z',
      current_framework_id: null,
      current_match_run_id: null,
      current_material_intake_run_id: null,
      current_phenomenon_candidate_id: 'candidate-1',
      current_stage: 'phenomenon_confirmation',
      entry_type: 'direct',
      next_action_label: '确认现象',
      phenomenon_summary: {
        phenomenon: '同一社区中的互助为何逐渐减少？',
        research_intent: null,
      },
      seed_theory_id: null,
      seed_theory_name: null,
      resume_path: '/research/task-1/phenomenon',
      retry: null,
      stage_label: '现象待确认',
      status: 'active',
      task_id: 'task-1',
      updated_at: '2026-08-09T08:00:00Z',
      version: 1,
    }])

    expect(await screen.findByText('同一社区中的互助为何逐渐减少？')).toBeVisible()
    expect(screen.queryByText('首次研究引导')).not.toBeInTheDocument()
  })

  it('shows multiple recent research tasks instead of hiding all but the first', async () => {
    const commonTask = {
      adopted_theory_count: 0,
      allowed_actions: ['confirm_phenomenon'],
      blocker: null,
      created_at: '2026-08-08T08:00:00Z',
      current_framework_id: null,
      current_match_run_id: null,
      current_material_intake_run_id: null,
      current_phenomenon_candidate_id: 'candidate-1',
      current_stage: 'phenomenon_confirmation',
      entry_type: 'direct',
      next_action_label: '确认现象',
      seed_theory_id: null,
      seed_theory_name: null,
      retry: null,
      stage_label: '现象待确认',
      status: 'active',
      version: 1,
    }
    renderPanel([{
      ...commonTask,
      phenomenon_summary: { phenomenon: '同一社区中的互助为何逐渐减少？', research_intent: null },
      resume_path: '/research/task-1/phenomenon',
      task_id: 'task-1',
      updated_at: '2026-08-09T08:00:00Z',
    }, {
      ...commonTask,
      phenomenon_summary: { phenomenon: '平台协作为什么产生隐形劳动？', research_intent: null },
      resume_path: '/research/task-2/phenomenon',
      task_id: 'task-2',
      updated_at: '2026-08-08T08:00:00Z',
    }])

    expect(await screen.findByText('同一社区中的互助为何逐渐减少？')).toBeVisible()
    expect(screen.getByText('平台协作为什么产生隐形劳动？')).toBeVisible()
  })

  it('refreshes a cached list when the work home is reopened', async () => {
    const responses = [
      { items: [], next_cursor: null },
      { items: [{
        adopted_theory_count: 0,
        allowed_actions: ['confirm_phenomenon'],
        blocker: null,
        created_at: '2026-08-08T08:00:00Z',
        current_framework_id: null,
        current_match_run_id: null,
        current_material_intake_run_id: null,
        current_phenomenon_candidate_id: 'candidate-1',
        current_stage: 'phenomenon_confirmation',
        entry_type: 'direct',
        next_action_label: '确认现象',
        phenomenon_summary: { phenomenon: '新建后应立即出现的研究', research_intent: null },
        seed_theory_id: null,
        seed_theory_name: null,
        resume_path: '/research/task-2/phenomenon',
        retry: null,
        stage_label: '现象待确认',
        status: 'active',
        task_id: 'task-2',
        updated_at: '2026-08-09T08:00:00Z',
        version: 1,
      }], next_cursor: null },
    ]
    const fetch = vi.fn(async () => new Response(JSON.stringify(
      responses[Math.min(fetch.mock.calls.length - 1, responses.length - 1)],
    ), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetch)
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
    })

    const first = render(
      <QueryClientProvider client={queryClient}>
        <RecentResearchPanel emptyIntro={<p>首次研究引导</p>} />
      </QueryClientProvider>,
    )
    expect(await screen.findByText('还没有研究任务')).toBeVisible()
    first.unmount()

    render(
      <QueryClientProvider client={queryClient}>
        <RecentResearchPanel emptyIntro={<p>首次研究引导</p>} />
      </QueryClientProvider>,
    )

    expect(await screen.findByText('新建后应立即出现的研究')).toBeVisible()
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('uses the server retry target when the latest research is blocked', async () => {
    renderPanel([{
      adopted_theory_count: 0,
      allowed_actions: [],
      blocker: {
        action: 'start_matching',
        code: 'no_reliable_candidate',
        message: '暂时没有可正式采用的理论候选。',
        recoverable: true,
      },
      conversation_id: 'conversation-1',
      created_at: '2026-08-08T08:00:00Z',
      current_framework_id: null,
      current_match_run_id: null,
      current_material_intake_run_id: null,
      current_phenomenon_candidate_id: null,
      current_stage: 'theory_matching',
      entry_type: 'direct_input',
      knowledge_release_id: 'release-formal-1',
      next_action_label: '重新检查理论候选',
      phenomenon_summary: {
        phenomenon: '社区互助为什么逐渐减少？',
        research_intent: null,
      },
      resume_path: '/research/task-3/match',
      retry: {
        action: 'start_matching',
        href: '/research/task-3/match?retry=1',
        method: 'GET',
      },
      seed_theory_id: null,
      seed_theory_name: null,
      source_run_id: 'run-1',
      source_turn_id: 'turn-1',
      stage_label: '理论匹配受阻',
      status: 'in_progress',
      task_id: 'task-3',
      updated_at: '2026-08-09T08:00:00Z',
      version: 1,
    }])

    expect(await screen.findByText('暂时没有可正式采用的理论候选。')).toBeVisible()
    expect(screen.getByRole('link', { name: /社区互助为什么逐渐减少/ })).toHaveAttribute(
      'href',
      '/research/task-3/match?retry=1',
    )
    expect(screen.getByText('重新检查理论候选')).toBeVisible()
  })
})
