import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as publicApi from './index'

function renderWorkspace(taskId: string, onNavigateHome = vi.fn()) {
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

  return { onNavigateHome }
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('SocioMatchWorkspace public API', () => {
  it('keeps transport functions and query hooks private', () => {
    expect(Object.keys(publicApi).sort()).toEqual([
      'SocioMatchWorkspace',
      'submitResearchTask',
    ])
  })

  it('restores the saved intake fields from the task route', async () => {
    const taskId = '9c2fb49f-cfd0-41f1-9556-118371c9de65'
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          task_id: taskId,
          phenomenon: 'A weekly ritual loses participation after hybridization.',
          research_intent: 'Study coordination drift.',
          context: 'Observed in a department sync over six weeks.',
          source: 'user_input',
          created_at: '2026-08-05T00:00:00Z',
          updated_at: '2026-08-05T00:00:00Z',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const { onNavigateHome } = renderWorkspace(taskId)

    expect(
      await screen.findByText(
        'A weekly ritual loses participation after hybridization.',
      ),
    ).toBeVisible()
    expect(screen.getByText('Study coordination drift.')).toBeVisible()
    expect(screen.getByText('user_input')).toBeVisible()

    const returnLink = screen.getByRole('link', { name: 'Back to intake' })
    expect(returnLink).toHaveAttribute('href', '/')
    fireEvent.click(returnLink)
    expect(onNavigateHome).toHaveBeenCalledOnce()
  })

  it('shows a specific message when the task_id does not exist', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            error: {
              code: 'research_task_not_found',
              message: "research task 'missing' was not found",
              trace_id: 'trace-404',
            },
          }),
          { status: 404, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )

    renderWorkspace('missing')

    expect(
      await screen.findByText('No research task exists for this task_id.'),
    ).toBeVisible()
    expect(
      screen.getByText("research task 'missing' was not found"),
    ).toBeVisible()
  })
})
