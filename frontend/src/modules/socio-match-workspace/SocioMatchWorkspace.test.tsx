import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as publicApi from './index'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('SocioMatchWorkspace public API', () => {
  it('keeps transport functions and query hooks private', () => {
    expect(Object.keys(publicApi).sort()).toEqual([
      'NewResearchPage',
      'PhenomenonWorkspace',
      'ResearchDemoPreview',
      'SocioMatchWorkspace',
      'startResearchTask',
    ])
  })

  it('receives routing state and navigation as stable props', async () => {
    const taskId = '9c2fb49f-cfd0-41f1-9556-118371c9de65'
    const onNavigateHome = vi.fn()
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            task_id: taskId,
            entry_type: 'direct_input',
            status: 'draft',
            version: 1,
            allowed_actions: ['submit_phenomenon'],
            created_at: '2026-07-28T00:00:00Z',
            updated_at: '2026-07-28T00:00:00Z',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <publicApi.SocioMatchWorkspace
          taskId={taskId}
          homeHref="/"
          onNavigateHome={onNavigateHome}
        />
      </QueryClientProvider>,
    )

    expect(await screen.findByText(taskId)).toBeVisible()
    expect(screen.getByText('direct_input')).toBeVisible()
    expect(screen.getByText('submit_phenomenon')).toBeVisible()

    const returnLink = screen.getByRole('link', {
      name: '← 返回工程起点',
    })
    expect(returnLink).toHaveAttribute('href', '/')
    fireEvent.click(returnLink)
    expect(onNavigateHome).toHaveBeenCalledOnce()
  })
})
